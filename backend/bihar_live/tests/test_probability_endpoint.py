from backend.app import app
from backend.bihar_live.research import live_prediction


def authenticated_client():
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 1  # authenticated test session for protected API routes
    return client


def test_probability_endpoint_returns_only_supported_flood_probability(monkeypatch):
    monkeypatch.setattr(live_prediction, "get_live_predictions", lambda: {
        "success": True,
        "available": True,
        "predictions": [{
            "district": "Patna",
            "station_name": "Patna Gandhighat",
            "status": "predicted",
            "risk_basis": "model_probability",
            "risk_percentage": 23.4,
            "forecast_end_ist": "2026-10-29T12:00:00",
            "observed_at_ist": "2026-10-28T12:00:00",
            "message": "Research estimate only.",
        }],
    })
    response = authenticated_client().get("/api/bihar-live/probability?district=patna&type=flood")
    body = response.get_json()

    assert response.status_code == 200
    assert body["available"] is True
    assert body["probability_percent"] == 23.4
    assert body["horizon_hours"] == 24
    assert "daily" not in body
    assert body["operational"] is False


def test_probability_endpoint_does_not_invent_heavy_rain_probability():
    response = authenticated_client().get("/api/bihar-live/probability?district=patna&type=heavy_rainfall")
    body = response.get_json()

    assert response.status_code == 200
    assert body["available"] is False
    assert body["probability_percent"] is None
    assert body["status"] == "model_not_available"


def test_probability_endpoint_rejects_unknown_district():
    response = authenticated_client().get("/api/bihar-live/probability?district=oslo&type=flood")
    assert response.status_code == 400


def test_probability_endpoint_withholds_probability_when_gauge_is_already_at_warning():
    monkeypatch_payload = {
        "success": True,
        "available": True,
        "predictions": [{
            "district": "Patna",
            "station_name": "Patna Gandhighat",
            "status": "warning_level_reached",
            "risk_basis": "observed",
            "risk_percentage": 100.0,
            "message": "Observed warning threshold reached.",
        }],
    }
    from backend.bihar_live.research import live_prediction
    original = live_prediction.get_live_predictions
    live_prediction.get_live_predictions = lambda: monkeypatch_payload
    try:
        body = authenticated_client().get("/api/bihar-live/probability?district=patna&type=flood").get_json()
    finally:
        live_prediction.get_live_predictions = original

    assert body["available"] is False
    assert body["probability_percent"] is None
    assert body["observed_threshold_reached"] is True
