"""Synchronized feature-source readiness metrics for Bihar v1."""
from __future__ import annotations

import pandas as pd


def summarize_synchronized_hourly_coverage(
    rainfall: pd.DataFrame,
    river: pd.DataFrame,
    *,
    station_pairs: set[tuple[str, str]] | None = None,
    window_hours: int = 168,
) -> dict:
    """Measure hours where both rainfall and river inputs coexist.

    Coverage is computed only for explicitly mapped station pairs and never
    treats missing source data as zero. If an empty mapping is supplied, no
    synchronization is inferred from timestamps alone.
    """
    if window_hours < 1:
        raise ValueError("window_hours must be positive")
    if station_pairs is not None:
        station_pairs = {(str(rain), str(river)) for rain, river in station_pairs}
    if rainfall.empty or river.empty or station_pairs == set():
        return {
            "rainfall_rows": int(len(rainfall)),
            "river_rows": int(len(river)),
            "synchronized_hours": 0,
            "stations": [],
            "stations_with_continuous_window": 0,
            "usable_continuous_windows": 0,
            "window_hours": window_hours,
            "station_mapping": "explicit" if station_pairs is not None else "unmapped_timestamp_only",
        }

    required = {"timestamp", "station_id"}
    for name, frame in (("rainfall", rainfall), ("river", river)):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{name} frame missing columns: {sorted(missing)}")

    rain = rainfall.copy()
    riv = river.copy()
    rain["timestamp"] = pd.to_datetime(rain["timestamp"], utc=True, errors="raise")
    riv["timestamp"] = pd.to_datetime(riv["timestamp"], utc=True, errors="raise")
    # A timestamp with a missing measurement is not usable synchronized evidence.
    # Keep compatibility with diagnostic frames that omit value columns entirely.
    if "value" in rain.columns:
        rain = rain[rain["value"].notna()].copy()
    if "value" in riv.columns:
        riv = riv[riv["value"].notna()].copy()
    if rain.empty or riv.empty:
        return {
            "rainfall_rows": int(len(rainfall)),
            "river_rows": int(len(river)),
            "synchronized_hours": 0,
            "stations": [],
            "stations_with_continuous_window": 0,
            "usable_continuous_windows": 0,
            "window_hours": window_hours,
        }

    rain_keys = rain[["timestamp", "station_id"]].drop_duplicates()
    riv_keys = riv[["timestamp", "station_id"]].drop_duplicates()

    # A station identifier is source-specific, so synchronize by timestamp
    # first and report the station combinations actually observed.
    rain_keys = rain_keys.rename(columns={"station_id": "rainfall_station"})
    riv_keys = riv_keys.rename(columns={"station_id": "river_station"})
    joined = rain_keys.merge(riv_keys, on="timestamp", how="inner").drop_duplicates()
    if station_pairs is not None:
        joined = joined[
            joined[["rainfall_station", "river_station"]]
            .apply(tuple, axis=1)
            .isin(station_pairs)
        ].copy()

    station_stats = []
    for (rain_station, river_station), part in joined.groupby(
        ["rainfall_station", "river_station"], dropna=False
    ):
        timestamps = part["timestamp"].drop_duplicates().sort_values()
        longest = 1 if len(timestamps) else 0
        run = 1
        diffs = timestamps.diff().dropna().dt.total_seconds().div(3600)
        for contiguous in diffs.eq(1.0):
            run = run + 1 if contiguous else 1
            longest = max(longest, run)
        station_stats.append({
            "rainfall_station": None if pd.isna(rain_station) else str(rain_station),
            "river_station": None if pd.isna(river_station) else str(river_station),
            "synchronized_hours": int(len(timestamps)),
            "start": timestamps.min().isoformat() if len(timestamps) else None,
            "end": timestamps.max().isoformat() if len(timestamps) else None,
            "longest_contiguous_hours": int(longest),
        })

    usable_windows = sum(
        max(0, item["longest_contiguous_hours"] - window_hours + 1)
        for item in station_stats
    )
    return {
        "rainfall_rows": int(len(rainfall)),
        "river_rows": int(len(river)),
        "synchronized_hours": int(joined["timestamp"].drop_duplicates().size),
        "stations": station_stats,
        "stations_with_continuous_window": int(sum(
            item["longest_contiguous_hours"] >= window_hours for item in station_stats
        )),
        "usable_continuous_windows": int(usable_windows),
        "window_hours": window_hours,
        "station_mapping": "explicit" if station_pairs is not None else "unmapped_timestamp_only",
    }
