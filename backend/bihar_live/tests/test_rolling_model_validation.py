import numpy as np
import pandas as pd

from backend.bihar_live.research.train_cwc_gauge_rolling_24h import (
    TARGET,
    calibration_summary,
    crossing_episode_summary,
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

    long_gap = np.concatenate([issue + np.arange(1, 11, dtype=np.int64) * hour,
                               issue + np.arange(17, 25, dtype=np.int64) * hour])
    assert not future_horizon_is_covered(issue, long_gap)

    short_end = issue + np.arange(1, 22, dtype=np.int64) * hour
    assert not future_horizon_is_covered(issue, short_end)



def test_crossing_episode_summary_deduplicates_overlapping_windows_and_uses_earliest_detection():
    crossing_a = pd.Timestamp("2026-06-01T12:00:00")
    crossing_b = pd.Timestamp("2026-06-05T06:00:00")
    rows = pd.DataFrame({
        "target_station": ["A", "A", "A", "B"],
        "issue_time": [
            crossing_a - pd.Timedelta(hours=18),
            crossing_a - pd.Timedelta(hours=12),
            crossing_a - pd.Timedelta(hours=6),
            crossing_b - pd.Timedelta(hours=12),
        ],
        "target_crossing_time": [crossing_a, crossing_a, crossing_a, crossing_b],
        TARGET: [1, 1, 1, 1],
    })

    result = crossing_episode_summary(rows, np.array([0.8, 0.1, 0.9, 0.1]), threshold=0.5)

    assert result["observed_crossing_episodes"] == 2
    assert result["detected_crossing_episodes"] == 1
    assert result["missed_crossing_episodes"] == 1
    assert result["episode_recall"] == 0.5
    assert result["median_lead_time_hours"] == 18.0
    assert "not independent or verified flood events" in result["interpretation"]


def test_crossing_episode_summary_counts_distinct_crossings_at_same_station():
    crossing_a = pd.Timestamp("2026-06-01T12:00:00")
    crossing_b = pd.Timestamp("2026-06-03T12:00:00")
    rows = pd.DataFrame({
        "target_station": ["A", "A", "A"],
        "issue_time": [
            crossing_a - pd.Timedelta(hours=12),
            crossing_b - pd.Timedelta(hours=18),
            crossing_b - pd.Timedelta(hours=6),
        ],
        "target_crossing_time": [crossing_a, crossing_b, crossing_b],
        TARGET: [1, 1, 1],
    })

    result = crossing_episode_summary(rows, np.array([0.8, 0.8, 0.7]), threshold=0.5)

    assert result["observed_crossing_episodes"] == 2
    assert result["detected_crossing_episodes"] == 2
    assert result["missed_crossing_episodes"] == 0
    assert result["episode_recall"] == 1.0
    assert result["median_lead_time_hours"] == 15.0


def test_crossing_episode_summary_returns_explicit_unavailable_metrics_when_none_detected():
    crossing = pd.Timestamp("2026-06-01T12:00:00")
    rows = pd.DataFrame({
        "target_station": ["A", "A"],
        "issue_time": [crossing - pd.Timedelta(hours=12), crossing - pd.Timedelta(hours=6)],
        "target_crossing_time": [crossing, crossing],
        TARGET: [1, 1],
    })

    result = crossing_episode_summary(rows, np.array([0.1, 0.2]), threshold=0.5)

    assert result["observed_crossing_episodes"] == 1
    assert result["detected_crossing_episodes"] == 0
    assert result["missed_crossing_episodes"] == 1
    assert result["episode_recall"] == 0.0
    assert "unavailable" in result["lead_time_note"]
