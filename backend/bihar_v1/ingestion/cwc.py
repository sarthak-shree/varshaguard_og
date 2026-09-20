"""CWC ingestion boundary.

No undocumented endpoint is hard-coded here. Provider integration is deliberately isolated
until the production CWC feed/access method is verified.
"""
from typing import Any


def normalize_river_observation(payload: Any) -> list[dict[str, Any]]:
    """Normalize a verified CWC payload into internal observation records.

    The exact CWC response schema must be supplied before this parser is implemented.
    """
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Expected a verified CWC observation payload as a list")
    return payload
