"""Data-readiness metrics for Bihar v1 training datasets."""
from __future__ import annotations

import pandas as pd


def _station_hourly_stats(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    required = {"timestamp", "station_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Coverage frame missing columns: {sorted(missing)}")

    out = []
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="raise")
    for station, part in work.groupby("station_id", dropna=False):
        timestamps = part["timestamp"].drop_duplicates().sort_values()
        if timestamps.empty:
            continue
        diffs = timestamps.diff().dropna().dt.total_seconds().div(3600)
        contiguous = diffs.eq(1.0)
        run = 1
        longest = 1
        for is_contiguous in contiguous:
            run = run + 1 if is_contiguous else 1
            longest = max(longest, run)
        start, end = timestamps.min(), timestamps.max()
        span_hours = int((end - start).total_seconds() // 3600) + 1
        unique_hours = int(len(timestamps))
        out.append({
            "station_id": None if pd.isna(station) else str(station),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "span_hours": span_hours,
            "unique_hours": unique_hours,
            "hourly_coverage_ratio": unique_hours / span_hours if span_hours else 0.0,
            "longest_contiguous_hours": int(longest),
        })
    return out


def summarize_hourly_coverage(
    frame: pd.DataFrame,
    *,
    continuous_window_hours: int = 168,
) -> dict:
    """Summarize raw, unique-hour, and continuous-window coverage.

    Duplicate records are not counted as additional hourly coverage.
    """
    if continuous_window_hours < 1:
        raise ValueError("continuous_window_hours must be positive")
    if frame.empty:
        return {
            "rows": 0,
            "unique_hours": 0,
            "duplicate_rows": 0,
            "stations": [],
            "stations_with_continuous_window": 0,
            "continuous_window_hours": continuous_window_hours,
            "usable_continuous_windows": 0,
        }

    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="raise")
    key = work["timestamp"].astype("string") + "|" + work["station_id"].astype("string")
    duplicate_rows = int(key.duplicated().sum())
    stats = _station_hourly_stats(work)
    usable_windows = sum(
        max(0, item["longest_contiguous_hours"] - continuous_window_hours + 1)
        for item in stats
    )
    return {
        "rows": int(len(work)),
        "unique_hours": int(work["timestamp"].drop_duplicates().size),
        "duplicate_rows": duplicate_rows,
        "stations": stats,
        "stations_with_continuous_window": int(sum(
            item["longest_contiguous_hours"] >= continuous_window_hours for item in stats
        )),
        "continuous_window_hours": continuous_window_hours,
        "usable_continuous_windows": int(usable_windows),
    }


def summarize_training_window_coverage(table: pd.DataFrame) -> dict:
    """Measure rows surviving the engineered feature windows."""
    if table.empty:
        return {"rows": 0, "complete_feature_rows": 0, "feature_window_coverage_ratio": 0.0}

    window_columns = [
        column for column in (
            "rain_1h", "rain_3h", "rain_6h", "rain_12h",
            "rain_24h", "rain_72h", "rain_168h",
            "river_level_lag_1h", "river_level_lag_3h",
            "river_level_lag_6h", "river_level_lag_12h",
            "river_level_lag_24h",
        ) if column in table.columns
    ]
    if not window_columns:
        return {
            "rows": int(len(table)),
            "complete_feature_rows": 0,
            "feature_window_coverage_ratio": 0.0,
            "feature_columns_checked": [],
        }
    complete = table[window_columns].notna().all(axis=1)
    count = int(complete.sum())
    return {
        "rows": int(len(table)),
        "complete_feature_rows": count,
        "feature_window_coverage_ratio": count / len(table),
        "feature_columns_checked": window_columns,
    }


def build_model_readiness(
    *,
    district: str,
    rainfall_hourly: pd.DataFrame,
    river: pd.DataFrame,
    event_inventory: dict,
    synchronized_hourly: dict,
    evaluation_ready: bool,
    evaluation_reason: str | None,
    continuous_window_hours: int = 168,
    minimum_independent_events: int = 5,
) -> dict:
    """Return explicit trainability blockers for each Bihar v1 model.

    This gate is intentionally conservative. Flood-event labels are not
    treated as heavy-rainfall labels, and river observations are not treated
    as threshold exceedances without an official danger threshold.
    """
    rainfall_coverage = summarize_hourly_coverage(
        rainfall_hourly,
        continuous_window_hours=continuous_window_hours,
    )
    river_coverage = summarize_hourly_coverage(
        river,
        continuous_window_hours=continuous_window_hours,
    )
    event_count = int(event_inventory.get("unique_events", 0))

    heavy_rainfall = []
    if rainfall_hourly.empty:
        heavy_rainfall.append("No supported hourly rainfall observations are available.")
    elif rainfall_coverage["stations_with_continuous_window"] == 0:
        heavy_rainfall.append(
            f"No station has a {continuous_window_hours}-hour continuous rainfall window."
        )
    heavy_rainfall.append(
        "No documented heavy-rainfall target/label definition is included in the current supervised dataset."
    )

    river_flood = []
    if river.empty:
        river_flood.append("No supported river-level observations are available.")
    elif river_coverage["stations_with_continuous_window"] == 0:
        river_flood.append(
            f"No station has a {continuous_window_hours}-hour continuous river-level window."
        )
    if synchronized_hourly.get("stations_with_continuous_window", 0) == 0:
        river_flood.append(
            f"No synchronized rainfall/river station pair has a {continuous_window_hours}-hour continuous window."
        )
    if event_count < minimum_independent_events:
        river_flood.append(
            f"Only {event_count} independent flood events are available; at least {minimum_independent_events} are required for the evaluation gate."
        )
    if not evaluation_ready:
        river_flood.append(
            evaluation_reason or "Chronological train/validation/test evaluation readiness is not satisfied."
        )
    river_flood.append(
        "Official river danger-level/threshold data is not included, so event-start labels cannot be treated as river-threshold exceedance labels."
    )

    inundation = [
        "Historical Sentinel-1 inundation masks are not included.",
        "Static terrain/DEM features are not included.",
    ]

    models = {
        "heavy_rainfall": heavy_rainfall,
        "river_flood": river_flood,
        "inundation": inundation,
    }
    return {
        "district": district,
        "status": "ready" if all(not reasons for reasons in models.values()) else "blocked",
        "models": {
            name: {
                "status": "ready" if not reasons else "blocked",
                "reasons": reasons,
            }
            for name, reasons in models.items()
        },
        "requirements": {
            "continuous_window_hours": continuous_window_hours,
            "minimum_independent_events": minimum_independent_events,
        },
        "evidence": {
            "rainfall_hourly_rows": int(len(rainfall_hourly)),
            "river_rows": int(len(river)),
            "independent_flood_events": event_count,
            "synchronized_stations_with_continuous_window": int(
                synchronized_hourly.get("stations_with_continuous_window", 0)
            ),
        },
    }
