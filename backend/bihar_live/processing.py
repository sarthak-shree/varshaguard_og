"""Layer 1.2: validate and derive useful river-level features."""

from __future__ import annotations

from collections.abc import Iterable


VALID_TRENDS = {"rising", "steady", "falling"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clean_trend(value) -> str:
    return str(value or "").strip().lower()


def _safe_difference(current, previous):
    if not _number(current) or not _number(previous):
        return None
    return round(float(current) - float(previous), 3)


def _level_state(water_level, warning_level, danger_level) -> str:
    if _number(danger_level) and water_level >= danger_level:
        return "ABOVE_DANGER"
    if _number(warning_level) and water_level >= warning_level:
        return "ABOVE_WARNING"
    return "BELOW_WARNING"


def _percent_of_level(water_level, reference_level):
    if not _number(reference_level) or reference_level == 0:
        return None
    return round((water_level / reference_level) * 100.0, 2)


def process_river_records(records: Iterable[dict]) -> list[dict]:
    """Return validated records enriched with deterministic river-level features."""
    processed = []
    seen = set()

    for record in records:
        river = str(record.get("river") or "").strip()
        station = str(record.get("station") or "").strip()
        district = str(record.get("district") or "").strip()
        water_level = record.get("water_level_m")

        if not river or not station or not district or not _number(water_level):
            continue

        identity = (river.casefold(), station.casefold(), district.casefold())
        if identity in seen:
            continue
        seen.add(identity)

        warning_level = record.get("warning_level_m")
        danger_level = record.get("danger_level_m")
        hfl = record.get("hfl_m")
        previous = record.get("water_level_1h_before_m")

        rise_1h = _safe_difference(water_level, previous)
        trend = _clean_trend(record.get("trend"))
        trend_valid = trend in VALID_TRENDS

        item = dict(record)
        item.update(
            {
                "trend_normalized": trend,
                "trend_valid": trend_valid,
                "rise_1h_m": rise_1h,
                "rise_rate_m_per_hour": rise_1h,
                "distance_to_warning_m": (
                    round(float(water_level) - float(warning_level), 3)
                    if _number(warning_level)
                    else None
                ),
                "distance_to_danger_m": (
                    round(float(water_level) - float(danger_level), 3)
                    if _number(danger_level)
                    else None
                ),
                "warning_level_pct": _percent_of_level(water_level, warning_level),
                "danger_level_pct": _percent_of_level(water_level, danger_level),
                "hfl_level_pct": _percent_of_level(water_level, hfl),
                "level_state": _level_state(water_level, warning_level, danger_level),
                "has_previous_hour": _number(previous),
                "processing_valid": True,
            }
        )
        processed.append(item)

    return processed
