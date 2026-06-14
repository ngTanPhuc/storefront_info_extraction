from pathlib import Path

from src.pipeline import run_pipeline


if __name__ == "__main__":
    run_pipeline(data_dir=Path("data"), output_path=Path("output/results.xlsx"))
