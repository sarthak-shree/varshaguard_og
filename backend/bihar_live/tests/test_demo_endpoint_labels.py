from backend.bihar_live.app import create_app


def test_fusion_endpoint_never_claims_live_multi_source_data():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/bihar-live/fusion")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "synthetic_demo"
    assert payload["source_status"] == "not_integrated"
    assert payload["operational"] is False
    assert "not live" in payload["badge"]


def test_evaluation_endpoint_marks_metrics_as_synthetic_only():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/bihar-live/model/evaluation")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "synthetic_demo"
    assert payload["model"] == "synthetic_rainfall_baseline"
    assert payload["operational"] is False
    assert "not evidence" in payload["badge"]
