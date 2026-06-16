from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from ddgs import DDGS

from .models import SearchResult

logger = logging.getLogger(__name__)

_MISSING_FIELD_ALIASES = {
    "phone": "phone_number",
    "phone_number": "phone_number",
    "website": "website_links",
    "websites": "website_links",
    "website_links": "website_links",
    "facebook": "website_links",
    "open_hours": "open_hours",
    "hours": "open_hours",
    "opening_hours": "open_hours",
}

_PHONE_QUERY_SUFFIXES = (
    "số điện thoại",
    "điện thoại",
    "hotline",
    "liên hệ",
    "phone number",
)

_WEBSITE_QUERY_SUFFIXES = (
    "website",
    "trang chủ",
    "fanpage",
    "facebook",
)

_OPEN_HOURS_QUERY_SUFFIXES = (
    "giờ mở cửa",
    "giờ hoạt động",
    "opening hours",
    "business hours",
)

_GENERIC_BUSINESS_TERMS = {
    "shop",
    "store",
    "company",
    "business",
    "restaurant",
    "cửa hàng",
    "siêu thị",
    "đại lý",
    "công ty",
    "nhà hàng",
    "quán",
    "cơ sở",
    "showroom",
    "hải sản",
    "nội thất",
    "điện lạnh",
    "khách sạn",
    "spa",
    "salon",
    "café",
    "coffee",
    "trà sữa",
    "ăn uống",
    "phụ kiện",
    "loa mic",
    "karaoke",
}

_GENERIC_OR_SLOGAN_TERMS = {
    "best",
    "quality",
    "uy tín",
    "chất lượng",
    "giá rẻ",
    "mua ngay",
    "hot",
    "sale",
    "khuyến mãi",
    "giảm giá",
    "địa chỉ",
    "liên hệ",
    "điện thoại",
    "hotline",
    "website",
    "facebook",
    "giờ mở cửa",
    "opening hours",
    "mở cửa",
}

_ADDRESS_STOPWORDS = {
    "số",
    "đường",
    "đại lộ",
    "phố",
    "phường",
    "ph",
    "p",
    "quận",
    "q",
    "huyện",
    "huyện",
    "thành phố",
    "tp",
    "tphcm",
    "hồ chí minh",
    "hochiminh",
    "việt nam",
    "vietnam",
    "địa chỉ",
    "đc",
    "dc",
    "kp",
    "khu phố",
    "khu",
    "lầu",
    "tầng",
    "floor",
    "no",
    "street",
    "ward",
    "district",
    "city",
    "address",
}

_NOISE_PATTERNS = (
    "404",
    "captcha",
    "login",
    "sign in",
    "not found",
    "page not found",
    "access denied",
    "subscribe",
    "subscribe to",
)

_GENERIC_DIRECTORY_PATTERNS = (
    "danh sách",
    "directory",
    "directories",
    "list of",
    "business directory",
)


def generate_queries(
    shop_name: str | None,
    address: str | None,
    missing_fields: set[str],
) -> list[str]:
    """Generate targeted search queries for the missing enrichment fields.

    Args:
        shop_name: Normalized primary business name from the image.
        address: Normalized address from the image, if available.
        missing_fields: Set of fields that still need enrichment.

    Returns:
        Deduplicated queries in the order they should be searched.
    """
    normalized_name = _normalize_query_text(shop_name)
    if not normalized_name:
        return []

    normalized_fields = {_normalize_field(field) for field in missing_fields}
    normalized_fields.discard("")

    queries: list[str] = []
    _append_query(queries, f'"{normalized_name}"')

    normalized_address = _normalize_query_text(address)
    if normalized_address:
        _append_query(queries, f'"{normalized_name}" {normalized_address}')

    if "phone_number" in normalized_fields:
        _append_field_queries(queries, normalized_name, _PHONE_QUERY_SUFFIXES)

    if "website_links" in normalized_fields:
        _append_field_queries(queries, normalized_name, _WEBSITE_QUERY_SUFFIXES)

    if "open_hours" in normalized_fields:
        _append_field_queries(queries, normalized_name, _OPEN_HOURS_QUERY_SUFFIXES)

    return _deduplicate_strings(queries)


def score_result(
    result: SearchResult,
    shop_name: str | None,
    address: str | None,
) -> int:
    """Score a search result for relevance to the target business.

    Args:
        result: Search result returned by DuckDuckGo.
        shop_name: Normalized primary business name from the image.
        address: Normalized address from the image, if available.

    Returns:
        Integer relevance score. Higher scores are more relevant.
    """
    title = result.title.strip()
    snippet = result.snippet.strip()
    url = result.url.strip()

    title_lower = title.lower()
    snippet_lower = snippet.lower()
    url_lower = url.lower()
    combined_lower = f"{title_lower} {snippet_lower} {url_lower}"

    normalized_name = _normalize_match_text(shop_name)
    address_fragments = _address_fragments(address)

    score = 0

    if "facebook.com" in url_lower:
        score += 5
    if "maps.google" in url_lower or "google.com/maps" in url_lower:
        score += 4

    if normalized_name and normalized_name in title_lower:
        score += 3
    elif _partial_name_match(title_lower, normalized_name):
        score += 1

    if normalized_name and normalized_name in snippet_lower:
        score += 2
    elif _partial_name_match(snippet_lower, normalized_name):
        score += 1

    if _address_fragments_match(combined_lower, address_fragments):
        score += 1

    if any(pattern in combined_lower for pattern in _NOISE_PATTERNS):
        score -= 5

    if "google.com/search" in url_lower:
        score -= 5

    if _looks_like_generic_directory(title_lower, snippet_lower, url_lower):
        score -= 1

    if score == 0:
        score -= 1

    return score


