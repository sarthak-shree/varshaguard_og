"""Offline regression tests for the Bihar live flood engine."""
from ml_engine import _alert_state, _rain_features, _river_confirmation, _river_summary


def test_rain_windows_are_not_all_the_same():
    features = _rain_features({
        "2026-09-10": 1.0,
        "2026-09-11": 2.0,
        "2026-09-12": 3.0,
        "2026-09-13": 4.0,
        "2026-09-14": 5.0,
    }, 9)
    assert features["rainfall_mm"] == 5.0
    assert features["rainfall_3d_sum_mm"] == 12.0
    assert features["rainfall_7d_sum_mm"] == 15.0
    assert features["rainfall_change_1d_mm"] == 1.0


def test_river_status_counts_thresholds():
    river = _river_summary([
        {"water_level_m": 10, "warning_level_m": 9, "danger_level_m": 11, "rise_1h_m": 0.1},
        {"water_level_m": 12, "warning_level_m": 9, "danger_level_m": 11, "rise_1h_m": -0.1},
    ])
    assert river["warning_count"] == 1
    assert river["danger_count"] == 1
    assert river["count"] == 2
    assert _river_confirmation(river) == "DANGER"


def test_alert_state_uses_ml_and_river_evidence():
    normal = {"danger_count": 0, "warning_count": 0}
    warning = {"danger_count": 0, "warning_count": 1}
    danger = {"danger_count": 1, "warning_count": 0}
    assert _alert_state(0.1, normal) == "LOW"
    assert _alert_state(0.1, warning) == "MEDIUM"
    assert _alert_state(0.1, danger) == "HIGH"
    assert _alert_state(0.8, normal) == "HIGH"


if __name__ == "__main__":
    test_rain_windows_are_not_all_the_same()
    test_river_status_counts_thresholds()
    test_alert_state_uses_ml_and_river_evidence()
    print("Bihar ML engine regression tests passed")
