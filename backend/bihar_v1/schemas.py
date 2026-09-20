"""Dependency-light data and API schemas for Bihar v1."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Observation:
    """Provider-neutral normalized observation used by the ingestion pipeline."""

    timestamp: str
    district: str
    variable: str
    value: float | None
    unit: str
    source: str
    station_id: str | None = None
    quality: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PredictionOutput:
    district: str
    probability: float | None = None
    horizon_hours: int = 24
    status: str = "not_ready"
    source: str = "model"
    generated_at: str = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskState:
    district: str
    rainfall_probability: float | None = None
    flood_probability: float | None = None
    inundation_probability: float | None = None
    risk_level: str = "unknown"
    generated_at: str = field(default_factory=utc_now)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
