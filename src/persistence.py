from __future__ import annotations

import csv
import json
import logging
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exporter import EXPORT_COLUMNS, shop_info_to_export_row
from .models import ShopInfo

logger = logging.getLogger(__name__)


class PersistenceManager:
    def __init__(self, json_dir: Path, csv_path: Path) -> None:
        self.json_dir = json_dir
        self.csv_path = csv_path

    def ensure_directories(self) -> None:
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def json_path_for_image(self, image_path: Path) -> Path:
        return self.json_dir / f"{_safe_filename(image_path.stem)}.json"

    def has_result(self, image_path: Path) -> bool:
        return self.json_path_for_image(image_path).exists()

    def save_success(
        self,
        image_path: Path,
        model: str,
        raw_response: str,
        parsed_result: dict[str, Any],
        shop_info: ShopInfo,
        search_queries: list[str],
        enrichment_results: dict[str, Any],
    ) -> Path:
        payload = {
            "image_name": image_path.name,
            "model": model,
            "raw_response": raw_response,
            "parsed_result": parsed_result,
            "final_result": shop_info.business_fields(),
            "search_queries": search_queries,
            "search_results": [
                result.model_dump() for result in shop_info.search_results
            ],
            "enrichment_results": enrichment_results,
            "export_row": shop_info_to_export_row(shop_info),
        }
        path = self.json_path_for_image(image_path)
        _atomic_write_json(path, payload)
        logger.info("Saved debug result for %s to %s", image_path, path)
        return path

    def save_error(self, image_path: Path, stage: str, error: Exception) -> Path:
        payload = {
            "processing_status": "failed",
            "created_at": _utc_now(),
            "image_name": image_path.name,
            "source_image": str(image_path),
            "failed_stage": stage,
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        }
        path = self.json_path_for_image(image_path)
        _atomic_write_json(path, payload)
        logger.info("Saved failure record for %s to %s", image_path, path)
        return path

    def append_row(self, shop_info: ShopInfo) -> None:
        row = shop_info_to_export_row(shop_info)
        fieldnames = list(row)
        file_exists = self.csv_path.exists() and self.csv_path.stat().st_size > 0

        with self.csv_path.open("a", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def rebuild_csv_from_json(self) -> None:
        rows = [_load_export_row(path) for path in sorted(self.json_dir.glob("*.json"))]
        with self.csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=EXPORT_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column) for column in EXPORT_COLUMNS})
        logger.info("Rebuilt %s from %d JSON result(s)", self.csv_path, len(rows))


def _load_export_row(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as json_file:
        payload = json.load(json_file)

    if payload.get("processing_status") == "failed":
        return {
            "image_name": payload.get("image_name", path.stem),
            "shop_name": None,
            "address": None,
            "phone_number": None,
            "website_links": None,
            "open_hours": None,
        }

    final_result = payload.get("final_result", {})
    return {
        "image_name": payload.get("image_name", final_result.get("image_name")),
        "shop_name": final_result.get("shop_name"),
        "address": final_result.get("address"),
        "phone_number": final_result.get("phone_number"),
        "website_links": ", ".join(final_result.get("website_links", [])),
        "open_hours": final_result.get("open_hours"),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")
    temporary_path.replace(path)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "image"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
