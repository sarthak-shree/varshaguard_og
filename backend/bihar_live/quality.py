"""Data-quality helpers for Bihar Live observations and predictions."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def freshness(observed_at: str | None, now: datetime | None = None, stale_after_minutes: int = 60) -> dict:
    now = now or datetime.now(timezone.utc)
    dt = parse_iso(observed_at)
    if dt is None:
        return {"fresh": False, "age_minutes": None, "status": "unknown"}
    age = max((now - dt.astimezone(timezone.utc)).total_seconds() / 60.0, 0.0)
    return {
        "fresh": age <= stale_after_minutes,
        "age_minutes": round(age, 2),
        "status": "fresh" if age <= stale_after_minutes else "stale",
    }


def source_metadata(source: str, source_url: str, observed_at: str | None, fetched_at: str | None) -> dict:
    return {
        "source": source,
        "source_url": source_url,
        "observed_at": observed_at,
        "fetched_at": fetched_at,
    }
