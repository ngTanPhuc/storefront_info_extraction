from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extractor import OllamaExtractor
from src.image_utils import prepare_image_for_vlm


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one HEIF/HEIC image for Ollama and send it to qwen2.5vl:3b."
    )
    parser.add_argument(
        "image_path",
        type=Path,
        help="Input HEIF/HEIC image path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prepared_image = prepare_image_for_vlm(args.image_path)
    print(f"Prepared image: {prepared_image}")

    extractor = OllamaExtractor(model="qwen2.5vl:3b")
    result = extractor.extract_from_image(prepared_image)
    print("Raw response:")
    print(result.raw_response)
    print("Parsed result:")
    print(result.business_fields())


if __name__ == "__main__":
    main()
