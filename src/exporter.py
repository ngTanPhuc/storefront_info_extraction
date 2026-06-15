from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .models import ShopInfo

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "image_name",
    "shop_name",
    "address",
    "phone_number",
    "website_links",
    "open_hours",
]


def shop_info_to_export_row(shop_info: ShopInfo) -> dict[str, Any]:
    row = shop_info.to_export_row()
    return {column: row.get(column) for column in EXPORT_COLUMNS}


def append_shop_info_to_csv(shop_info: ShopInfo, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    row = shop_info_to_export_row(shop_info)
    fieldnames = list(row)
    file_exists = csv_path.exists() and csv_path.stat().st_size > 0

    with csv_path.open("a", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def export_to_excel(records: list[ShopInfo], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [shop_info_to_export_row(record) for record in records]
    dataframe = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    dataframe.to_excel(output_path, index=False)
    logger.info("Exported %d records to %s", len(records), output_path)


def convert_csv_to_excel(csv_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.read_csv(csv_path, keep_default_na=False)
    dataframe.to_excel(output_path, index=False)
    logger.info("Exported %d CSV row(s) to %s", len(dataframe), output_path)
