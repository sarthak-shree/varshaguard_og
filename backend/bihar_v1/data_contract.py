"""Bihar v1 historical data-acquisition contract and validation helpers.

The contract is intentionally stricter than the current dataset. It describes what
must exist before a district/model is allowed to move from blocked to trainable.
It does not fabricate missing sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from datetime import datetime, timezone
import hashlib


@dataclass(frozen=True)
class SourceRequirement:
    name: str
    required: bool
    temporal_granularity: str
    required_columns: tuple[str, ...]
    purpose: str
    format: str = "csv"


SOURCE_REQUIREMENTS: tuple[SourceRequirement, ...] = (
    SourceRequirement(
        "hourly_rainfall", True, "hourly",
        ("Data Acquisition Time", "District", "Station", "Telemetry Hourly Rainfall (mm)"),
        "Predict heavy rainfall and provide precipitation forcing for flood prediction.",
    ),
    SourceRequirement(
        "river_level", True, "hourly_or_better",
        ("Data Acquisition Time", "District", "Station", "River Water Level Telemetry Hourly (meter)"),
        "Predict river-threshold exceedance within the 24-hour horizon.",
    ),
    SourceRequirement(
        "river_threshold", True, "static_or_versioned",
        ("Station", "Danger Level"),
        "Define the official station-specific river danger threshold; values must not be invented.",
    ),
    SourceRequirement(
        "flood_events", True, "event",
        ("Start Date", "End Date", "Bihar District"),
        "Provide independent historical flood-event labels.",
    ),
    SourceRequirement(
        "sentinel1_inundation", True, "event_or_scene",
        ("scene_timestamp", "district", "mask_path"),
        "Provide historical spatial inundation labels.",
        "manifest",
    ),
    SourceRequirement(
        "dem", True, "static",
        ("elevation_path",),
        "Provide static terrain/elevation features for spatial inundation modeling.",
        "manifest",
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


def validate_source_file(path: str | Path | None, source_name: str) -> dict:
    """Validate the structural contract of one local source."""
    requirement = source_contract(source_name)
    raw_path = str(path or "").strip()
    result = {
        "source": source_name,
        "path": raw_path,
        "exists": False,
        "status": "missing",
        "missing_columns": [],
    }
    if not raw_path:
        return result

    file_path = Path(raw_path)
    result["exists"] = file_path.exists()
    if not file_path.exists():
        return result

    if requirement.format != "csv":
        result["status"] = "present"
        return result

    if file_path.suffix.lower() != ".csv":
        result["status"] = "invalid_format"
        return result

    import pandas as pd

    frame = pd.read_csv(file_path, nrows=0)
    missing = sorted(set(requirement.required_columns) - set(frame.columns))
    result["missing_columns"] = missing
    result["status"] = "ready" if not missing else "invalid_schema"
    return result


def build_source_manifest(paths: dict[str, str | Path | None]) -> dict:
    """Create a reproducible manifest of the currently supplied raw sources."""
    sources = {}
    for requirement in SOURCE_REQUIREMENTS:
        raw = str(paths.get(requirement.name) or "").strip()
        item = {"path": raw, "status": "missing", "sha256": None, "size_bytes": None}
        if raw:
            path = Path(raw)
            if path.is_file():
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                item.update({"status": "present", "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size})
        sources[requirement.name] = item
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
    }


def write_source_manifest(paths: dict[str, str | Path | None], output: str | Path) -> dict:
    """Write a deterministic source inventory manifest with file hashes."""
    manifest = build_source_manifest(paths)
    Path(output).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

def validate_source_manifest(manifest: dict, *, require_existing_files: bool = True) -> dict:
    """Verify manifest structure and recorded file checksums."""
    errors = []
    if manifest.get("schema_version") != 1:
        errors.append("unsupported_schema_version")
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        return {"status": "invalid", "errors": errors + ["sources_missing_or_invalid"]}
    for requirement in SOURCE_REQUIREMENTS:
        item = sources.get(requirement.name)
        if not isinstance(item, dict):
            errors.append(f"{requirement.name}:entry_missing")
            continue
        if item.get("status") != "present":
            continue
        path = Path(str(item.get("path") or ""))
        if require_existing_files and not path.is_file():
            errors.append(f"{requirement.name}:file_missing")
            continue
        if path.is_file() and item.get("sha256"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != item["sha256"]:
                errors.append(f"{requirement.name}:sha256_mismatch")
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def validate_contract(paths: dict[str, str | Path]) -> dict:
    """Validate the required source inventory without modifying any source."""
    results = {}
    blockers = []
    for requirement in SOURCE_REQUIREMENTS:
        result = validate_source_file(paths.get(requirement.name), requirement.name)
        results[requirement.name] = result
        if requirement.required and result["status"] != "ready" and result["status"] != "present":
            detail = (
                f" (missing columns: {', '.join(result['missing_columns'])})"
                if result["missing_columns"] else ""
            )
            blockers.append(f"{requirement.name}: {result['status']}{detail}")
    return {
        "status": "ready" if not blockers else "blocked",
        "required_sources": list(results),
        "sources": results,
        "blockers": blockers,
    }
