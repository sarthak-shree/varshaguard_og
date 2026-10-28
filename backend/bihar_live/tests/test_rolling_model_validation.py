import numpy as np
import pandas as pd

from backend.bihar_live.research.train_cwc_gauge_rolling_24h import (
    TARGET,
    calibration_summary,
    evaluate,
    lead_time_summary,
)


def test_calibration_summary_reports_reliability_bins_and_ece():
    y = pd.Series([0, 0, 1, 1])
    probability = np.array([0.1, 0.2, 0.8, 0.9])

    result = calibration_summary(y, probability, bins=5)

    assert result["expected_calibration_error"] == 0.15
    assert sum(item["rows"] for item in result["bins"]) == 4
    assert all("observed_positive_fraction" in item for item in result["bins"])


def test_evaluate_includes_calibration_and_imbalance_aware_metrics():
    y = pd.Series([0, 0, 0, 1, 1])
    probability = np.array([0.05, 0.1, 0.2, 0.7, 0.8])

    result = evaluate(y, probability, threshold=0.5, baseline=0.4)

    assert result["rows"] == 5
    assert result["positive_rows"] == 2
    assert result["average_precision"] is not None
    assert "expected_calibration_error" in result["calibration"]
    assert len(result["confusion_matrix_labels_0_1"]) == 2


def test_lead_time_uses_first_observed_crossing_for_detected_positive_windows():
    issue = pd.Timestamp("2026-06-01T00:00:00")
    rows = pd.DataFrame({
        "issue_time": [issue, issue],
        "target_crossing_time": [issue + pd.Timedelta(hours=9), pd.NaT],
        TARGET: [1, 0],
    })

    result = lead_time_summary(rows, np.array([0.9, 0.1]), threshold=0.5)

    assert result["detected_positive_issue_windows"] == 1
    assert result["median_hours"] == 9.0
    assert "not independent flood events" in result["interpretation"]


def test_lead_time_is_explicit_when_no_positive_window_is_detected():
    issue = pd.Timestamp("2026-06-01T00:00:00")
    rows = pd.DataFrame({
        "issue_time": [issue],
        "target_crossing_time": [pd.NaT],
        TARGET: [0],
    })

    result = lead_time_summary(rows, np.array([0.1]), threshold=0.5)

    assert result["detected_positive_issue_windows"] == 0
    assert "unavailable" in result["note"]

def test_future_horizon_coverage_requires_start_end_and_bounded_gaps():
    from backend.bihar_live.research.train_cwc_gauge_rolling_24h import future_horizon_is_covered

    hour = 3_600_000_000_000
    issue = 1_800_000_000_000_000_000
    hourly = issue + np.arange(1, 25, dtype=np.int64) * hour
    assert future_horizon_is_covered(issue, hourly)

    late_start = issue + np.arange(5, 25, dtype=np.int64) * hour
    assert not future_horizon_is_covered(issue, late_start)

    long_gap = np.concatenate([issue + np.arange(1, 10, dtype=np.int64) * hour,
                               issue + np.arange(17, 25, dtype=np.int64) * hour])
    assert not future_horizon_is_covered(issue, long_gap)

    short_end = issue + np.arange(1, 22, dtype=np.int64) * hour
    assert not future_horizon_is_covered(issue, short_end)
