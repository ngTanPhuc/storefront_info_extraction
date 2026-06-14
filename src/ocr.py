from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


class OCRReader:
    def __init__(self, lang: str = "en") -> None:
        from paddleocr import PaddleOCR

        logger.info("Initializing PaddleOCR with language=%s", lang)
        device = os.getenv("OCR_DEVICE", "cpu")
        cpu_threads = int(os.getenv("OCR_CPU_THREADS", "4"))
        try:
            self._reader = PaddleOCR(
                lang=lang,
                device=device,
                enable_mkldnn=False,
                cpu_threads=cpu_threads,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
            )
        except TypeError:
            self._reader = PaddleOCR(use_angle_cls=True, lang=lang)

    def extract_text(self, image_path: Path) -> str:
        logger.info("Running OCR for %s", image_path)
        image_input = _load_image_input(image_path)
        if hasattr(self._reader, "predict"):
            result = self._reader.predict(image_input)
        else:
            result = self._reader.ocr(image_input, cls=True)
        text_lines = _extract_text_lines(result)
        text = "\n".join(line for line in text_lines if line.strip())
        logger.debug("OCR text for %s: %s", image_path, text)
        return text


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


def _extract_text_lines(result: Any) -> list[str]:
    lines: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            rec_texts = node.get("rec_texts")
            if isinstance(rec_texts, list):
                for text in rec_texts:
                    if isinstance(text, str):
                        lines.append(text)
            text = node.get("text") or node.get("transcription")
            if isinstance(text, str):
                lines.append(text)
            for value in node.values():
                walk(value)
            return

        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and isinstance(node[1], (list, tuple)):
                maybe_text = node[1][0] if node[1] else None
                if isinstance(maybe_text, str):
                    lines.append(maybe_text)
                    return
            for item in node:
                walk(item)

    walk(result)
    return lines


def _load_image_input(image_path: Path) -> str | np.ndarray:
    if cv2.imread(str(image_path)) is not None:
        return str(image_path)

    try:
        import pillow_heif
    except ImportError as exc:
        raise RuntimeError(
            f"Could not read image {image_path}. It may be a HEIF/HEIC file with a "
            "non-HEIF extension. Install pillow-heif to decode it."
        ) from exc

    logger.info("Decoding HEIF/HEIC image with pillow-heif: %s", image_path)
    heif_file = pillow_heif.read_heif(image_path)
    rgb = np.asarray(heif_file.to_pillow().convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
