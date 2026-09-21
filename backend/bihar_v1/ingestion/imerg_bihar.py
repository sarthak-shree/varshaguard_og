"""Bihar-specific IMERG spatial ingestion.

This adapter requires authoritative district polygons before assigning precipitation
cells to Patna or Muzaffarpur. It never falls back to coordinate proximity.
"""
from typing import Any, Iterable

from .imerg import normalize_precipitation, precipitation_to_observations
from ..spatial_mapping import assign_districts


def bihar_precipitation_to_observations(
    records: list[dict[str, Any]],
    district_features: Iterable[dict],
):
    """Normalize, spatially assign, and convert IMERG records for Bihar."""
    normalized = normalize_precipitation(records)
    assigned = assign_districts(normalized, district_features)
    # Never emit an observation with an unknown district into the Bihar training/inference path.
    assigned = [record for record in assigned if record.get("district")]
    return precipitation_to_observations(assigned)
