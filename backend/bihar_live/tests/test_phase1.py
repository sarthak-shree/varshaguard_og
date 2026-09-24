from backend.bihar_live.app import create_app
from backend.bihar_live.config import DATA_MODE
from backend.bihar_live.synthetic import generate_observations

def test_synthetic_generator_has_both_districts_and_variables():
    rows = generate_observations(hours=6, seed=1)
    assert {row.district for row in rows} == {"patna", "muzaffarpur"}
    assert {row.variable for row in rows} == {"rain_mm", "river_level_m"}

def test_health_exposes_mode_badge():
    app = create_app()
    with app.test_client() as client:
        response = client.get("/api/bihar-live/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == DATA_MODE
    assert payload["badge"] == "Synthetic demo data"

def test_real_mode_fails_closed():
    from backend.bihar_live.adapters.sources import build_adapters
    adapters = build_adapters("real")
    try:
        adapters["radar"].fetch()
    except RuntimeError as exc:
        assert "not configured" in str(exc)
    else:
        raise AssertionError("Real adapter must not silently fall back to synthetic")
