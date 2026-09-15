"""Layer 1.3A: persistence abstraction for Bihar river observations.

The storage layer deliberately contains no database-driver-specific code.
A PostgreSQL repository can implement this contract in Layer 1.3B.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True)
class RiverObservation:
    """Canonical observation record stored by VARSHAGUARD."""

    river: str
    station: str
    district: str
    observed_at: datetime | None
    water_level_m: float
    warning_level_m: float | None = None
    danger_level_m: float | None = None
    hfl_m: float | None = None
    trend: str | None = None
    water_level_1h_before_m: float | None = None
    fetched_at: datetime | None = None


class RiverObservationRepository(Protocol):
    """Persistence contract used by the Bihar Live service."""

    def save_observations(self, observations: Sequence[RiverObservation]) -> int:
        """Persist observations and return the number accepted."""
        ...

    def get_history(
        self,
        *,
        station: str | None = None,
        district: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[RiverObservation]:
        """Return historical observations matching the supplied filters."""
        ...


class UnconfiguredRepository:
    """Explicit placeholder until Layer 1.3B configures PostgreSQL."""

    def save_observations(self, observations: Sequence[RiverObservation]) -> int:
        raise RuntimeError(
            "Historical storage is not configured yet. "
            "Configure the Layer 1.3B PostgreSQL repository first."
        )

    def get_history(
        self,
        *,
        station: str | None = None,
        district: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[RiverObservation]:
        raise RuntimeError(
            "Historical storage is not configured yet. "
            "Configure the Layer 1.3B PostgreSQL repository first."
        )
