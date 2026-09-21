"""Verified external source catalog for Bihar v1 acquisition.

This catalog records access facts; it never marks a source as locally available.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AcquisitionSource:
    name: str
    provider: str
    purpose: str
    temporal_resolution: str
    spatial_resolution: str
    access_url: str
    registration_required: bool
    local_contract_name: str


ACQUISITION_SOURCES = (
    AcquisitionSource(
        "imerg_early",
        "NASA GPM",
        "Near-real-time precipitation forcing and historical precipitation augmentation.",
        "30 minute / 3 hour / 1 day",
        "0.1 degree / 10 km",
        "https://gpm.nasa.gov/data/directory/imerg-early-run-pps-near-real-time-gis",
        True,
        "hourly_rainfall",
    ),
    AcquisitionSource(
        "imd_api",
        "India Meteorological Department",
        "Official Indian weather observations, forecasts and warnings.",
        "Provider-dependent",
        "Provider-dependent",
        "https://api.imd.gov.in/public/index.php",
        True,
        "hourly_rainfall",
    ),
)


def list_acquisition_sources() -> list[dict]:
    """Return acquisition metadata without claiming local availability."""
    return [asdict(source) for source in ACQUISITION_SOURCES]


def acquisition_source(name: str) -> AcquisitionSource:
    for source in ACQUISITION_SOURCES:
        if source.name == name:
            return source
    raise ValueError(f"Unknown acquisition source: {name}")
