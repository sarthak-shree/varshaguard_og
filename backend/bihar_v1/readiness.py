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
