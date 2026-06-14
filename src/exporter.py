from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .models import ShopInfo

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "source_image",
    "shop_name",
    "address",
    "phone_number",
    "website_links",
    "open_hours",
    "ocr_text",
    "search_results",
]


def export_to_excel(records: list[ShopInfo], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [record.to_export_row() for record in records]
    dataframe = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    dataframe.to_excel(output_path, index=False)
    logger.info("Exported %d records to %s", len(records), output_path)
