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
    AcquisitionSource(
        "cwc_floodwatch",
        "Central Water Commission",
        "River observations and flood forecasting reference data; station danger thresholds must be obtained from authoritative station records.",
        "Provider-dependent",
        "Station-based",
        "https://ffs.india-water.gov.in/",
        True,
        "river_level",
    ),
    AcquisitionSource(
        "district_boundary_nwic",
        "National Water Data Portal / Geological Survey of India",
        "Administrative district polygons for spatially assigning gridded precipitation and inundation data.",
        "Versioned static",
        "District polygons",
        "https://www.nwdp.nwic.gov.in/dataset/district-boundary",
        False,
        "district_boundaries",
    ),
    AcquisitionSource(
        "sentinel1_copernicus",
        "Copernicus Data Space Ecosystem",
        "Historical SAR scenes for deriving inundation masks; not used as a direct future 24-hour predictor.",
        "Scene-dependent",
        "Radar scene footprint",
        "https://dataspace.copernicus.eu/",
        True,
        "sentinel1_inundation",
    ),
    AcquisitionSource(
        "srtm_1arcsec",
        "USGS / NASA",
        "Static elevation terrain features for spatial inundation modeling.",
        "Static",
        "1 arc-second (~30 m)",
        "https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm-1",
        True,
        "dem",
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
