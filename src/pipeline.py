from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .enricher import ShopInfoEnricher
from .exporter import convert_csv_to_excel
from .extractor import OllamaExtractor, VLM_MODEL
from .images import list_images
from .persistence import PersistenceManager
from .search import DuckDuckGoSearcher

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineSummary:
    processed: int
    skipped: int
    failed: int


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def run_pipeline(
    data_dir: Path = Path("data"),
    output_path: Path = Path("output/results.xlsx"),
    force: bool = False,
) -> PipelineSummary:
    configure_logging()

    output_dir = output_path.parent
    json_dir = output_dir / "json"
    csv_path = output_path.with_suffix(".csv")

    model = os.getenv("OLLAMA_MODEL", VLM_MODEL)
    max_search_results = int(os.getenv("MAX_SEARCH_RESULTS", "5"))

    logger.info("Starting VLM storefront extraction pipeline.")
    logger.info("Data directory: %s", data_dir)
    logger.info("Excel output path: %s", output_path)
    logger.info("JSON output directory: %s", json_dir)
    logger.info("CSV output path: %s", csv_path)
    logger.info("Ollama model: %s", model)
    logger.info("Force reprocess: %s", force)

    images = list_images(data_dir)
    logger.info("Found %d image(s).", len(images))

    persistence = PersistenceManager(json_dir=json_dir, csv_path=csv_path)
    persistence.ensure_directories()
    persistence.rebuild_csv_from_json()

    extractor = OllamaExtractor(model=model)
    searcher = DuckDuckGoSearcher(max_results=max_search_results)
    enricher = ShopInfoEnricher(searcher=searcher, extractor=extractor)

    processed_count = 0
    skipped_count = 0
    failed_count = 0

    for image_path in images:
        print("🤡", image_path)
        print("🤡", type(image_path))
        print("🤡", image_path.exists())
        print("🤡", image_path.resolve())
        json_path = persistence.json_path_for_image(image_path)
        if json_path.exists() and not force:
            logger.info("Skipping %s because %s already exists.", image_path, json_path)
            skipped_count += 1
            continue

        stage = "startup"
        try:
            logger.info("Processing %s", image_path)

            stage = "image_preparation"
            shop_info = extractor.extract_from_image(image_path)
            stage = "vlm"
            parsed_result = shop_info.business_fields()

            stage = "enrich"
            enriched_info = enricher.enrich_if_needed(shop_info)

            persistence.save_success(
                image_path=image_path,
                model=model,
                raw_response=enriched_info.raw_response,
                parsed_result=parsed_result,
                shop_info=enriched_info,
                search_queries=enriched_info.search_queries,
                enrichment_results=enriched_info.enrichment_results,
            )
            persistence.append_row(enriched_info)
            processed_count += 1
        except Exception as error:
            failed_count += 1
            logger.exception("Failed to process %s during %s.", image_path, stage)
            persistence.save_error(
                image_path=image_path,
                stage=stage,
                error=error,
            )

    persistence.rebuild_csv_from_json()
    convert_csv_to_excel(csv_path=csv_path, output_path=output_path)

    summary = PipelineSummary(
        processed=processed_count,
        skipped=skipped_count,
        failed=failed_count,
    )
    logger.info("Pipeline complete: %s", summary)
    return summary
