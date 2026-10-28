from backend.bihar_live import open_meteo_flood


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_flood_client_uses_bihar_coordinates_and_requested_models(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({
            "timezone": "Asia/Kolkata",
            "daily_units": {"river_discharge": "m³/s"},
            "daily": {
                "time": ["2026-10-28", "2026-10-29"],
                "river_discharge": [120.0, 145.0],
                "river_discharge_mean": [118.0, 140.0],
            },
        })

    monkeypatch.setattr(open_meteo_flood.requests, "get", fake_get)
    open_meteo_flood._cache.clear()
    result = open_meteo_flood.get_river_discharge_forecast("patna", force_refresh=True)

    assert result["available"] is True
    assert result["coordinates"]["latitude"] == 25.623333
    assert result["coordinates"]["longitude"] == 85.171111
    assert result["daily"]["river_discharge"] == [120.0, 145.0]
    assert result["operational"] is False
    assert captured["url"] == open_meteo_flood.OPEN_METEO_FLOOD_URL
    assert captured["params"]["ensemble"] == "true"
    assert captured["params"]["models"] == ",".join(open_meteo_flood.MODEL_NAMES)
    assert captured["timeout"] == open_meteo_flood.REQUEST_TIMEOUT_SECONDS


def test_flood_client_handles_http_failure(monkeypatch):
    def fake_get(*args, **kwargs):
        raise open_meteo_flood.requests.Timeout("timed out")

    monkeypatch.setattr(open_meteo_flood.requests, "get", fake_get)
    open_meteo_flood._cache.clear()
    result = open_meteo_flood.get_river_discharge_forecast("muzaffarpur", force_refresh=True)

    assert result["available"] is False
    assert "temporarily unavailable" in result["message"]


def test_flood_client_rejects_unsupported_district_without_network(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("network should not be called for unsupported district")

    monkeypatch.setattr(open_meteo_flood.requests, "get", fail_if_called)
    result = open_meteo_flood.get_river_discharge_forecast("oslo", force_refresh=True)
    assert result["available"] is False


def test_flood_client_accepts_nested_ensemble_series(monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse({
            "timezone": "Asia/Kolkata",
            "daily_units": {"river_discharge": "m³/s"},
            "daily": {
                "time": ["2026-10-28", "2026-10-29"],
                "river_discharge": [[100.0, 120.0, 140.0], [110.0, 130.0, 150.0]],
            },
        })

    monkeypatch.setattr(open_meteo_flood.requests, "get", fake_get)
    open_meteo_flood._cache.clear()
    result = open_meteo_flood.get_river_discharge_forecast("patna", force_refresh=True)

    assert result["available"] is True
    assert result["daily"]["river_discharge"][0] == [100.0, 120.0, 140.0]
