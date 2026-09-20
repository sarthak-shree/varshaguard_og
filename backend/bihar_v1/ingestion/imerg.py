"""NASA GPM IMERG ingestion boundary."""
from typing import Any


def normalize_precipitation(payload: Any) -> list[dict[str, Any]]:
    """Normalize IMERG results into timestamp/latitude/longitude/rainfall records."""
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Expected normalized IMERG records as a list")
    return payload
