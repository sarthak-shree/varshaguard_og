"""Normalize Bihar source tables into the provider-neutral Observation contract."""
from typing import Iterable
import pandas as pd
from ..schemas import Observation


def _text(value) -> str | None:
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def normalize_rainfall_csv(frame: pd.DataFrame, *, value_column: str) -> list[Observation]:
    required = {"District", "Station", "Data Acquisition Time", value_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing rainfall columns: {sorted(missing)}")
    timestamps = pd.to_datetime(frame["Data Acquisition Time"], dayfirst=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("Rainfall file contains invalid timestamps")
    out = []
    for row, ts in zip(frame.itertuples(index=False), timestamps):
        record = row._asdict()
        district = _text(record["District"])
        value = pd.to_numeric(pd.Series([record[value_column]]), errors="coerce").iloc[0]
        out.append(Observation(
            timestamp=ts.tz_localize("Asia/Kolkata").tz_convert("UTC").isoformat(),
            district=(district or "").strip().lower().replace(" ", "_"),
            variable="rain_mm",
            value=None if pd.isna(value) else float(value),
            unit="mm",
            source=str(record.get("Agency") or "unknown").lower(),
            station_id=_text(record.get("Station")),
            quality="unknown",
            metadata={
                "latitude": _text(record.get("Latitude")),
                "longitude": _text(record.get("Longitude")),
                "raw_district": district,
            },
        ))
    return out


def normalize_river_csv(frame: pd.DataFrame, *, value_column: str) -> list[Observation]:
    required = {"District", "Station", "Data Acquisition Time", value_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing river columns: {sorted(missing)}")
    timestamps = pd.to_datetime(frame["Data Acquisition Time"], dayfirst=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("River file contains invalid timestamps")
    out = []
    for row, ts in zip(frame.itertuples(index=False), timestamps):
        record = row._asdict()
        district = _text(record["District"])
        value = pd.to_numeric(pd.Series([record[value_column]]), errors="coerce").iloc[0]
        out.append(Observation(
            timestamp=ts.tz_localize("Asia/Kolkata").tz_convert("UTC").isoformat(),
            district=(district or "").strip().lower().replace(" ", "_"),
            variable="river_level_m",
            value=None if pd.isna(value) else float(value),
            unit="m",
            source=str(record.get("Agency") or "unknown").lower(),
            station_id=_text(record.get("Station")),
            quality="unknown",
            metadata={
                "latitude": _text(record.get("Latitude")),
                "longitude": _text(record.get("Longitude")),
                "river": _text(record.get("River")),
                "raw_district": district,
            },
        ))
    return out
