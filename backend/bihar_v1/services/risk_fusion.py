"""Risk fusion layer.

This first implementation refuses to manufacture a risk probability when model outputs are
not available. Production thresholds should be calibrated from validation data.
"""
from ..schemas import RiskState


def fuse(district: str, rainfall: float | None, flood: float | None, inundation: float | None) -> RiskState:
    values = [v for v in (rainfall, flood, inundation) if v is not None]
    if not values:
        return RiskState(district=district, risk_level="not_ready")
    # Placeholder only: real thresholds must be learned/calibrated from historical events.
    combined = max(values)
    level = "high" if combined >= 0.75 else "moderate" if combined >= 0.40 else "low"
    return RiskState(
        district=district,
        rainfall_probability=rainfall,
        flood_probability=flood,
        inundation_probability=inundation,
        risk_level=level,
        details={"method": "temporary_max_probability_placeholder"},
    )
