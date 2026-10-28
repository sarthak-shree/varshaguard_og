from pathlib import Path

import pandas as pd
import pytest

from scripts.normalize_public_sources import align_observations, normalize_public_csv
from scripts.evaluate_independent_events import evaluate_events


def test_normalizer_keeps_observed_source_and_reports_coverage(tmp_path):
    path = tmp_path / "rain.csv"
    pd.DataFrame({
        "Station Name": ["Gauge A", "Gauge A", "Gauge A"],
        "Date Time": ["2025-08-01 00:00:00", "2025-08-01 01:00:00", "bad timestamp"],
        "Rainfall (mm)": [0.0, 5.0, 9.0],
    }).to_csv(path, index=False)
    normalized, report = normalize_public_csv(path, "bihar-rain", "Bihar WRD", "rainfall_mm", "mm")

    assert len(normalized) == 2
    assert normalized["source_kind"].eq("observed").all()
    assert normalized["station_id"].iloc[0] == "bihar-rain:Gauge A"
    assert report["rejected_rows"] == 1
    assert report["station_reconciliation"] == "source-prefixed IDs; cross-agency joins disabled"


def test_forecast_input_cannot_be_normalized_as_observation_labels(tmp_path):
    path = tmp_path / "forecast.csv"
    pd.DataFrame({"station": ["A"], "date": ["2025-01-01"], "rainfall": [3]}).to_csv(path, index=False)
    with pytest.raises(ValueError, match="Forecast inputs"):
        normalize_public_csv(path, "nwp", "Weather provider", "rainfall_mm", "mm", source_kind="forecast")


def test_alignment_reports_missing_hour_slots_without_filling():
    frame = pd.DataFrame([
        {"station_id": "A", "observed_at": "2025-01-01T00:00:00+00:00", "variable": "stage_m", "value": 2.0},
        {"station_id": "A", "observed_at": "2025-01-01T02:00:00+00:00", "variable": "stage_m", "value": 2.5},
    ])
    aligned, report = align_observations(frame)

    assert len(aligned) == 3
    assert pd.isna(aligned.loc[1, "stage_m"])
    assert report["missing_values_not_filled"] is True
    assert report["missing_hour_slots"] >= 1


def test_event_metrics_are_not_estimable_without_verified_station_matches():
    predictions = pd.DataFrame([{"station_id": "A", "issue_time": "2025-01-01T00:00:00Z", "predicted_event": True}])
    events = pd.DataFrame([{
        "event_id": "broad-map", "station_id": "", "event_start": None, "event_end": None,
        "ground_verified": False, "station_level_match_ready": False,
    }])
    report = evaluate_events(predictions, events)

    assert report["status"] == "not_estimable"
    assert report["metrics"] is None
    assert report["eligible_events"] == 0


def test_event_recall_and_lead_time_only_use_verified_matched_events():
    predictions = pd.DataFrame([
        {"station_id": "A", "issue_time": "2025-08-01T00:00:00Z", "predicted_event": True},
        {"station_id": "A", "issue_time": "2025-08-01T12:00:00Z", "predicted_event": False},
    ])
    events = pd.DataFrame([{
        "event_id": "event-1", "station_id": "A", "event_start": "2025-08-01T06:00:00Z",
        "event_end": "2025-08-01T18:00:00Z", "ground_verified": True, "station_level_match_ready": True,
    }])
    report = evaluate_events(predictions, events)

    assert report["status"] == "evaluated_research_only"
    assert report["metrics"]["event_recall"] == 1.0
    assert report["metrics"]["median_lead_time_hours_detected_events"] == 6.0
    assert "not inferred" in report["precision_note"]
