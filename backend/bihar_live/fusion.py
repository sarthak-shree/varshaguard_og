"""Phase 3 multi-source rainfall fusion baseline."""
from __future__ import annotations

SOURCE_WEIGHTS = {
    "0-3": {"radar": 0.45, "satellite": 0.40, "observations": 0.10, "nwp": 0.05},
    "6-24": {"radar": 0.15, "satellite": 0.20, "observations": 0.10, "nwp": 0.55},
    "24-72": {"radar": 0.05, "satellite": 0.10, "observations": 0.05, "nwp": 0.80},
}

def weights_for_lead(lead_hours: int) -> dict[str, float]:
    if lead_hours <= 3:
        return SOURCE_WEIGHTS["0-3"].copy()
    if lead_hours <= 24:
        return SOURCE_WEIGHTS["6-24"].copy()
    return SOURCE_WEIGHTS["24-72"].copy()

def fuse(values: dict[str, float | None], lead_hours: int) -> dict:
    weights = weights_for_lead(lead_hours)
    available = {k: v for k, v in values.items() if v is not None and k in weights}
    if not available:
        raise ValueError("No valid source values available for fusion")
    total_weight = sum(weights[k] for k in available)
    estimate = sum(float(values[k]) * weights[k] for k in available) / total_weight
    confidence = {k: round(weights[k] / total_weight, 4) for k in available}
    return {"estimate_mm": round(estimate, 3), "confidence": confidence, "weights": weights}
