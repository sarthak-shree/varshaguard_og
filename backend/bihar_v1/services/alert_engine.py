"""Alert generation from a fused risk state."""
from ..schemas import RiskState


def build_alert(state: RiskState) -> dict:
    if state.risk_level in {"unknown", "not_ready"}:
        return {"active": False, "reason": "prediction system not ready", "district": state.district}
    return {
        "active": state.risk_level in {"moderate", "high"},
        "district": state.district,
        "risk_level": state.risk_level,
        "horizon_hours": 24,
        "generated_at": state.generated_at,
    }
