"""Build leakage-safe hourly training tables for Bihar v1."""
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
        .dropna(subset=["value"])
        .groupby("timestamp", as_index=False)["value"].sum()
        .rename(columns={"value": "rain_mm"})
    )
    river = (
        obs[obs["variable"] == "river_level_m"]
        .dropna(subset=["value"])
        .groupby("timestamp", as_index=False)["value"].mean()
        .rename(columns={"value": "river_level_m"})
    )

    frame = pd.merge(rain, river, on="timestamp", how="outer").sort_values("timestamp")
    frame = build_tabular_features(frame)

    labels = labels.copy()
    labels["timestamp"] = pd.to_datetime(labels["timestamp"], utc=True, errors="raise")
    label_cols = ["timestamp", "flood_event_start_next_24h", "flood_event_ongoing"]
    if "flood_event_uei" in labels.columns:
        label_cols.append("flood_event_uei")
    frame = frame.merge(labels[label_cols], on="timestamp", how="left")

    frame["flood_event_start_next_24h"] = frame["flood_event_start_next_24h"].fillna(0).astype("int8")
    frame["flood_event_ongoing"] = frame["flood_event_ongoing"].fillna(0).astype("int8")

    # Samples during an already ongoing event are not valid negatives.
    frame = frame[frame["flood_event_ongoing"] == 0].copy()

    rainfall_features = [
        "rain_1h", "rain_3h", "rain_6h", "rain_12h", "rain_24h",
        "rain_72h", "rain_168h",
    ]
    river_features = [
        "river_level_m",
        "river_level_lag_1h", "river_level_lag_3h",
        "river_level_lag_6h", "river_level_lag_12h", "river_level_lag_24h",
        "river_rise_1h", "river_rise_3h", "river_rise_6h",
        "river_rise_12h", "river_rise_24h",
    ]
    required_features = list(rainfall_features)
    if "river_level_m" in frame.columns and frame["river_level_m"].notna().any():
        required_features.extend(river_features)

    frame = frame.dropna(subset=required_features).reset_index(drop=True)
    return frame


def summarize_target(frame: pd.DataFrame) -> dict:
    if "flood_event_start_next_24h" not in frame:
        raise ValueError("Training table has no flood target")
    counts = frame["flood_event_start_next_24h"].value_counts().to_dict()
    total = len(frame)
    positives = int(counts.get(1, 0))
    event_count = int(frame.loc[
        frame["flood_event_start_next_24h"] == 1, "flood_event_uei"
    ].dropna().nunique()) if "flood_event_uei" in frame.columns else 0
    return {
        "rows": total,
        "positive": positives,
        "negative": int(counts.get(0, 0)),
        "positive_rate": (positives / total) if total else 0.0,
        "positive_events": event_count,
    }
