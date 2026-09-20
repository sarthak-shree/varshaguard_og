"""Build leakage-safe hourly training tables for Bihar v1.

The generator works from normalized hourly observations and district event labels.
It never invents missing rainfall/river values and excludes ongoing flood-event
timestamps from negative samples.
"""
from __future__ import annotations

import pandas as pd

from .feature_engineering import build_tabular_features


def build_training_table(
    observations: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    district: str,
) -> pd.DataFrame:
    required = {"timestamp", "variable", "value"}
    missing = required - set(observations.columns)
    if missing:
        raise ValueError(f"Missing observation columns: {sorted(missing)}")

    obs = observations.copy()
    obs["timestamp"] = pd.to_datetime(obs["timestamp"], utc=True, errors="raise")
    obs["value"] = pd.to_numeric(obs["value"], errors="coerce")
    obs = obs[obs["district"].astype(str).str.lower() == district.lower()].copy()

    rain = (
        obs[obs["variable"] == "rain_mm"]
        .groupby("timestamp", as_index=False)["value"].sum()
        .rename(columns={"value": "rain_mm"})
    )
    river = (
        obs[obs["variable"] == "river_level_m"]
        .groupby("timestamp", as_index=False)["value"].mean()
        .rename(columns={"value": "river_level_m"})
    )

    frame = pd.merge(rain, river, on="timestamp", how="outer").sort_values("timestamp")
    frame = build_tabular_features(frame)

    labels = labels.copy()
    labels["timestamp"] = pd.to_datetime(labels["timestamp"], utc=True, errors="raise")
    label_cols = ["timestamp", "flood_event_start_next_24h", "flood_event_ongoing"]
    frame = frame.merge(labels[label_cols], on="timestamp", how="left")

    frame["flood_event_start_next_24h"] = frame["flood_event_start_next_24h"].fillna(0).astype("int8")
    frame["flood_event_ongoing"] = frame["flood_event_ongoing"].fillna(0).astype("int8")

    # Samples during an already ongoing event are not valid negatives.
    frame = frame[frame["flood_event_ongoing"] == 0].copy()

    # Do not train rows whose 24h feature windows are incomplete.
    feature_columns = [
        "rain_1h", "rain_3h", "rain_6h", "rain_12h", "rain_24h",
        "rain_72h", "rain_168h", "river_level_m",
        "river_level_lag_1h", "river_level_lag_3h",
        "river_level_lag_6h", "river_level_lag_12h", "river_level_lag_24h",
        "river_rise_1h", "river_rise_3h", "river_rise_6h",
        "river_rise_12h", "river_rise_24h",
    ]
    available = [c for c in feature_columns if c in frame.columns]
    frame = frame.dropna(subset=available).reset_index(drop=True)
    return frame


def summarize_target(frame: pd.DataFrame) -> dict:
    if "flood_event_start_next_24h" not in frame:
        raise ValueError("Training table has no flood target")
    counts = frame["flood_event_start_next_24h"].value_counts().to_dict()
    total = len(frame)
    positives = int(counts.get(1, 0))
    return {
        "rows": total,
        "positive": positives,
        "negative": int(counts.get(0, 0)),
        "positive_rate": (positives / total) if total else 0.0,
    }
