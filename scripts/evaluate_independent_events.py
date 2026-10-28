"""Independent event matching and conservative event-level evaluation.

Only events marked ground_verified and station_level_match_ready, with explicit event
start/end times and an exact station ID, can enter metrics. Broad-area reports and
satellite rapid-mapping snapshots without ground verification remain context-only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def evaluate_events(predictions: pd.DataFrame, events: pd.DataFrame, lead_hours: float = 24.0) -> dict:
    required_predictions = {"station_id", "issue_time", "predicted_event"}
    required_events = {"event_id", "station_id", "event_start", "event_end", "ground_verified", "station_level_match_ready"}
    if not required_predictions.issubset(predictions.columns):
        raise ValueError(f"predictions missing {sorted(required_predictions - set(predictions.columns))}")
    if not required_events.issubset(events.columns):
        raise ValueError(f"events missing {sorted(required_events - set(events.columns))}")
    pred = predictions.copy()
    pred["issue_time"] = pd.to_datetime(pred["issue_time"], utc=True, errors="coerce")
    pred["predicted_event"] = pred["predicted_event"].astype(bool)
    pred = pred.dropna(subset=["station_id", "issue_time"])
    ledger = events.copy()
    ledger["event_start"] = pd.to_datetime(ledger["event_start"], utc=True, errors="coerce")
    ledger["event_end"] = pd.to_datetime(ledger["event_end"], utc=True, errors="coerce")
    verified = ledger["ground_verified"].astype(str).str.lower().isin({"true", "1", "yes"})
    station_ready = ledger["station_level_match_ready"].astype(str).str.lower().isin({"true", "1", "yes"})
    eligible = ledger[verified & station_ready & ledger["event_start"].notna() & ledger["event_end"].notna()
                      & ledger["event_end"].ge(ledger["event_start"])].copy()
    if eligible.empty:
        return {
            "status": "not_estimable", "operational": False, "eligible_events": 0,
            "ineligible_event_rows": int(len(ledger)),
            "matched_prediction_rows": 0,
            "metrics": None,
            "reason": "No event has verified ground truth, exact station-level spatial matching, and explicit start/end times. Event precision, recall and lead time are not estimable.",
        }
    eligible_ids = set(eligible["event_id"].astype(str))
    matches = []
    for event in eligible.to_dict("records"):
        station_preds = pred[pred["station_id"].astype(str).eq(str(event["station_id"]))]
        lower = event["event_start"] - pd.Timedelta(hours=lead_hours)
        window = station_preds[(station_preds["issue_time"] >= lower) & (station_preds["issue_time"] <= event["event_start"])]
        positives = window[window["predicted_event"]]
        detected = not positives.empty
        lead = None
        if detected:
            first_alert = positives["issue_time"].max()
            lead = (event["event_start"] - first_alert).total_seconds() / 3600
        matches.append({"event_id": str(event["event_id"]), "station_id": str(event["station_id"]),
                        "detected": detected, "lead_time_hours": lead,
                        "prediction_rows_in_window": int(len(window))})
    event_hits = sum(item["detected"] for item in matches)
    # Event precision is only meaningful when alerts have an auditable event/no-event matching
    # policy. This function only estimates event recall and lead time for eligible events.
    return {
        "status": "evaluated_research_only", "operational": False,
        "eligible_events": int(len(eligible)), "ineligible_event_rows": int(len(ledger) - len(eligible)),
        "matched_prediction_rows": int(sum(item["prediction_rows_in_window"] for item in matches)),
        "metrics": {
            "event_recall": round(event_hits / len(eligible), 5),
            "events_detected": int(event_hits), "events_missed": int(len(eligible) - event_hits),
            "median_lead_time_hours_detected_events": (
                round(float(pd.Series([item["lead_time_hours"] for item in matches if item["lead_time_hours"] is not None]).median()), 3)
                if event_hits else None
            ),
        },
        "event_matches": matches,
        "precision_note": "Event precision and false-alarm rate require a complete, station/time-matched negative-event ledger; not inferred from positive events alone.",
        "lead_time_note": f"Detection means a positive prediction in the {lead_hours:g} hours before the documented event start; source event times must be independently verified.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, help="CSV: station_id,issue_time,predicted_event")
    parser.add_argument("--events", required=True, help="CSV: event_id,station_id,event_start,event_end,ground_verified,station_level_match_ready")
    parser.add_argument("--output", default="data/processed/event_evaluation.json")
    args = parser.parse_args()
    report = evaluate_events(pd.read_csv(args.predictions), pd.read_csv(args.events))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
