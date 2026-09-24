from backend.bihar_live.fusion import fuse, weights_for_lead
from backend.bihar_live.synthetic import generate_observations
from backend.bihar_live.models.training import train_evaluate

def test_short_lead_weights_favor_radar_and_satellite():
    w=weights_for_lead(3)
    assert w["radar"] > w["nwp"] and w["satellite"] > w["nwp"]

def test_fusion_returns_confidence():
    result=fuse({"radar":20,"satellite":10,"observations":5,"nwp":2},3)
    assert result["estimate_mm"] > 0
    assert abs(sum(result["confidence"].values())-1)<1e-6

def test_model_uses_chronological_split():
    _,metrics=train_evaluate(generate_observations(hours=96))
    assert metrics["split"]=="chronological"
    assert metrics["data_mode"]=="synthetic"
