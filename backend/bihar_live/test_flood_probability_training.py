import pandas as pd

from backend.bihar_live.train_flood_probability import _features


def test_target_looks_forward_24_hours():
    times = pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC")
    levels = [5.0] * 30
    levels[25] = 10.0
    frame = pd.DataFrame({
        "timestamp": times,
        "station": "TEST",
        "level": levels,
        "warning": 8.0,
        "danger": 9.0,
        "river": "Test River",
        "district": "Test",
    })
    result = _features(frame)
    row = result.loc[result["timestamp"] == times[0]].iloc[0]
    assert row["target"] == 1.0


def test_feature_engineering_requires_hourly_history():
    times = pd.date_range("2024-01-01", periods=30, freq="h", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": times,
        "station": "TEST",
        "level": 5.0,
        "warning": 8.0,
        "danger": 9.0,
        "river": "Test River",
        "district": "Test",
    })
    result = _features(frame)
    usable = result.dropna(subset=["rise_24h", "mean_24h", "target"])
    assert not usable.empty
