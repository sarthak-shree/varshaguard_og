"""Alert generation from a fused risk state.

Alerts are fail-closed: only calibrated operational risk states may activate one.
"""
from __future__ import annotations

from ..schemas import RiskState


def build_alert(state: RiskState) -> dict:
    if state.risk_level in {"unknown", "not_ready"}:
        return {
            "active": False,
            "reason": "prediction system not ready",
            "district": state.district,
        }

    if state.risk_level not in {"low", "moderate", "high"}:
        return {
            "active": False,
            "reason": "invalid risk level",
            "district": state.district,
        }

    return {
        "active": state.risk_level in {"moderate", "high"},
        "district": state.district,
        "risk_level": state.risk_level,
        "horizon_hours": 24,
        "generated_at": state.generated_at,
    }
