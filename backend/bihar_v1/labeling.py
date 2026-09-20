"""Historical event-label generation for Bihar v1.

Labels are built from the supplied Bihar district-event inventory. A positive
sample at time t means a flood event for that district is documented to START
within the next 24 hours. Ongoing events are not counted as new positives.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


def _parse_inventory_datetime(value: object) -> pd.Timestamp:
    """Parse common Bihar inventory date formats with an explicit year policy."""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return pd.NaT

    parts = text.split(maxsplit=1)
    date_part = parts[0].replace("-", "/")
    time_part = parts[1] if len(parts) == 2 else "00:00"

    fields = [x for x in re.split(r"/", date_part) if x]
    if len(fields) != 3:
        return pd.NaT

    try:
        day, month, year = (int(x) for x in fields)
        hour_minute = [int(x) for x in re.split(r":", time_part)[:2]]
        hour = hour_minute[0] if hour_minute else 0
        minute = hour_minute[1] if len(hour_minute) > 1 else 0
    except (TypeError, ValueError):
        return pd.NaT

    if year < 100:
        year = 1900 + year if year >= 67 else 2000 + year

    try:
        return pd.Timestamp(datetime(year, month, day, hour, minute))
    except ValueError:
        return pd.NaT


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
    out["UEI"] = out["UEI"].astype(str).str.strip()
    if out["UEI"].eq("").any():
        raise ValueError("Flood inventory contains empty UEI values")
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
    target["flood_event_uei"] = pd.Series(pd.NA, index=target.index, dtype="string")
    target["flood_event_start_timestamp"] = pd.NaT

    horizon = pd.Timedelta(hours=horizon_hours)
    for row in selected.itertuples(index=False):
        start = pd.Timestamp(row.start)
        end = pd.Timestamp(row.end)
        if start.tzinfo is None:
            start = start.tz_localize("UTC")
        else:
            start = start.tz_convert("UTC")
        if end.tzinfo is None:
            end = end.tz_localize("UTC")
        else:
            end = end.tz_convert("UTC")

        lead_mask = (
            (target["timestamp"] < start)
            & (target["timestamp"] >= start - horizon)
        )
        ongoing_mask = (
            (target["timestamp"] >= start)
            & (target["timestamp"] <= end)
        )
        target.loc[lead_mask, "flood_event_start_next_24h"] = True
        target.loc[lead_mask, "flood_event_uei"] = str(row.UEI)
        target.loc[lead_mask, "flood_event_start_timestamp"] = start
        target.loc[ongoing_mask, "flood_event_ongoing"] = True

    target["flood_event_start_next_24h"] = target["flood_event_start_next_24h"].astype("int8")
    target["flood_event_ongoing"] = target["flood_event_ongoing"].astype("int8")
    return target
