"""Assemble source CSVs into auditable Bihar v1 training datasets."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from .data_pipeline import ensure_data_dirs, observations_to_frame
from .ingestion.normalizers import normalize_rainfall_csv, normalize_river_csv
from .labeling import build_24h_event_labels, load_district_events
from .splitting import (
    chronological_split,
    enforce_event_isolation,
    split_summary,
    validate_split_readiness,
)
from .station_registry import stations_for_district
from .training_table import build_training_table, summarize_target

DISTRICTS = ("patna", "muzaffarpur")


def _norm_station(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _station_aliases(district: str, variable: str, granularity: str) -> set[str]:
    supported = stations_for_district(district)
    names = supported.get(variable if variable == "river" else f"rainfall_{granularity}", set())
    aliases = {_norm_station(x) for x in names}
    if district == "patna" and variable == "rainfall" and granularity == "daily":
        aliases.update({_norm_station("Gandhi Ghat"), _norm_station("Gandhighat")})
    if district == "muzaffarpur" and variable == "rainfall" and granularity == "daily":
        aliases.update({
            _norm_station("Sikandarpur"),
            _norm_station("Sikandarpur (Muzzafarpur)"),
            _norm_station("Sikandarpur (Muzaffarpur)"),
        })
    return aliases


def _read_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _normalize_source(
    path: str | Path,
    *,
    variable: str,
    value_column: str,
    districts: tuple[str, ...] = DISTRICTS,
    granularity: str = "hourly",
) -> pd.DataFrame:
    raw = _read_csv(path)
    if variable == "rainfall":
        observations = normalize_rainfall_csv(raw, value_column=value_column)
    elif variable == "river":
        observations = normalize_river_csv(raw, value_column=value_column)
    else:
        raise ValueError(f"Unsupported variable: {variable}")

    normalized = observations_to_frame(observations)
    if normalized.empty:
        return normalized

    normalized["_station_key"] = normalized["station_id"].map(_norm_station)
    selected = []
    for district in districts:
        aliases = _station_aliases(district, variable, granularity)
        if not aliases:
            continue
        part = normalized[
            (normalized["district"] == district)
            & normalized["_station_key"].isin(aliases)
        ].copy()
        if not part.empty:
            selected.append(part)
    if not selected:
        return normalized.iloc[0:0].copy()
    return pd.concat(selected, ignore_index=True).drop(columns="_station_key")


def _audit_observations(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"rows": 0, "districts": [], "stations": [], "start": None, "end": None}
    ts = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    valid = ts.dropna().sort_values()
    if valid.empty:
        return {"rows": int(len(frame)), "districts": [], "stations": [], "start": None, "end": None}
    gaps = valid.diff().dropna().dt.total_seconds().div(3600)
    gap_values = gaps[gaps > 1.0]
    return {
        "rows": int(len(frame)),
        "districts": sorted(frame["district"].dropna().unique().tolist()),
        "stations": sorted(frame["station_id"].dropna().astype(str).unique().tolist()),
        "start": valid.min().isoformat(),
        "end": valid.max().isoformat(),
        "median_interval_hours": float(gaps.median()) if not gaps.empty else None,
        "max_interval_hours": float(gaps.max()) if not gaps.empty else None,
        "gaps_over_1h": int(len(gap_values)),
        "duplicate_timestamps": int(ts.duplicated().sum()),
        "coverage_hours": float((valid.max() - valid.min()).total_seconds() / 3600),
    }


def _empty_training_summary(reason: str) -> dict:
    return {
        "status": "not_trainable",
        "reason": reason,
        "training": {"rows": 0, "positive": 0, "negative": 0, "positive_rate": 0.0, "positive_events": 0},
        "split_summary": {},
        "readiness": {"ready_for_model_evaluation": False, "splits": {}},
    }



def _readiness_blockers(district: str, sources: dict[str, pd.DataFrame], event_frame: pd.DataFrame, district_result: dict) -> dict:
    """Return explicit blockers without implying that missing data can be synthesized."""
    hourly = sources.get("rainfall_hourly", pd.DataFrame())
    river = sources.get("river", pd.DataFrame())
    district_hourly = hourly[hourly["district"] == district] if not hourly.empty else hourly
    district_river = river[river["district"] == district] if not river.empty else river
    district_events = event_frame[event_frame["district"] == district] if not event_frame.empty else event_frame

    blockers = {
        "heavy_rainfall": [],
        "river_flood": [],
        "inundation": [
            "No Sentinel-1 inundation masks are included in the current assembler inputs.",
            "No static terrain/DEM feature set is included in the current assembler inputs.",
        ],
    }
    if district_hourly.empty:
        blockers["heavy_rainfall"].append("No supported hourly rainfall observations are available for this district.")
    if district_river.empty:
        blockers["river_flood"].append("No supported river-level observations are available for this district.")
    if district_events.empty:
        blockers["river_flood"].append("No flood-event inventory records are available for this district.")
    if district_result.get("readiness", {}).get("ready_for_model_evaluation") is not True:
        reason = district_result.get("readiness", {}).get("reason")
        if reason:
            blockers["river_flood"].append(str(reason))

    return {model: {"status": "blocked" if reasons else "not_blocked", "reasons": reasons} for model, reasons in blockers.items()}


def _assemble_district(
    district: str,
    sources: dict[str, pd.DataFrame],
    event_frame: pd.DataFrame,
    output_dir: Path,
) -> dict:
    hourly_rain = sources.get("rainfall_hourly", pd.DataFrame())
    river = sources.get("river", pd.DataFrame())
    parts = [
        frame[frame["district"] == district].copy()
        for frame in (hourly_rain, river)
        if not frame.empty
    ]
    observations = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    if observations.empty:
        return _empty_training_summary(
            "No supported hourly rainfall or river observations for this district."
        )

    timestamps = pd.Series(
        pd.to_datetime(observations["timestamp"], utc=True).drop_duplicates()
    )
    labels = build_24h_event_labels(timestamps, event_frame, district=district)
    table = build_training_table(observations, labels, district=district)
    target = summarize_target(table)

    table_path = output_dir / f"{district}_flood_training.csv"
    table.to_csv(table_path, index=False)

    # Small/synthetic tables must produce an auditable "not ready" result,
    # not crash the entire dataset assembly job.
    if table["timestamp"].nunique() < 3:
        raw_splits = {
            "train": table.iloc[0:0].copy(),
            "validation": table.iloc[0:0].copy(),
            "test": table.iloc[0:0].copy(),
        }
        pre_isolation_summary = split_summary(raw_splits)
        splits = enforce_event_isolation(raw_splits)
        split_info = split_summary(splits)
        readiness = validate_split_readiness(splits)
        split_reason = "Fewer than 3 unique timestamps remain after feature/label filtering."
    else:
        raw_splits = chronological_split(table)
        pre_isolation_summary = split_summary(raw_splits)
        splits = enforce_event_isolation(raw_splits)
        split_info = split_summary(splits)
        readiness = validate_split_readiness(splits)
        split_reason = None

    split_dir = output_dir / district
    split_dir.mkdir(parents=True, exist_ok=True)
    for split_name, split_frame in splits.items():
        split_frame.to_csv(split_dir / f"{split_name}.csv", index=False)

    pre_rows = sum(item["rows"] for item in pre_isolation_summary.values())
    post_rows = sum(item["rows"] for item in split_info.values())
    pre_events = sum(item["positive_events"] for item in pre_isolation_summary.values())
    post_events = sum(item["positive_events"] for item in split_info.values())

    status = "trainable" if target["positive"] > 0 and target["negative"] > 0 else "not_trainable"
    if not readiness["ready_for_model_evaluation"]:
        status = "not_evaluation_ready"

    return {
        "status": status,
        "reason": split_reason,
        "training": target,
        "observation_coverage": _audit_observations(observations),
        "label_positive_timestamps": int(labels["flood_event_start_next_24h"].sum()),
        "ongoing_timestamps_excluded": int(labels["flood_event_ongoing"].sum()),
        "pre_isolation_split_summary": pre_isolation_summary,
        "split_summary": split_info,
        "event_isolation_removed": {
            "rows": int(pre_rows - post_rows),
            "positive_rows": int(
                sum(item["positive"] for item in pre_isolation_summary.values())
                - sum(item["positive"] for item in split_info.values())
            ),
            "positive_event_assignments": int(pre_events - post_events),
        },
        "readiness": readiness,
        "training_table": str(table_path),
        "split_files": {
            name: str(split_dir / f"{name}.csv") for name in splits
        },
    }


def assemble(
    *,
    hourly_rainfall: str | Path | None = None,
    daily_rainfall: str | Path | None = None,
    river: str | Path | None = None,
    events: str | Path | None = None,
    rainfall_hourly_value_column: str = "Telemetry Hourly Rainfall (mm)",
    rainfall_daily_value_column: str = "Manual Rainfall (mm)",
    river_value_column: str = "River Water Level Telemetry Hourly (meter)",
    output_root: str | Path | None = None,
) -> dict:
    if not events:
        raise ValueError("A flood-event inventory is required for supervised training.")

    paths = ensure_data_dirs(Path(output_root) if output_root else None)
    event_frame = load_district_events(events)

    sources: dict[str, pd.DataFrame] = {}
    if hourly_rainfall:
        sources["rainfall_hourly"] = _normalize_source(
            hourly_rainfall, variable="rainfall",
            value_column=rainfall_hourly_value_column, granularity="hourly",
        )
    if daily_rainfall:
        sources["rainfall_daily"] = _normalize_source(
            daily_rainfall, variable="rainfall",
            value_column=rainfall_daily_value_column, granularity="daily",
        )
    if river:
        sources["river"] = _normalize_source(
            river, variable="river",
            value_column=river_value_column, granularity="river",
        )

    for name, frame in sources.items():
        frame.to_csv(paths["processed"] / f"{name}_supported.csv", index=False)

    report: dict = {
        "districts": {},
        "sources": {name: _audit_observations(frame) for name, frame in sources.items()},
        "source_coverage_matrix": {district: {"rainfall_hourly_rows": int((sources.get("rainfall_hourly", pd.DataFrame()).get("district", pd.Series(dtype=str)) == district).sum()), "river_rows": int((sources.get("river", pd.DataFrame()).get("district", pd.Series(dtype=str)) == district).sum()), "event_rows": int((event_frame["district"] == district).sum())} for district in DISTRICTS},
        "notes": [
            "Daily rainfall is retained as processed evidence but is not upsampled into hourly training rows.",
            "Only stations explicitly listed in station_registry.py are included.",
            "A supervised training table requires a flood-event inventory; no labels are fabricated when the inventory is unavailable.",
            "Evaluation readiness requires independent flood events in each chronological split.",
        ],
    }

    for district in DISTRICTS:
        result = _assemble_district(district, sources, event_frame, paths["training"])
        result["readiness_blockers"] = _readiness_blockers(district, sources, event_frame, result)
        report["districts"][district] = result

    report_path = paths["processed"] / "dataset_audit.json"
    report["event_inventory"] = {
        "rows": int(len(event_frame)),
        "districts": sorted(event_frame["district"].dropna().unique().tolist()),
        "start": event_frame["start"].min().isoformat() if not event_frame.empty else None,
        "end": event_frame["end"].max().isoformat() if not event_frame.empty else None,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble auditable Bihar v1 datasets.")
    parser.add_argument("--events", required=True)
    parser.add_argument("--hourly-rainfall")
    parser.add_argument("--daily-rainfall")
    parser.add_argument("--river")
    parser.add_argument("--output-root")
    parser.add_argument("--rainfall-hourly-value-column", default="Telemetry Hourly Rainfall (mm)")
    parser.add_argument("--rainfall-daily-value-column", default="Manual Rainfall (mm)")
    parser.add_argument("--river-value-column", default="River Water Level Telemetry Hourly (meter)")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = assemble(
        hourly_rainfall=args.hourly_rainfall,
        daily_rainfall=args.daily_rainfall,
        river=args.river,
        events=args.events,
        rainfall_hourly_value_column=args.rainfall_hourly_value_column,
        rainfall_daily_value_column=args.rainfall_daily_value_column,
        river_value_column=args.river_value_column,
        output_root=args.output_root,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
