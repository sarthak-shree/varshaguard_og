"""Transparent baseline forecasts for VarshaGuard.

These functions deliberately do not train an ML model. A defensible trained rainfall
or stage model requires aligned historical inputs and future labels; the current live
feeds alone do not provide that validated training set. Provider NWP rainfall is
reported as a forecast, while stage extrapolation is labelled an unvalidated baseline.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30))
STAGE_HORIZONS_HOURS = (1, 3, 6, 12)


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    return parsed.astimezone(IST)


def rainfall_summary(hourly: list[dict], district: str, source: str = "Open-Meteo") -> dict:
    """Summarize already time-aligned hourly rainfall forecast rows."""
    rows = []
    for item in hourly if isinstance(hourly, list) else []:
        stamp = _parse_timestamp(item.get("time") or item.get("time_ist"))
        try:
            rain = float(item.get("precipitation_mm"))
        except (TypeError, ValueError, OverflowError):
            continue
        if stamp is None or not math.isfinite(rain) or rain < 0:
            continue
        chance = item.get("precipitation_probability_pct")
        try:
            chance = float(chance) if chance is not None else None
        except (TypeError, ValueError, OverflowError):
            chance = None
        rows.append((stamp, rain, chance))
    rows.sort(key=lambda row: row[0])
    if not rows:
        return {
            "success": True, "available": False, "district": district,
            "source": source, "message": "No valid hourly rainfall forecast rows are available.",
            "operational": False,
        }
    first = rows[0][0]
    window_rows = {
        str(hours): [row for row in rows if first <= row[0] < first + timedelta(hours=hours)]
        for hours in (1, 3, 6, 12, 24)
    }
    totals = {hours: round(sum(row[1] for row in selected), 1) for hours, selected in window_rows.items()}
    peak = max((row[1] for row in rows[:24]), default=None)
    peak_chance = max((row[2] for row in rows[:24] if row[2] is not None), default=None)
    return {
        "success": True,
        "available": True,
        "district": district,
        "source": source,
        "forecast_model": "Open-Meteo numerical weather prediction (provider forecast; not a locally trained ML model)",
        "forecast_start_ist": rows[0][0].isoformat(timespec="minutes"),
        "forecast_end_ist": rows[min(23, len(rows) - 1)][0].isoformat(timespec="minutes"),
        "valid_hour_count": len(rows),
        "rainfall_accumulation_mm": {f"next_{hours}h": value for hours, value in totals.items()},
        "peak_hourly_rainfall_mm": round(peak, 1) if peak is not None else None,
        "maximum_precipitation_chance_pct": round(peak_chance) if peak_chance is not None else None,
        "hourly_forecast": [
            {
                "time_ist": stamp.isoformat(timespec="minutes"),
                "precipitation_mm": round(rain, 2),
                "precipitation_probability_pct": round(chance) if chance is not None else None,
            }
            for stamp, rain, chance in rows[:24]
        ],
        "validation": {
            "validated_on_independent_local_rain_gauge_labels": False,
            "status": "provider_forecast_context_not_locally_validated",
        },
        "operational": False,
        "note": "Rainfall amount is forecast context, not a probability of heavy rain or flooding. Accumulations are derived from the hourly provider forecast.",
    }


def project_stage_trend(
    history: list[dict],
    warning_level_m: float | None = None,
    horizons_hours: tuple[int, ...] = STAGE_HORIZONS_HOURS,
) -> dict:
    """Fit a transparent least-squares trend to recent observed stage readings."""
    points = []
    for item in history if isinstance(history, list) else []:
        stamp = _parse_timestamp(item.get("timestamp_ist") or item.get("time"))
        try:
            stage = float(item.get("stage_m"))
        except (TypeError, ValueError, OverflowError):
            continue
        if stamp is None or not math.isfinite(stage):
            continue
        points.append((stamp, stage))
    points.sort(key=lambda point: point[0])
    # Keep only the most recent 24 hours, deduplicated by timestamp.
    unique = {}
    for stamp, stage in points:
        unique[stamp] = stage
    points = sorted(unique.items())[-100:]
    if len(points) < 3:
        return {
            "success": True, "available": False, "method": "linear_trend_baseline",
            "message": "At least three distinct recent stage readings are required.",
            "operational": False, "validated": False,
        }
    origin = points[-1][0]
    points = [(stamp, stage) for stamp, stage in points if (origin - stamp).total_seconds() <= 24 * 3600]
    if len(points) < 3 or (points[-1][0] - points[0][0]).total_seconds() < 2 * 3600:
        return {
            "success": True, "available": False, "method": "linear_trend_baseline",
            "message": "Recent readings must span at least two hours before a trend can be estimated.",
            "operational": False, "validated": False,
        }
    xs = [(stamp - points[0][0]).total_seconds() / 3600 for stamp, _ in points]
    ys = [stage for _, stage in points]
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    denominator = sum((x - xbar) ** 2 for x in xs)
    if denominator <= 0:
        return {
            "success": True, "available": False, "method": "linear_trend_baseline",
            "message": "Readings do not span a usable time range.",
            "operational": False, "validated": False,
        }
    slope = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / denominator
    intercept = ybar - slope * xbar
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    rmse = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    latest_stage = ys[-1]
    elapsed_hours = xs[-1]
    forecast = []
    for hours in horizons_hours:
        projected = intercept + slope * (elapsed_hours + hours)
        row = {"horizon_hours": hours, "projected_stage_m": round(projected, 3)}
        if warning_level_m is not None and math.isfinite(float(warning_level_m)):
            row["warning_level_m"] = round(float(warning_level_m), 3)
            row["trend_crosses_warning"] = projected >= float(warning_level_m)
        forecast.append(row)
    return {
        "success": True,
        "available": True,
        "method": "ordinary_least_squares_recent_stage_trend",
        "forecast_model": "Unvalidated linear trend baseline; not a trained ML model",
        "observations_used": len(points),
        "history_start_ist": points[0][0].isoformat(timespec="minutes"),
        "latest_observation_ist": points[-1][0].isoformat(timespec="minutes"),
        "latest_stage_m": round(latest_stage, 3),
        "trend_m_per_hour": round(slope, 5),
        "trend_direction": "rising" if slope > 0.005 else "falling" if slope < -0.005 else "near_steady",
        "in_sample_residual_rmse_m": round(rmse, 3),
        "residual_rmse_note": "In-sample diagnostic only; not a forecast confidence interval.",
        "forecasts": forecast,
        "validation": {"chronological_backtest_complete": False, "status": "research_baseline_not_validated"},
        "operational": False,
        "message": "Linear extrapolation can fail when rainfall, upstream releases, or river routing change. Follow official CWC and local authority updates.",
    }
