"""Assemble source CSVs into auditable Bihar v1 training datasets.

This module is intentionally local/offline: raw source files stay outside GitHub.
It filters only stations explicitly supported by station_registry.py and never
creates synthetic hourly observations from daily data.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from .data_pipeline import ensure_data_dirs, observations_to_frame
from .ingestion.normalizers import normalize_rainfall_csv, normalize_river_csv
from .labeling import build_24h_event_labels, load_district_events
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
    # Known spelling/format variations in the supplied historical sources.
    if district == "patna" and variable == "rainfall" and granularity == "daily":
        aliases.update({_norm_station("Gandhi Ghat"), _norm_station("Gandhighat")})
    if district == "muzaffarpur" and variable == "rainfall" and granularity == "daily":
        aliases.update({
            _norm_station("Sikandarpur"),
            _norm_station("Sikandarpur (Muzzafarpur)"),
            _norm_station("Sikandarpur (Muzaffarpur)"),
        })
    return aliases


def _filter_supported(frame: pd.DataFrame, district: str, *, variable: str, granularity: str) -> pd.DataFrame:
    aliases = _station_aliases(district, variable, granularity)
    if not aliases:
        return frame.iloc[0:0].copy()
    mask = frame["District"].astype(str).str.strip().str.lower().str.replace(r"\s+", "_", regex=True).eq(district)
    mask &= frame["Station"].map(_norm_station).isin(aliases)
    return frame.loc[mask].copy()


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
    return {
        "rows": int(len(frame)),
        "districts": sorted(frame["district"].dropna().unique().tolist()),
        "stations": sorted(frame["station_id"].dropna().astype(str).unique().tolist()),
        "start": ts.min().isoformat() if not ts.isna().all() else None,
        "end": ts.max().isoformat() if not ts.isna().all() else None,
    }


def assemble(
    *,
    hourly_rainfall: str | Path | None = None,
    daily_rainfall: str | Path | None = None,
    river: str | Path | None = None,
    events: str | Path,
    rainfall_hourly_value_column: str = "Telemetry Hourly Rainfall (mm)",
    rainfall_daily_value_column: str = "Manual Rainfall (mm)",
    river_value_column: str = "River Water Level Telemetry Hourly (meter)",
    output_root: str | Path | None = None,
) -> dict:
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
        "notes": [
            "Daily rainfall is retained as processed evidence but is not upsampled into hourly training rows.",
            "Only stations explicitly listed in station_registry.py are included.",
        ],
    }

    for district in DISTRICTS:
        district_frames = [
            frame for name, frame in sources.items()
            if name in {"rainfall_hourly", "river"} and not frame.empty
        ]
        observations = (
            pd.concat(district_frames, ignore_index=True)
            if district_frames else pd.DataFrame()
        )
        if observations.empty:
            report["districts"][district] = {
                "status": "not_trainable",
                "reason": "No supported hourly rainfall or river observations.",
                "training": {"rows": 0, "positive": 0, "negative": 0, "positive_rate": 0.0},
            }
            continue

        observations = observations[observations["district"] == district].copy()
        timestamps = pd.Series(pd.to_datetime(observations["timestamp"], utc=True).drop_duplicates())
        labels = build_24h_event_labels(timestamps, event_frame, district=district)
        table = build_training_table(observations, labels, district=district)

        target = summarize_target(table)
        status = "trainable" if target["positive"] > 0 and target["negative"] > 0 else "not_trainable"
        table.to_csv(paths["training"] / f"{district}_flood_training.csv", index=False)
        report["districts"][district] = {
            "status": status,
            "training": target,
            "observation_coverage": _audit_observations(observations),
            "label_positive_timestamps": int(labels["flood_event_start_next_24h"].sum()),
            "ongoing_timestamps_excluded": int(labels["flood_event_ongoing"].sum()),
        }

    report_path = paths["processed"] / "dataset_audit.json"
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
