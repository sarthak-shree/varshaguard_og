"""Provider-neutral schemas for JalDrishti data exchange."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class GridObservation:
    timestamp_utc: str
    timestamp_ist: str
    district: str
    source: str
    variable: str
    value: float | None
    unit: str
    latitude: float | None = None
    longitude: float | None = None
    quality: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class ForecastPoint:
    district: str
    lead_hours: int
    expected_rain_mm: float
    heavy_rain_probability: float
    lower_mm: float
    upper_mm: float
    source_confidence: dict[str, float]
    generated_at: str = field(default_factory=utc_now)
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
