from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .enricher import ShopInfoEnricher
from .exporter import convert_csv_to_excel
from .extractor import OllamaExtractor, INFO_FIELDS
from .ocr import OCRReader, list_images
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

    _configure_runtime_paths(output_dir)

    model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    ocr_lang = os.getenv("OCR_LANG", "vi")
    max_search_results = int(os.getenv("MAX_SEARCH_RESULTS", "5"))

    logger.info("Starting storefront extraction pipeline.")
    logger.info("Data directory: %s", data_dir)
    logger.info("Excel output path: %s", output_path)
    logger.info("JSON output directory: %s", json_dir)
    logger.info("CSV output path: %s", csv_path)
    logger.info("Force reprocess: %s", force)

    images = list_images(data_dir)
    logger.info("Found %d image(s).", len(images))

    persistence = PersistenceManager(json_dir=json_dir, csv_path=csv_path)
    persistence.ensure_directories()
    persistence.rebuild_csv_from_json()

    ocr_reader = OCRReader(lang=ocr_lang)
    extractor = OllamaExtractor(model=model)
    searcher = DuckDuckGoSearcher(max_results=max_search_results)
    enricher = ShopInfoEnricher(searcher=searcher, extractor=extractor)

    processed_count = 0
    skipped_count = 0
    failed_count = 0

    for image_path in images:
        json_path = persistence.json_path_for_image(image_path)
        if json_path.exists() and not force:
            logger.info("Skipping %s because %s already exists.", image_path, json_path)
            skipped_count += 1
            continue

        stage = "startup"
        ocr_text = ""
        try:
            logger.info("Processing %s", image_path)

            stage = "ocr"
            ocr_text = ocr_reader.extract_text(image_path)

            stage = "extract"
            shop_info = extractor.extract_from_ocr(
                ocr_text=ocr_text,
                source_image=str(image_path),
            )
            extracted_fields = {
                field: getattr(shop_info, field) for field in INFO_FIELDS
            }

            stage = "enrich"
            enriched_info = enricher.enrich_if_needed(shop_info)

            persistence.save_success(
                image_path=image_path,
                ocr_text=ocr_text,
                extracted_fields=extracted_fields,
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
                ocr_text=ocr_text,
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


def _configure_runtime_paths(output_dir: Path) -> None:
    cache_dir = output_dir / ".paddlex_cache"
    temp_dir = output_dir / ".tmp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    os.environ.setdefault("TMPDIR", str(temp_dir))
