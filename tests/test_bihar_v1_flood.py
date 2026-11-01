"""Bihar v1 flood forecast: live CWC gauge model wiring and fail-closed states."""
import joblib
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from backend.app import app
from backend.bihar_live.research import live_prediction
from backend.bihar_v1.prediction import flood_predictor


def _live_payload(**overrides):
    prediction = {
        "station_code": "003-MGD5PTN",
        "station_name": "Gandhighat",
        "district": "Patna",
        "status": "predicted",
        "risk_basis": "model_probability",
        "risk_level": "medium",
        "model_probability": 0.31,
        "decision_threshold": 0.206491,
        "observed_at_ist": "2026-07-01T10:00",
        "forecast_end_ist": "2026-07-02T10:00",
        "current_stage_m": 46.9,
        "warning_level_m": 47.6,
        "feature_coverage": {"available": 30, "total": 43},
        "message": "Experimental estimate.",
    }
    prediction.update(overrides)
    return {
        "available": True,
        "model_name": "cwc_test",
        "model_type": "random_forest",
        "generated_at_ist": "2026-07-01T10:05:00+05:30",
        "limitations": ["Research only."],
        "predictions": [prediction],
    }


@pytest.fixture
def live(monkeypatch):
    """Patch the live CWC call; returns a setter for the payload it should return."""
    state = {"payload": _live_payload()}
    monkeypatch.setattr(live_prediction, "get_live_predictions", lambda: state["payload"])
    return state


def test_predicted_returns_model_probability(live):
    out = flood_predictor.predict("Patna", {})
    assert out.status == "ok"
    assert out.probability == pytest.approx(0.31)
    assert out.source == flood_predictor.LIVE_CWC_SOURCE
    assert out.details["station_name"] == "Gandhighat"
    assert out.details["dashboard_band"] == "medium"
    assert out.details["operational"] is False
    assert out.details["operational_threshold_status"] == "not_calibrated"
    assert "not a flood-event" in out.details["target_definition"]


@pytest.mark.parametrize("live_status", ["warning_level_reached", "danger_level_reached"])
def test_observed_threshold_is_not_reported_as_a_probability(live, live_status):
    live["payload"] = _live_payload(
        status=live_status, risk_basis="observed", model_probability=None, risk_level="high"
    )
    out = flood_predictor.predict("patna", {})
    assert out.status == "observed_threshold_reached"
    assert out.probability is None
    assert out.details["dashboard_band"] is None


@pytest.mark.parametrize("live_status", ["stale", "insufficient_inputs", "model_error"])
def test_unusable_readings_withhold_probability(live, live_status):
    live["payload"] = _live_payload(
        status=live_status, risk_basis="unavailable", model_probability=None
    )
    out = flood_predictor.predict("patna", {})
    assert out.status == live_status
    assert out.probability is None


@pytest.mark.parametrize("bad", [None, -0.1, 1.5, float("nan"), "0.3", True])
def test_invalid_model_probability_is_rejected(live, bad):
    live["payload"] = _live_payload(model_probability=bad)
    out = flood_predictor.predict("patna", {})
    assert out.status == "model_error"
    assert out.probability is None


def test_probability_requires_model_probability_basis(live):
    live["payload"] = _live_payload(risk_basis="observed")
    out = flood_predictor.predict("patna", {})
    assert out.status == "model_error"
    assert out.probability is None


def test_feed_unavailable_fails_closed(live):
    live["payload"] = {"available": False, "error": "CWC feed is unreachable.", "predictions": []}
    out = flood_predictor.predict("patna", {})
    assert out.status == "unavailable"
    assert out.probability is None
    assert out.details["message"] == "CWC feed is unreachable."


def test_district_without_a_gauge_prediction_is_unavailable(live):
    out = flood_predictor.predict("muzaffarpur", {})
    assert out.status == "unavailable"
    assert out.probability is None


def test_live_call_exception_never_propagates(monkeypatch):
    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(live_prediction, "get_live_predictions", boom)
    out = flood_predictor.predict("patna", {})
    assert out.status == "unavailable"
    assert out.probability is None


def test_explicit_v1_artifact_takes_precedence_over_live_model(live, tmp_path):
    frame = pd.DataFrame({"x": [0.0, 1.0, 2.0, 3.0], "y": [0.0, 0.0, 1.0, 1.0]})
    model = LogisticRegression().fit(frame[["x"]], frame["y"])
    artifact = tmp_path / "patna_flood_xgboost.joblib"
    joblib.dump(model, artifact)

    out = flood_predictor.predict("patna", {"x": 2.5}, model_file=artifact)
    assert out.status == "ok"
    assert out.source == "model"  # the v1 artifact, not the live CWC model
    assert out.probability != pytest.approx(0.31)


def test_configured_but_missing_v1_model_does_not_fall_back(live, monkeypatch, tmp_path):
    monkeypatch.setenv("VARSHAGUARD_PATNA_FLOOD_MODEL", str(tmp_path / "missing.joblib"))
    out = flood_predictor.predict("patna", {})
    assert out.status == "model_not_trained"
    assert out.probability is None


def test_missing_research_model_files_report_not_trained(monkeypatch):
    monkeypatch.setattr(flood_predictor, "live_cwc_model_available", lambda: False)
    out = flood_predictor.predict("patna", {})
    assert out.status == "model_not_trained"


def test_forecast_endpoint_exposes_flood_but_keeps_risk_and_alert_closed(live):
    client = app.test_client()
    body = client.get("/api/bihar/v1/patna/forecast").get_json()
    assert body["success"] is True
    assert body["flood"]["status"] == "ok"
    assert body["flood"]["probability"] == pytest.approx(0.31)
    assert body["rainfall"]["status"] == "model_not_trained"
    assert body["inundation"]["status"] == "model_not_trained"
    # Probabilities are uncalibrated, so no operational risk level or alert is issued.
    assert body["risk"]["risk_level"] == "not_ready"
    assert body["risk"]["flood_probability"] == pytest.approx(0.31)
    assert body["alert"]["active"] is False


def test_forecast_endpoint_unsupported_district_is_404(live):
    assert app.test_client().get("/api/bihar/v1/delhi/forecast").status_code == 404


def test_status_endpoint_reports_live_research_model():
    body = app.test_client().get("/api/bihar/v1/patna/status").get_json()
    flood = body["models"]["flood"]
    assert flood["status"] == "live_cwc_research_model"
    assert flood["artifact_available"] is False
    assert body["operational_risk"] == "not_ready"
    assert body["data_feeds"]["status"] == "not_ready"
