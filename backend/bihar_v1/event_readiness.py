"""Flood-event coverage diagnostics for Bihar v1."""
from __future__ import annotations

import pandas as pd


def summarize_event_coverage(
    events: pd.DataFrame,
    *,
    district: str,
    start_column: str = "start",
    end_column: str = "end",
    event_id_column: str = "uei",
) -> dict:
    """Summarize independent flood events and their temporal distribution.

    This is diagnostic only. It does not convert district-event records into
    additional events and does not infer missing event dates.
    """
    required = {"district", start_column, end_column}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"Event frame missing columns: {sorted(missing)}")
    resolved_event_id = event_id_column
    if resolved_event_id not in events.columns:
        lowered = {str(column).strip().lower(): column for column in events.columns}
        resolved_event_id = lowered.get(event_id_column.strip().lower())
        if resolved_event_id is None:
            raise ValueError(f"Event frame missing columns: ['{event_id_column}']")

    frame = events[events["district"] == district].copy()
    if frame.empty:
        return {
            "district": district,
            "records": 0,
            "unique_events": 0,
            "start": None,
            "end": None,
            "events_by_year": {},
            "event_ids": [],
        }

    frame[start_column] = pd.to_datetime(frame[start_column], utc=True, errors="coerce")
    frame[end_column] = pd.to_datetime(frame[end_column], utc=True, errors="coerce")
    frame = frame.dropna(subset=[start_column, end_column, resolved_event_id])
    frame = frame.drop_duplicates(subset=[resolved_event_id])

    years = frame[start_column].dt.year.value_counts().sort_index()
    return {
        "district": district,
        "records": int(len(events[events["district"] == district])),
        "unique_events": int(len(frame)),
        "start": frame[start_column].min().isoformat() if len(frame) else None,
        "end": frame[end_column].max().isoformat() if len(frame) else None,
        "events_by_year": {str(int(year)): int(count) for year, count in years.items()},
        "event_ids": sorted(frame[resolved_event_id].astype(str).tolist()),
    }
