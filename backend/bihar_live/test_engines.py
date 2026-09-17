from backend.bihar_live.inundation_engine import build_inundation_context
from backend.bihar_live.risk_engine import build_risk_context


def test_risk_engine_never_invents_probability():
    record = {"water_level_m": 10.0, "warning_level_m": 9.0, "danger_level_m": 11.0, "trend": "rising"}
    result = build_risk_context(record)
    assert result["risk_level"] == "WARNING"
    assert result["probability"] is None
    assert result["probability_available"] is False


def test_inundation_engine_requires_spatial_inputs():
    result = build_inundation_context({"water_level_m": 10.0})
    assert result["status"] == "awaiting_model_inputs"
    assert result["extent_percent"] is None
    assert "terrain/DEM" in result["requires"]
