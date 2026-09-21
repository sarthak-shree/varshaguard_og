"""CLI for auditing Bihar v1 raw-source acquisition readiness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data_contract import build_source_manifest, validate_contract, validate_source_manifest


SOURCE_ARGS = (
    "hourly_rainfall",
    "river_level",
    "river_threshold",
    "flood_events",
    "district_boundaries",
    "sentinel1_inundation",
    "dem",
)


def audit_sources(paths: dict[str, str | Path | None]) -> dict:
    """Return contract and provenance state without modifying source files."""
    manifest = build_source_manifest(paths)
    return {
        "data_acquisition_contract": validate_contract(paths),
        "raw_source_manifest": manifest,
        "raw_source_manifest_validation": validate_source_manifest(manifest),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Bihar v1 raw data sources.")
    for name in SOURCE_ARGS:
        parser.add_argument(f"--{name.replace('_', '-')}")
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    paths = {name: getattr(args, name) for name in SOURCE_ARGS}
    report = audit_sources(paths)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
