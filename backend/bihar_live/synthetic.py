"""Deterministic monsoon-style synthetic generator for Phase 1."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import math
import random
from .config import SUPPORTED_DISTRICTS
from .schemas import GridObservation

def generate_observations(hours: int = 24, seed: int = 26071) -> list[GridObservation]:
    rng = random.Random(seed)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=hours - 1)
    out: list[GridObservation] = []
    centres = {"patna": (25.5941, 85.1376), "muzaffarpur": (26.1209, 85.3647)}
    for district_idx, slug in enumerate(SUPPORTED_DISTRICTS):
        lat, lon = centres[slug]
        rain_scale = 1.25 if slug == "patna" else 1.05
        river_base = 50.0 if slug == "patna" else 49.0
        for i in range(hours):
            ts = start + timedelta(hours=i)
            ist = ts.astimezone(timezone(timedelta(hours=5, minutes=30)))
            phase = i / max(hours - 1, 1)
            pulse = max(0.0, math.sin((phase * 2.8 + district_idx) * math.pi)) ** 6
            rain = max(0.0, rng.gauss(1.2 + 17.0 * pulse * rain_scale, 1.0))
            river = river_base + 0.45 * max(0.0, rain - 5.0) + 0.15 * i + rng.uniform(-0.2, 0.2)
            out.append(GridObservation(
                timestamp_utc=ts.isoformat(), timestamp_ist=ist.isoformat(),
                district=slug, source="synthetic", variable="rain_mm",
                value=round(rain, 3), unit="mm", latitude=lat, longitude=lon,
                quality="synthetic", metadata={"grid_resolution_deg": 0.05},
            ))
            out.append(GridObservation(
                timestamp_utc=ts.isoformat(), timestamp_ist=ist.isoformat(),
                district=slug, source="synthetic", variable="river_level_m",
                value=round(river, 3), unit="m", latitude=lat, longitude=lon,
                quality="synthetic", metadata={"grid_resolution_deg": 0.05},
            ))
    return out
