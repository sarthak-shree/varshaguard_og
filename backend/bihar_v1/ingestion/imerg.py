"""NASA GPM IMERG ingestion boundary.

The parser accepts provider-neutral records after an external download step. It does
not claim to implement an undocumented NASA download endpoint.
"""
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {"timestamp", "latitude", "longitude", "rainfall_mm"}


def normalize_precipitation(payload: Any) -> list[dict[str, Any]]:
    """Validate and normalize IMERG precipitation records."""
    if payload is None:
        return []
    if isinstance(payload, pd.DataFrame):
        frame = payload.copy()
    elif isinstance(payload, list):
        frame = pd.DataFrame(payload)
    else:
        raise ValueError("Expected IMERG records as a list or DataFrame")

    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing IMERG columns: {sorted(missing)}")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if frame["timestamp"].isna().any():
        raise ValueError("IMERG payload contains invalid timestamps")

    for column in ("latitude", "longitude", "rainfall_mm"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise ValueError(f"IMERG payload contains invalid {column} values")

    frame = frame.sort_values(["timestamp", "latitude", "longitude"]).reset_index(drop=True)
    return frame.to_dict(orient="records")
