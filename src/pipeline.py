from __future__ import annotations

import logging
import os
from pathlib import Path

from .enricher import ShopInfoEnricher
from .exporter import export_to_excel
from .extractor import OllamaExtractor
from .models import ShopInfo
from .ocr import OCRReader, list_images
from .search import DuckDuckGoSearcher

logger = logging.getLogger(__name__)


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
) -> list[ShopInfo]:
    configure_logging()

    _configure_runtime_paths(output_path.parent)

    model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    ocr_lang = os.getenv("OCR_LANG", "vi")
    max_search_results = int(os.getenv("MAX_SEARCH_RESULTS", "5"))

    logger.info("Starting storefront extraction pipeline.")
    logger.info("Data directory: %s", data_dir)
    logger.info("Output path: %s", output_path)

    images = list_images(data_dir)
    logger.info("Found %d image(s).", len(images))

    ocr_reader = OCRReader(lang=ocr_lang)
    extractor = OllamaExtractor(model=model)
    searcher = DuckDuckGoSearcher(max_results=max_search_results)
    enricher = ShopInfoEnricher(searcher=searcher, extractor=extractor)

    records: list[ShopInfo] = []
    for image_path in images:
        try:
            logger.info("Processing %s", image_path)
            ocr_text = ocr_reader.extract_text(image_path)
            shop_info = extractor.extract_from_ocr(
                ocr_text=ocr_text,
                source_image=str(image_path),
            )
            records.append(enricher.enrich_if_needed(shop_info))
        except Exception:
            logger.exception("Failed to process %s", image_path)

    export_to_excel(records, output_path)
    logger.info("Pipeline complete.")
    return records


def _configure_runtime_paths(output_dir: Path) -> None:
    cache_dir = output_dir / ".paddlex_cache"
    temp_dir = output_dir / ".tmp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    os.environ.setdefault("TMPDIR", str(temp_dir))
