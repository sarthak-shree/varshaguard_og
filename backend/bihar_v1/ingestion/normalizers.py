"""Normalize Bihar source tables into the provider-neutral Observation contract."""
import pandas as pd
from ..schemas import Observation


def _text(value) -> str | None:
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def _normalize_timestamps(series: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(series, dayfirst=True, errors="coerce")
    if timestamps.isna().any():
        raise ValueError("Source file contains invalid timestamps")
    return timestamps


def normalize_rainfall_csv(frame: pd.DataFrame, *, value_column: str) -> list[Observation]:
    required = {"District", "Station", "Data Acquisition Time", value_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing rainfall columns: {sorted(missing)}")

    timestamps = _normalize_timestamps(frame["Data Acquisition Time"])
    raw_values = frame[value_column]
    values = pd.to_numeric(raw_values, errors="coerce")
    invalid_values = values.isna() & raw_values.notna()
    if invalid_values.any():
        raise ValueError("Source file contains non-numeric values")
    if (values.dropna() < 0).any():
        raise ValueError("Rainfall observations cannot be negative")
    out = []
    for idx, ts in timestamps.items():
        row = frame.loc[idx]
        value = values.loc[idx]
        district = _text(row["District"])
        out.append(Observation(
            timestamp=ts.tz_localize("Asia/Kolkata").tz_convert("UTC").isoformat(),
            district=(district or "").strip().lower().replace(" ", "_"),
            variable="rain_mm",
            value=None if pd.isna(value) else float(value),
            unit="mm",
            source=str(row.get("Agency") or "unknown").lower(),
            station_id=_text(row.get("Station")),
            quality="unknown",
            metadata={
                "latitude": _text(row.get("Latitude")),
                "longitude": _text(row.get("Longitude")),
                "raw_district": district,
            },
        ))
    return out


def normalize_river_csv(frame: pd.DataFrame, *, value_column: str) -> list[Observation]:
    required = {"District", "Station", "Data Acquisition Time", value_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing river columns: {sorted(missing)}")

    timestamps = _normalize_timestamps(frame["Data Acquisition Time"])
    raw_values = frame[value_column]
    values = pd.to_numeric(raw_values, errors="coerce")
    invalid_values = values.isna() & raw_values.notna()
    if invalid_values.any():
        raise ValueError("Source file contains non-numeric values")
    out = []
    for idx, ts in timestamps.items():
        row = frame.loc[idx]
        value = values.loc[idx]
        district = _text(row["District"])
        out.append(Observation(
            timestamp=ts.tz_localize("Asia/Kolkata").tz_convert("UTC").isoformat(),
            district=(district or "").strip().lower().replace(" ", "_"),
            variable="river_level_m",
            value=None if pd.isna(value) else float(value),
            unit="m",
            source=str(row.get("Agency") or "unknown").lower(),
            station_id=_text(row.get("Station")),
            quality="unknown",
            metadata={
                "latitude": _text(row.get("Latitude")),
                "longitude": _text(row.get("Longitude")),
                "river": _text(row.get("River")),
                "raw_district": district,
            },
        ))
    return out
