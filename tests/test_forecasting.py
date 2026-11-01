from datetime import datetime, timedelta, timezone

from backend.bihar_live.forecasting import project_stage_trend, rainfall_summary

IST = timezone(timedelta(hours=5, minutes=30))


def test_rainfall_summary_accumulates_hourly_forecast_and_preserves_provider_context():
    start = datetime(2026, 7, 1, 10, tzinfo=IST)
    rows = [
        {
            "time_ist": (start + timedelta(hours=index)).isoformat(),
            "precipitation_mm": 1.25,
            "precipitation_probability_pct": 60 + (index % 10),
        }
        for index in range(24)
    ]

    result = rainfall_summary(rows, "patna")

    assert result["available"] is True
    assert result["rainfall_accumulation_mm"]["next_1h"] == 1.2
    assert result["rainfall_accumulation_mm"]["next_3h"] == 3.8
    assert result["rainfall_accumulation_mm"]["next_24h"] == 30.0
    assert result["peak_hourly_rainfall_mm"] == 1.2
    assert result["maximum_precipitation_chance_pct"] == 69
    assert result["validation"]["validated_on_independent_local_rain_gauge_labels"] is False
    assert result["operational"] is False


def test_rainfall_summary_fails_closed_for_invalid_or_negative_rows():
    result = rainfall_summary([
        {"time": "not-a-time", "precipitation_mm": 2},
        {"time": "2026-07-01T10:00:00+05:30", "precipitation_mm": -1},
        {"time": "2026-07-01T11:00:00+05:30", "precipitation_mm": "NaN"},
    ], "patna")

    assert result["available"] is False
    assert "No valid" in result["message"]


def test_stage_trend_projects_recent_linear_rise_without_claiming_validation():
    start = datetime(2026, 7, 1, 0, tzinfo=IST)
    history = [
        {
            "timestamp_ist": (start + timedelta(hours=index)).isoformat(),
            "stage_m": 10.0 + index * 0.1,
        }
        for index in range(7)
    ]

    result = project_stage_trend(history, warning_level_m=11.0)

    assert result["available"] is True
    assert result["trend_direction"] == "rising"
    assert result["trend_m_per_hour"] > 0
    assert result["forecasts"][1]["horizon_hours"] == 3
    assert abs(result["forecasts"][1]["projected_stage_m"] - 10.9) < 0.01
    assert result["forecasts"][-1]["trend_crosses_warning"] is True
    assert result["validation"]["chronological_backtest_complete"] is False
    assert result["operational"] is False


def test_stage_trend_requires_enough_recent_observations_and_span():
    short = [
        {"timestamp_ist": "2026-07-01T10:00:00+05:30", "stage_m": 10.0},
        {"timestamp_ist": "2026-07-01T10:15:00+05:30", "stage_m": 10.1},
    ]
    result = project_stage_trend(short)

    assert result["available"] is False
    assert "three distinct" in result["message"]


def test_stage_trend_ignores_invalid_values_and_duplicate_timestamps():
    history = [
        {"timestamp_ist": "2026-07-01T00:00:00+05:30", "stage_m": 10},
        {"timestamp_ist": "2026-07-01T00:00:00+05:30", "stage_m": 10.1},
        {"timestamp_ist": "2026-07-01T01:00:00+05:30", "stage_m": 10.2},
        {"timestamp_ist": "2026-07-01T02:00:00+05:30", "stage_m": "bad"},
        {"timestamp_ist": "2026-07-01T03:00:00+05:30", "stage_m": 10.4},
    ]
    result = project_stage_trend(history)

    assert result["available"] is True
    assert result["observations_used"] == 3