def is_valid_business_name(shop_name: str | None) -> bool:
    """Return whether a shop name is specific enough to search safely.

    Args:
        shop_name: Candidate business name from VLM extraction.

    Returns:
        True when the value looks like a business name rather than missing,
        generic, slogan-like, or URL/phone-number text.
    """
    if shop_name is None:
        logger.info("Skipping enrichment: shop_name is missing.")
        return False

    normalized = shop_name.strip()
    if len(normalized) < 3:
        logger.info("Skipping enrichment: shop_name is too short: %r", shop_name)
        return False

    if _looks_like_url(normalized) or _looks_like_phone_only(normalized):
        logger.info("Skipping enrichment: shop_name looks like a URL or phone number: %r", shop_name)
        return False

    lowered = normalized.lower()
    if lowered in _GENERIC_BUSINESS_TERMS or lowered in _GENERIC_OR_SLOGAN_TERMS:
        logger.info("Skipping enrichment: shop_name is generic/slogan-like: %r", shop_name)
        return False

    meaningful_tokens = _meaningful_business_tokens(normalized)
    if not meaningful_tokens:
        logger.info("Skipping enrichment: shop_name has no meaningful tokens: %r", shop_name)
        return False

    if len(meaningful_tokens) == 1 and _looks_like_slogan(normalized):
        logger.info("Skipping enrichment: shop_name appears to be a slogan: %r", shop_name)
        return False

    return True


def score_and_deduplicate_results(
    results: Iterable[SearchResult],
    shop_name: str | None,
    address: str | None,
) -> list[tuple[int, SearchResult]]:
    """Score results and keep only the first occurrence of each URL.

    Args:
        results: Raw search results, possibly containing duplicate URLs.
        shop_name: Normalized primary business name from the image.
        address: Normalized address from the image, if available.

    Returns:
        Deduplicated `(score, result)` pairs sorted by score descending.
    """
    seen_urls: set[str] = set()
    scored_results: list[tuple[int, SearchResult]] = []

    for result in results:
        normalized_url = _normalize_url(result.url)
        if not normalized_url or normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)
        scored_results.append((score_result(result, shop_name, address), result))

    scored_results.sort(key=lambda item: item[0], reverse=True)
    return scored_results


def select_top_results(
    scored_results: list[tuple[int, SearchResult]],
    limit: int,
) -> list[SearchResult]:
    """Select the highest-scoring results to pass to the LLM.

    Args:
        scored_results: Deduplicated results sorted by score descending.
        limit: Maximum number of results to return.

    Returns:
        Top positive-scoring results, capped at `limit`.
    """
    if limit <= 0:
        return []

    selected: list[SearchResult] = []
    for score, result in scored_results:
        if score <= 0:
            continue
        selected.append(result)
        if len(selected) >= limit:
            break

    return selected


