"""Configuration and supported geography for Bihar v1."""
import os
from pathlib import Path

SUPPORTED_DISTRICTS = {
    "patna": {"name": "Patna", "slug": "patna"},
    "muzaffarpur": {"name": "Muzaffarpur", "slug": "muzaffarpur"},
}

PREDICTION_HORIZON_HOURS = 24
UPDATE_INTERVAL_MINUTES = 60

# Repository-relative default output location for derived Bihar v1 data.
BIHAR_V1_DATA_ROOT = Path(
    os.getenv(
        "VARSHAGUARD_BIHAR_V1_DATA_ROOT",
        Path(__file__).resolve().parents[2] / "data" / "bihar_v1",
    )
)

IMD_BASE_URL = os.getenv("VARSHAGUARD_IMD_BASE_URL", "https://api.imd.gov.in/api/v1")
CWC_BASE_URL = os.getenv("VARSHAGUARD_CWC_BASE_URL", "")
IMERG_BASE_URL = os.getenv("VARSHAGUARD_IMERG_BASE_URL", "")


def district(slug: str) -> dict:
    key = slug.strip().lower()
    if key not in SUPPORTED_DISTRICTS:
        raise ValueError(f"Unsupported Bihar district: {slug}")
    return SUPPORTED_DISTRICTS[key]
