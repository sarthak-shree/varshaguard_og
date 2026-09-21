"""Bihar v1 historical data-acquisition contract and validation helpers.

The contract is intentionally stricter than the current dataset. It describes what
must exist before a district/model is allowed to move from blocked to trainable.
It does not fabricate missing sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceRequirement:
    name: str
    required: bool
    temporal_granularity: str
    required_columns: tuple[str, ...]
    purpose: str


SOURCE_REQUIREMENTS: tuple[SourceRequirement, ...] = (
    SourceRequirement(
        "hourly_rainfall",
        True,
        "hourly",
        ("Data Acquisition Time", "District", "Station", "Telemetry Hourly Rainfall (mm)"),
        "Predict heavy rainfall and provide precipitation forcing for flood prediction.",
    ),
    SourceRequirement(
        "river_level",
        True,
        "hourly_or_better",
        ("Data Acquisition Time", "District", "Station", "River Water Level Telemetry Hourly (meter)"),
        "Predict river-threshold exceedance within the 24-hour horizon.",
    ),
    SourceRequirement(
        "river_threshold",
        True,
        "static_or_versioned",
        ("Station", "Danger Level"),
        "Define the official station-specific river danger threshold; values must not be invented.",
    ),
    SourceRequirement(
        "flood_events",
        True,
        "event",
        ("Start Date", "End Date", "Bihar District"),
        "Provide independent historical flood-event labels.",
    ),
    SourceRequirement(
        "sentinel1_inundation",
        True,
        "event_or_scene",
        ("scene_timestamp", "district", "mask_path"),
        "Provide historical spatial inundation labels.",
    ),
    SourceRequirement(
        "dem",
        True,
        "static",
        ("elevation_path",),
        "Provide static terrain/elevation features for spatial inundation modeling.",
    ),
)


DISTRICT_REQUIRED_SOURCES = {
    "patna": tuple(item.name for item in SOURCE_REQUIREMENTS),
    "muzaffarpur": tuple(item.name for item in SOURCE_REQUIREMENTS),
}


def source_contract(name: str) -> SourceRequirement:
    for requirement in SOURCE_REQUIREMENTS:
        if requirement.name == name:
            return requirement
    raise ValueError(f"Unknown Bihar v1 source: {name}")


def validate_source_file(path: str | Path, source_name: str) -> dict:
    """Validate only the structural contract of one local source file."""
    path = Path(path)
    requirement = source_contract(source_name)
    result = {
        "source": source_name,
        "path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "missing_columns": [],
    }
    if not path.exists():
        return result

    if path.suffix.lower() != ".csv":
        result["status"] = "present_non_csv"
        return result

    import pandas as pd

    frame = pd.read_csv(path, nrows=0)
    missing = sorted(set(requirement.required_columns) - set(frame.columns))
    result["missing_columns"] = missing
    result["status"] = "ready" if not missing else "invalid_schema"
    return result


def validate_contract(paths: dict[str, str | Path]) -> dict:
    """Validate the required source inventory without modifying any source."""
    results = {}
    blockers = []
    for requirement in SOURCE_REQUIREMENTS:
        result = validate_source_file(paths.get(requirement.name, ""), requirement.name)
        results[requirement.name] = result
        if requirement.required and result["status"] != "ready":
            blockers.append(
                f"{requirement.name}: {result['status']}"
                + (
                    f" (missing columns: {', '.join(result['missing_columns'])})"
                    if result["missing_columns"]
                    else ""
                )
            )
    return {
        "status": "ready" if not blockers else "blocked",
        "required_sources": list(results),
        "sources": results,
        "blockers": blockers,
    }