class DuckDuckGoSearcher:
    """Search DuckDuckGo with field-aware queries and relevance filtering."""

    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results
        self.last_queries: list[str] = []

    def search(
        self,
        shop_name: str | None,
        address: str | None,
        missing_fields: set[str] | None = None,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """Search for missing business fields using targeted queries.

        Args:
            shop_name: Primary business name extracted from the image.
            address: Address extracted from the image, if available.
            missing_fields: Fields to search for. If omitted, all enrichment
                fields are searched.
            top_k: Maximum number of scored results to return. Defaults to
                `self.max_results`.

        Returns:
            Top scored, deduplicated search results.
        """
        if not is_valid_business_name(shop_name):
            self.last_queries = []
            return []

        normalized_missing_fields = {
            _normalize_field(field)
            for field in (missing_fields or {"phone_number", "website_links", "open_hours"})
        }
        normalized_missing_fields.discard("")
        if not normalized_missing_fields:
            logger.info("Skipping enrichment: no missing fields were provided.")
            self.last_queries = []
            return []

        queries = generate_queries(shop_name, address, normalized_missing_fields)
        if not queries:
            logger.info("Skipping enrichment: no searchable business name was available.")
            self.last_queries = []
            return []

        self.last_queries = queries
        _log_generated_queries(queries)

        raw_results = self._search_queries(queries)
        if not raw_results:
            logger.info("DuckDuckGo search returned no results for %s.", shop_name)
            return []

        scored_results = score_and_deduplicate_results(raw_results, shop_name, address)
        _log_result_scores(scored_results)

        limit = self.max_results if top_k is None else top_k
        top_results = select_top_results(scored_results, limit=limit)
        _log_top_results(top_results)

        if not top_results:
            logger.info("DuckDuckGo search produced no positive-scoring results for %s.", shop_name)

        return top_results

    def _search_queries(self, queries: list[str]) -> list[SearchResult]:
        results: list[SearchResult] = []
        for query in queries:
            results.extend(self._search_query(query))
        return results

    def _search_query(self, query: str) -> list[SearchResult]:
        logger.info("Searching DuckDuckGo for: %s", query)
        query_results: list[SearchResult] = []

        try:
            with DDGS() as ddgs:
                for item in ddgs.text(query, max_results=self.max_results):
                    query_results.append(_search_result_from_ddgs_item(item))
        except Exception:
            logger.exception("DuckDuckGo search failed for query: %s", query)

        return query_results


def format_search_results(results: list[SearchResult]) -> str:
    """Format selected search results as compact text for the LLM."""
    chunks: list[str] = []
    for index, result in enumerate(results, start=1):
        chunks.append(
            "\n".join(
                [
                    f"Result {index}",
                    f"Title: {result.title}",
                    f"URL: {result.url}",
                    f"Snippet: {result.snippet}",
                ]
            )
        )
    return "\n\n".join(chunks)


def _append_field_queries(queries: list[str], shop_name: str, suffixes: tuple[str, ...]) -> None:
    for suffix in suffixes:
        _append_query(queries, f'"{shop_name}" {suffix}')


def _append_query(queries: list[str], query: str) -> None:
    normalized_query = re.sub(r"\s+", " ", query.strip())
    if normalized_query:
        queries.append(normalized_query)


def _deduplicate_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(value)
    return deduplicated


def _search_result_from_ddgs_item(item: Any) -> SearchResult:
    return SearchResult(
        title=str(item.get("title", "")),
        url=str(item.get("href") or item.get("url") or ""),
        snippet=str(item.get("body") or item.get("snippet") or ""),
    )


def _normalize_field(field: str) -> str:
    normalized = field.strip().lower().replace("-", "_").replace(" ", "_")
    return _MISSING_FIELD_ALIASES.get(normalized, normalized)


def _normalize_query_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip())


def _normalize_match_text(value: str | None) -> str:
    text = _normalize_query_text(value).lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/").lower()
    if not netloc:
        return ""
    return f"{scheme}://{netloc}{path}"


def _partial_name_match(text: str, normalized_name: str) -> bool:
    tokens = [token for token in normalized_name.split() if len(token) >= 4]
    if not tokens:
        return False
    return sum(1 for token in tokens if token in text) >= max(1, min(2, len(tokens)))


def _address_fragments(address: str | None) -> list[str]:
    normalized = _normalize_match_text(address)
    if not normalized:
        return []

    fragments: list[str] = []
    for token in normalized.split():
        if len(token) < 4 or token in _ADDRESS_STOPWORDS:
            continue
        if token.isdigit():
            continue
        fragments.append(token)

    return _deduplicate_strings(fragments)


def _address_fragments_match(text: str, fragments: list[str]) -> bool:
    if len(fragments) < 2:
        return False
    matches = sum(1 for fragment in fragments if fragment in text)
    return matches >= 2


def _looks_like_generic_directory(
    title_lower: str,
    snippet_lower: str,
    url_lower: str,
) -> bool:
    combined = f"{title_lower} {snippet_lower} {url_lower}"
    return any(pattern in combined for pattern in _GENERIC_DIRECTORY_PATTERNS)


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.scheme and parsed.netloc) or "www." in value.lower()


def _looks_like_phone_only(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    letters = re.sub(r"[^A-Za-zÀ-ỹà-ỹ]", "", value)
    return len(digits) >= 8 and not letters


def _looks_like_slogan(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in _GENERIC_OR_SLOGAN_TERMS)


def _meaningful_business_tokens(value: str) -> list[str]:
    normalized = _normalize_match_text(value)
    tokens = [token for token in normalized.split() if token not in _GENERIC_BUSINESS_TERMS]
    return [token for token in tokens if len(token) >= 2]


def _log_generated_queries(queries: list[str]) -> None:
    logger.info("Generated Queries:")
    for query in queries:
        logger.info("  * %s", query)


def _log_result_scores(scored_results: list[tuple[int, SearchResult]]) -> None:
    logger.info("Result Scores:")
    for score, result in scored_results:
        logger.info("Score: %s", score)
        logger.info("Title: %s", result.title)
        logger.info("URL: %s", result.url)
        if result.snippet:
            logger.info("Snippet: %s", result.snippet)


def _log_top_results(results: list[SearchResult]) -> None:
    logger.info("Top Results Selected:")
    for result in results:
        logger.info("  * %s — %s", result.title, result.url)
