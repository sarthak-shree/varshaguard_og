"""Calibration-aware fusion of Bihar v1 model probabilities.

No operational risk level is emitted until calibrated thresholds are supplied.
"""
from __future__ import annotations

from ..schemas import RiskState


def _valid_probability(value: float | None) -> bool:
    return value is not None and 0.0 <= float(value) <= 1.0


def fuse(
    district: str,
    rainfall: float | None,
    flood: float | None,
    inundation: float | None,
    *,
    thresholds: dict[str, float] | None = None,
) -> RiskState:
    probabilities = {
        "rainfall": rainfall,
        "flood": flood,
        "inundation": inundation,
    }
    invalid = [
        name for name, value in probabilities.items()
        if value is not None and not _valid_probability(value)
    ]
    if invalid:
        return RiskState(
            district=district,
            rainfall_probability=rainfall,
            flood_probability=flood,
            inundation_probability=inundation,
            risk_level="not_ready",
            details={"method": "calibrated_fusion_required", "reason": "probability_out_of_range",
                     "invalid_components": invalid},
        )

    available = {name: value for name, value in probabilities.items() if value is not None}
    if not available:
        return RiskState(district=district, risk_level="not_ready",
                         details={"method": "calibrated_fusion_required",
                                  "reason": "no_model_probabilities_available"})

    if thresholds is None:
        return RiskState(
            district=district,
            rainfall_probability=rainfall,
            flood_probability=flood,
            inundation_probability=inundation,
            risk_level="not_ready",
            details={"method": "calibrated_fusion_required",
                     "reason": "operational_thresholds_not_calibrated",
                     "available_components": list(available)},
        )

    required = {"low", "moderate", "high"}
    missing = sorted(required - set(thresholds))
    if missing:
        return RiskState(
            district=district,
            rainfall_probability=rainfall,
            flood_probability=flood,
            inundation_probability=inundation,
            risk_level="not_ready",
            details={"method": "calibrated_fusion_required",
                     "reason": "incomplete_thresholds", "missing_thresholds": missing},
        )

    low, moderate, high = (float(thresholds[k]) for k in ("low", "moderate", "high"))
    if not (0.0 <= low < moderate < high <= 1.0):
        raise ValueError("thresholds must satisfy 0 <= low < moderate < high <= 1")

    combined = max(float(value) for value in available.values())
    level = "high" if combined >= high else "moderate" if combined >= moderate else "low"
    return RiskState(
        district=district,
        rainfall_probability=rainfall,
        flood_probability=flood,
        inundation_probability=inundation,
        risk_level=level,
        details={"method": "calibrated_max_probability", "combined_probability": combined,
                 "thresholds": {"low": low, "moderate": moderate, "high": high},
                 "available_components": list(available)},
    )
