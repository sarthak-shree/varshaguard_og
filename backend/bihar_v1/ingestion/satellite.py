"""Sentinel-1 ingestion boundary for historical inundation labels and verification."""
from typing import Any


def normalize_flood_mask(payload: Any) -> dict[str, Any]:
    """Return a normalized flood-mask metadata object.

    Actual SAR processing belongs in the data pipeline, not the HTTP API layer.
    """
    if payload is None:
        return {"status": "empty"}
    if not isinstance(payload, dict):
        raise ValueError("Expected flood-mask metadata as a dictionary")
    return payload
