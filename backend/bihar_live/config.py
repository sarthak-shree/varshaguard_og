"""Bihar Live / JalDrishti configuration boundary."""
from __future__ import annotations
import os
from pathlib import Path

DATA_MODE = os.getenv("JALDRISHTI_DATA_MODE", "synthetic").strip().lower()
if DATA_MODE not in {"synthetic", "real"}:
    raise ValueError("JALDRISHTI_DATA_MODE must be 'synthetic' or 'real'")

SUPPORTED_DISTRICTS = {
    "patna": {"name": "Patna", "slug": "patna"},
    "muzaffarpur": {"name": "Muzaffarpur", "slug": "muzaffarpur"},
}

DATA_ROOT = Path(os.getenv("JALDRISHTI_DATA_ROOT", Path(__file__).resolve().parents[2] / "data" / "bihar_live"))
SYNTHETIC_ROOT = DATA_ROOT / "synthetic"
REAL_ROOT = DATA_ROOT / "real"
PREDICTION_HORIZON_HOURS = 72
UPDATE_INTERVAL_MINUTES = int(os.getenv("JALDRISHTI_UPDATE_INTERVAL_MINUTES", "15"))
GRID_RESOLUTION_DEGREES = float(os.getenv("JALDRISHTI_GRID_RESOLUTION_DEGREES", "0.05"))

def data_root() -> Path:
    return SYNTHETIC_ROOT if DATA_MODE == "synthetic" else REAL_ROOT

def district(slug: str) -> dict:
    key = slug.strip().lower()
    if key not in SUPPORTED_DISTRICTS:
        raise ValueError(f"Unsupported Bihar district: {slug}")
    return SUPPORTED_DISTRICTS[key]
