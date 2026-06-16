from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Final

from PIL import Image
from pillow_heif import register_heif_opener

logger = logging.getLogger(__name__)

SUPPORTED_VLM_EXTENSIONS: Final[set[str]] = {".png", ".jpg", ".jpeg", ".webp"}
HEIF_EXTENSIONS: Final[set[str]] = {".heif", ".heic"}
DEFAULT_CONVERTED_IMAGES_DIR: Final[Path] = Path("output/converted_images")


class ImagePreparationError(RuntimeError):
    """Raised when an image cannot be prepared for the VLM."""


def is_supported_vlm_image(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_VLM_EXTENSIONS


def prepare_image_for_vlm(
    image_path: Path,
    output_dir: Path = DEFAULT_CONVERTED_IMAGES_DIR,
) -> Path:
    if not image_path.exists():
        raise ImagePreparationError(f"Image does not exist: {image_path}")

    if is_supported_vlm_image(image_path) and not _looks_like_heif(image_path):
        logger.info("Image ready for VLM: %s", image_path)
        return image_path

    if _is_heif_image(image_path):
        return _convert_heif_to_png(image_path=image_path, output_dir=output_dir)

    raise ImagePreparationError(
        f"Unsupported image format for VLM: {image_path.suffix or '<none>'}"
    )


def validate_prepared_image(image_path: Path) -> None:
    if not image_path.exists():
        raise ImagePreparationError(f"Prepared image does not exist: {image_path}")
    if image_path.stat().st_size <= 0:
        raise ImagePreparationError(f"Prepared image is empty: {image_path}")


def _is_heif_image(image_path: Path) -> bool:
    return image_path.suffix.lower() in HEIF_EXTENSIONS or _looks_like_heif(image_path)


def _looks_like_heif(image_path: Path) -> bool:
    heif_brands = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}
    try:
        with image_path.open("rb") as image_file:
            header = image_file.read(32)
    except OSError:
        return False

    if len(header) < 12 or header[4:8] != b"ftyp":
        return False

    major_brand = header[8:12]
    compatible_brands = {header[index : index + 4] for index in range(12, len(header) - 3, 4)}
    return major_brand in heif_brands or bool(compatible_brands & heif_brands)


def _convert_heif_to_png(image_path: Path, output_dir: Path) -> Path:
    output_path = output_dir / f"{_safe_filename(image_path.stem)}.png"
    temporary_path = output_path.with_suffix(".png.tmp")

    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info("Using cached converted image: %s", output_path)
        logger.info("Image ready for VLM: %s", output_path)
        return output_path

    logger.info("Converting HEIF image to PNG: %s", image_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    register_heif_opener()

    try:
        with Image.open(image_path) as image:
            rgb_image = image.convert("RGB")
            rgb_image.save(
                temporary_path,
                format="PNG",
                optimize=True,
                compress_level=3,
            )
    except Exception as error:
        _remove_if_exists(temporary_path)
        raise ImagePreparationError(
            f"Failed to convert HEIF image to PNG: {image_path}"
        ) from error

    try:
        validate_prepared_image(temporary_path)
        temporary_path.replace(output_path)
    except ImagePreparationError:
        _remove_if_exists(temporary_path)
        raise

    logger.info("Image ready for VLM: %s", output_path)
    return output_path


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "image"


def _remove_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logger.exception("Failed to remove temporary image: %s", path)
