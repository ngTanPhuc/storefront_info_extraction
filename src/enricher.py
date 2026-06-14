from __future__ import annotations

import logging
from typing import Any

from .extractor import OllamaExtractor
from .models import ShopInfo
from .search import DuckDuckGoSearcher, format_search_results

logger = logging.getLogger(__name__)


class ShopInfoEnricher:
    def __init__(self, searcher: DuckDuckGoSearcher, extractor: OllamaExtractor) -> None:
        self.searcher = searcher
        self.extractor = extractor

    def enrich_if_needed(self, shop_info: ShopInfo) -> ShopInfo:
        missing_fields = shop_info.missing_enrichment_fields
        if not missing_fields:
            logger.info("No enrichment needed for %s", shop_info.source_image)
            return shop_info

        logger.info(
            "Enriching %s. Missing fields: %s",
            shop_info.source_image,
            ", ".join(missing_fields),
        )
        results = self.searcher.search(shop_info.shop_name, shop_info.address)
        shop_info.search_results = results
        if not results:
            return shop_info

        extracted = self.extractor.extract_missing_from_search(
            shop_info=shop_info,
            search_results_text=format_search_results(results),
            missing_fields=missing_fields,
        )
        _merge_missing_fields(shop_info, extracted, missing_fields)
        return ShopInfo(**shop_info.model_dump())


def _merge_missing_fields(
    shop_info: ShopInfo,
    extracted: dict[str, Any],
    missing_fields: list[str],
) -> None:
    for field in missing_fields:
        value = extracted.get(field)
        if field == "website_links":
            if value:
                shop_info.website_links = value
            continue
        if value:
            setattr(shop_info, field, value)
