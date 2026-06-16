from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def list_images(data_dir: Path) -> list[Path]:
    if not data_dir.exists():
        logger.warning("Data directory does not exist: %s", data_dir)
        return []

    images = [
        path
        for path in data_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images, key=lambda path: path.name.lower())
