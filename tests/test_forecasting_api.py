from datetime import datetime, timedelta, timezone

from flask import Flask

from backend.bihar_live.api import bp

IST = timezone(timedelta(hours=5, minutes=30))


def _client():
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client()


def test_rainfall_forecast_route_returns_derived_accumulations(monkeypatch):
    from backend.bihar_live import public_weather

    start = datetime(2026, 7, 1, 10, tzinfo=IST)
    hourly = [
        {
            "time_ist": (start + timedelta(hours=index)).isoformat(),
            "precipitation_mm": 2.0,
            "precipitation_probability_pct": 70,
        }
        for index in range(24)
    ]
    monkeypatch.setattr(public_weather, "get_rainfall_forecast", lambda district: {
        "success": True,
        "available": True,
        "district": district,
        "source": "Open-Meteo",
        "location": "Patna · Gandhighat",
        "fetched_at_ist": start.isoformat(),
        "hourly_forecast": hourly,
        "data_quality": {"valid_hourly_values": 24, "status": "usable"},
    })

    response = _client().get("/api/bihar-live/forecast/rainfall?district=patna")
    data = response.get_json()

    assert response.status_code == 200
    assert data["available"] is True
    assert data["rainfall_accumulation_mm"]["next_3h"] == 6.0
    assert data["rainfall_accumulation_mm"]["next_24h"] == 48.0
    assert data["validation"]["status"] == "provider_forecast_context_not_locally_validated"


def test_river_stage_forecast_route_uses_cwc_history_and_labels_baseline(monkeypatch):
    from backend.bihar_live.research import live_prediction

    start = datetime(2026, 7, 1, 0, tzinfo=IST)
    history = [
        {
            "timestamp_ist": (start + timedelta(hours=index)).isoformat(),
            "stage_m": 10.0 + index * 0.1,
        }
        for index in range(7)
    ]
    monkeypatch.setattr(live_prediction, "get_live_predictions", lambda: {
        "success": True,
        "available": True,
        "predictions": [{
            "district": "Patna",
            "station_name": "Patna · Gandhighat",
            "stage_history": history,
            "warning_level_m": 11.0,
            "observed_at_ist": history[-1]["timestamp_ist"],
            "data_age_hours": 0.2,
            "current_stage_m": 10.6,
        }],
    })

    response = _client().get("/api/bihar-live/forecast/river-stage?district=patna")
    data = response.get_json()

    assert response.status_code == 200
    assert data["available"] is True
    assert data["method"] == "ordinary_least_squares_recent_stage_trend"
    assert data["forecasts"][1]["horizon_hours"] == 3
    assert data["operational"] is False
    assert data["validation"]["chronological_backtest_complete"] is False


def test_forecast_routes_reject_unsupported_districts():
    client = _client()

    assert client.get("/api/bihar-live/forecast/rainfall?district=nowhere").status_code == 400
    assert client.get("/api/bihar-live/forecast/river-stage?district=nowhere").status_code == 400
    assert client.get("/api/bihar-live/data-quality?district=nowhere").status_code == 400
