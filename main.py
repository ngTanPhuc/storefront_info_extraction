from __future__ import annotations

import argparse
from pathlib import Path

from src.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract storefront business information from images."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Directory containing storefront images.",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path("output/results.xlsx"),
        help="Final Excel output path.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess images even when output/json/<image>.json already exists.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(data_dir=args.data_dir, output_path=args.output_path, force=args.force)
