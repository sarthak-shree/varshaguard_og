"""Historical event-label generation for Bihar v1.

Labels are built from the supplied Bihar district-event inventory. A positive
sample at time t means a flood event for that district is documented to START
within the next 24 hours. Ongoing events are not counted as new positives.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


def _parse_inventory_datetime(value: object) -> pd.Timestamp:
    """Parse the inventory's dd/mm/yy dates without pandas' 1969/2068 pivot.

    The inventory uses two-digit years spanning 1967-2023. We therefore map
    67-99 to 1967-1999 and 00-68 to 2000-2068 explicitly.
    """
    text = str(value).strip()
    if not text:
        return pd.NaT
    try:
        date_part, time_part = text.split(maxsplit=1)
    except ValueError:
        date_part, time_part = text, "00:00"
    day, month, year = [int(x) for x in date_part.split("/")[:3]]
    year = 1900 + year if year >= 67 else 2000 + year
    return pd.Timestamp(datetime(year, month, day, *[int(x) for x in time_part.split(":")[:2]]))


def load_district_events(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"Start Date", "End Date", "Bihar District", "UEI"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")

    out = frame.copy()
    out["start"] = out["Start Date"].map(_parse_inventory_datetime)
    out["end"] = out["End Date"].map(_parse_inventory_datetime)
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
        start = pd.Timestamp(row.start).tz_localize("UTC")
        end = pd.Timestamp(row.end).tz_localize("UTC")
        target["flood_event_start_next_24h"] |= (
            (target["timestamp"] < start) &
            (target["timestamp"] >= start - horizon)
        )
        target["flood_event_ongoing"] |= (
            (target["timestamp"] >= start) &
            (target["timestamp"] <= end)
        )

    target["flood_event_start_next_24h"] = target["flood_event_start_next_24h"].astype("int8")
    target["flood_event_ongoing"] = target["flood_event_ongoing"].astype("int8")
    return target
