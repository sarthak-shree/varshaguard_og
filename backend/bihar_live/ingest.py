"""Layer 1.1: fetch and normalize live Bihar river observations."""

from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests

from .source import EXPECTED_FIELDS, SOURCE_URL


REQUEST_TIMEOUT_SECONDS = 20


def _clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).split())


def _to_float(value):
    if pd.isna(value):
        return None
    text = _clean_text(value).replace(",", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _find_column(columns, candidates):
    normalized = {" ".join(str(col).lower().split()): col for col in columns}
    for candidate in candidates:
        key = " ".join(candidate.lower().split())
        if key in normalized:
            return normalized[key]
    for col in columns:
        name = " ".join(str(col).lower().split())
        if any(candidate.lower() in name for candidate in candidates):
            return col
    return None


def _normalize_table(table: pd.DataFrame) -> list[dict]:
    columns = list(table.columns)
    river_col = _find_column(columns, ["river", "river name"])
    station_col = _find_column(columns, ["site", "station", "station name", "gauge site"])
    district_col = _find_column(columns, ["district"])
    level_col = _find_column(columns, ["gauge", "water level", "current water level"])
    warning_col = _find_column(columns, ["warning"])
    danger_col = _find_column(columns, ["danger"])
    hfl_col = _find_column(columns, ["hfl", "highest flood level"])
    trend_col = _find_column(columns, ["trend"])
    status_col = _find_column(columns, ["status", "level status"])
    observed_col = _find_column(columns, ["date/time", "date time", "observation time", "time"])

    required = {
        "river": river_col,
        "station": station_col,
        "district": district_col,
        "water_level_m": level_col,
    }
    missing = [name for name, col in required.items() if col is None]
    if missing:
        raise ValueError(
            "Could not identify required live-river columns: " + ", ".join(missing)
        )

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for _, row in table.iterrows():
        river = _clean_text(row[river_col])
        station = _clean_text(row[station_col])
        district = _clean_text(row[district_col])
        water_level = _to_float(row[level_col])

        if not river or not station or not district or water_level is None:
            continue

        observed_at = _clean_text(row[observed_col]) if observed_col else ""
        rows.append(
            {
                "river": river,
                "station": station,
                "district": district,
                "water_level_m": water_level,
                "warning_level_m": _to_float(row[warning_col]) if warning_col else None,
                "danger_level_m": _to_float(row[danger_col]) if danger_col else None,
                "hfl_m": _to_float(row[hfl_col]) if hfl_col else None,
                "trend": _clean_text(row[trend_col]) if trend_col else "",
                "status": _clean_text(row[status_col]) if status_col else "",
                "observed_at": observed_at,
                "fetched_at": now,
            }
        )

    return rows


def fetch_live_river_observations() -> dict:
    """Fetch the public live-river table and return normalized records."""
    response = requests.get(
        SOURCE_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "VARSHAGUARD/0.3 Bihar Live Prototype"},
    )
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise ValueError("No table found in the Bihar FMISC/WRD response")

    largest = max(tables, key=lambda frame: frame.shape[0] * max(frame.shape[1], 1))
    records = _normalize_table(largest)

    return {
        "success": True,
        "source": "Bihar FMISC/WRD",
        "source_url": SOURCE_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "records": records,
        "fields": list(EXPECTED_FIELDS),
    }
