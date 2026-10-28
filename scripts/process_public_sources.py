"""Normalize downloaded official CSVs, report coverage, train only eligible real-data targets.

This orchestration never downloads or synthesizes replacement data itself. It processes only
files whose source downloader successfully saved and inventoried; schema mismatches are
reported and skipped, never guessed around.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.fetch_public_sources import OUT as RAW_DIR, SOURCES
from scripts.normalize_public_sources import normalize_public_csv
from backend.bihar_live.historical_pipeline import build_supervised_rows, train_and_evaluate
from scripts.evaluate_independent_events import evaluate_events

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "processed" / "public_sources"
EVENT_LEDGER = ROOT / "data" / "bihar_live" / "research" / "independent_flood_events.csv"
SOURCE_CONFIG = {
    "bihar_hourly_rainfall": ("Bihar Water Department", "rainfall_mm", "mm"),
    "cwc_bihar_hourly_rainfall": ("Central Water Commission", "rainfall_mm", "mm"),
    "bihar_hourly_river_stage": ("Bihar Water Department", "stage_m", "m"),
    "bihar_daily_water_level": ("Bihar Water Department", "stage_m", "m"),
}


def run() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"downloads": {}}
    normalized_frames = []
    statuses = []
    for source_id, (agency, variable, unit) in SOURCE_CONFIG.items():
        raw_path = RAW_DIR / f"{source_id}.csv"
        if not raw_path.exists():
            statuses.append({"source_id": source_id, "status": "not_downloaded"})
            continue
        try:
            normalized, coverage = normalize_public_csv(
                raw_path, source_id, agency, variable, unit, source_kind="observed"
            )
            normalized.to_csv(OUTPUT / f"{source_id}_observations.csv", index=False)
            (OUTPUT / f"{source_id}_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
            normalized_frames.append(normalized)
            statuses.append({"source_id": source_id, "status": "normalized", **coverage})
        except Exception as exc:
            statuses.append({
                "source_id": source_id, "status": "schema_review_required",
                "error": f"{type(exc).__name__}: {exc}",
                "columns": manifest.get("downloads", {}).get(source_id, {}).get("inspection", {}).get("columns", []),
            })
    if normalized_frames:
        combined = pd.concat(normalized_frames, ignore_index=True)
        combined.to_csv(OUTPUT / "all_observations.csv", index=False)
        supervised = build_supervised_rows(combined)
        if not supervised.empty:
            supervised.to_csv(OUTPUT / "supervised_rows.csv", index=False)
        training = train_and_evaluate(supervised, OUTPUT / "models")
    else:
        combined = pd.DataFrame()
        supervised = pd.DataFrame()
        training = {
            "status": "insufficient_data", "operational": False,
            "message": "No downloaded CSV could be normalized. No model was trained.",
            "models": {},
        }
    # Existing ledger records are context-only until station/time/ground verification passes.
    if EVENT_LEDGER.exists():
        raw_events = pd.read_csv(EVENT_LEDGER)
        events = pd.DataFrame({
            "event_id": raw_events.get("event_id"),
            "station_id": raw_events.get("station_id", pd.Series([""] * len(raw_events))),
            "event_start": raw_events.get("event_start_time_ist"),
            "event_end": raw_events.get("event_end_time_ist"),
            "ground_verified": raw_events.get("ground_verified", False),
            "station_level_match_ready": raw_events.get("station_level_match_ready", False),
        })
        if "matching_status" in raw_events:
            matched = raw_events["matching_status"].astype(str).str.lower().eq("matched")
            events["station_level_match_ready"] = events["station_level_match_ready"].astype(str).str.lower().isin({"true", "1", "yes"}) & matched
        event_report = evaluate_events(
            pd.DataFrame(columns=["station_id", "issue_time", "predicted_event"]), events
        )
    else:
        event_report = {"status": "not_estimable", "operational": False, "metrics": None,
                        "reason": "Independent event ledger is missing."}
    report = {
        "schema_version": 1, "status": "completed_with_gaps" if statuses else "no_sources",
        "sources": statuses,
        "source_count": len(statuses),
        "normalized_source_count": sum(item["status"] == "normalized" for item in statuses),
        "observation_rows": int(len(combined)),
        "station_count": int(combined["station_id"].nunique()) if not combined.empty else 0,
        "supervised_issue_rows": int(len(supervised)),
        "training": training,
        "independent_event_evaluation": event_report,
        "operational": False,
        "warnings": [
            "No station identity is merged across agencies without an explicit mapping file.",
            "Daily stage measurements are not relabelled as hourly observations.",
            "Forecast inputs are not used as observed rainfall targets.",
            "Event metrics remain unavailable unless independent events have verified station-level matches and exact onset times.",
        ],
    }
    (OUTPUT / "pipeline_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    run()
