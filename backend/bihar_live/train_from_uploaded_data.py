"""Import the user-supplied Bihar datasets into the repository and train the Bihar model.

This script is meant for a repository environment where the uploaded source files
are copied to the paths supplied through environment variables. It keeps source
files outside Git by default and writes only derived, reproducible artifacts.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from bihar_historical_train import build_training_table
from bihar_historical_model import train_and_compare

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "data" / "bihar"


def copy_source(src: Path, name: str) -> Path:
    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {src}")
    TARGET.mkdir(parents=True, exist_ok=True)
    dst = TARGET / name
    shutil.copy2(src, dst)
    return dst


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telemetry-2021-2025", required=True, type=Path)
    parser.add_argument("--telemetry-2026-2030", required=True, type=Path)
    parser.add_argument("--telemetry-1991-2020", required=True, type=Path)
    parser.add_argument("--telemetry-1961-1990", required=True, type=Path)
    parser.add_argument("--flood-inventory", required=True, type=Path)
    args = parser.parse_args()

    copy_source(args.telemetry_2021_2025, "telemetry_2021_2025.csv")
    copy_source(args.telemetry_2026_2030, "telemetry_2026_2030.csv")
    copy_source(args.telemetry_1991_2020, "telemetry_1991_2020.csv")
    copy_source(args.telemetry_1961_1990, "telemetry_1961_1990.csv")
    copy_source(args.flood_inventory, "Bihar_flood_inventory.zip")

    print(build_training_table().describe(include="all"))
    print(train_and_compare())


if __name__ == "__main__":
    main()
