"""Historical event-label generation for Bihar v1.

Labels are built from the supplied Bihar district-event inventory. A positive
sample at time t means a flood event for that district is documented to START
within the next 24 hours. Ongoing events are not counted as new positives.
This avoids using future event duration as a hidden feature.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd


def load_district_events(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"Start Date", "End Date", "Bihar District", "UEI"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")

    out = frame.copy()
    out["start"] = pd.to_datetime(out["Start Date"], dayfirst=True, errors="coerce")
    out["end"] = pd.to_datetime(out["End Date"], dayfirst=True, errors="coerce")
    if out[["start", "end"]].isna().any().any():
        raise ValueError("Flood inventory contains invalid event dates")
    out["district"] = (
        out["Bihar District"].astype(str).str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
    )
    if (out["end"] < out["start"]).any():
        raise ValueError("Flood inventory contains events ending before they start")
    return out


def build_24h_event_labels(
    timestamps: pd.Series,
    events: pd.DataFrame,
    *,
    district: str,
    horizon_hours: int = 24,
) -> pd.DataFrame:
    if horizon_hours <= 0:
        raise ValueError("horizon_hours must be positive")

    ts = pd.to_datetime(timestamps, utc=True, errors="raise")
    target = pd.DataFrame({"timestamp": ts}).sort_values("timestamp").reset_index(drop=True)
    district_key = district.strip().lower().replace(" ", "_")
    selected = events[events["district"] == district_key]

    target["flood_event_start_next_24h"] = False
    target["flood_event_ongoing"] = False

    horizon = pd.Timedelta(hours=horizon_hours)
    for row in selected.itertuples(index=False):
        target["flood_event_start_next_24h"] |= (
            (target["timestamp"] < row.start.tz_localize("UTC")) &
            (target["timestamp"] >= row.start.tz_localize("UTC") - horizon)
        )
        target["flood_event_ongoing"] |= (
            (target["timestamp"] >= row.start.tz_localize("UTC")) &
            (target["timestamp"] <= row.end.tz_localize("UTC"))
        )

    target["flood_event_start_next_24h"] = target["flood_event_start_next_24h"].astype("int8")
    target["flood_event_ongoing"] = target["flood_event_ongoing"].astype("int8")
    return target
