from __future__ import annotations

import logging

from duckduckgo_search import DDGS

from .models import SearchResult

logger = logging.getLogger(__name__)


class DuckDuckGoSearcher:
    def __init__(self, max_results: int = 5) -> None:
        self.max_results = max_results
        self.last_queries: list[str] = []

    def search(self, shop_name: str | None, address: str | None) -> list[SearchResult]:
        query = " ".join(part for part in [shop_name, address] if part).strip()
        if not query:
            logger.warning("Skipping search because shop_name and address are missing.")
            return []

        self.last_queries = [query]
        logger.info("Searching DuckDuckGo for: %s", query)
        results: list[SearchResult] = []
        try:
            with DDGS() as ddgs:
                for item in ddgs.text(query, max_results=self.max_results):
                    results.append(
                        SearchResult(
                            title=str(item.get("title", "")),
                            url=str(item.get("href") or item.get("url") or ""),
                            snippet=str(item.get("body") or item.get("snippet") or ""),
                        )
                    )
        except Exception:
            logger.exception("DuckDuckGo search failed for query: %s", query)
            return []

        return results


def format_search_results(results: list[SearchResult]) -> str:
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
