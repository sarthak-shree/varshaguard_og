"""Canonical local dataset audit for Bihar v1.

Run with paths to the user's CSV exports. This tool reports schema, date coverage,
district/station coverage, missingness and duplicate timestamps without modifying
the source files.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


RAIN_HOURLY_COL = "Telemetry Hourly Rainfall (mm)"
RAIN_DAILY_COL = "Manual Daily Rainfall (mm)"
RIVER_HOURLY_COL = "River Water Level Telemetry Hourly (meter)"


def audit_csv(path: str | Path) -> dict:
    path = Path(path)
    frame = pd.read_csv(path)
    result = {
        "file": str(path),
        "rows": int(len(frame)),
        "columns": list(frame.columns),
    }

    if "Data Acquisition Time" in frame:
        ts = pd.to_datetime(frame["Data Acquisition Time"], dayfirst=True, errors="coerce")
        result["invalid_timestamps"] = int(ts.isna().sum())
        if ts.notna().any():
            result["start"] = str(ts.min())
            result["end"] = str(ts.max())
            result["unique_days"] = int(ts.dt.normalize().nunique())

    for col in ("District", "Station", "River", "Agency"):
        if col in frame:
            values = frame[col].dropna().astype(str).str.strip()
            result[f"unique_{col.lower()}"] = int(values.nunique())

    if "District" in frame:
        result["districts"] = sorted(frame["District"].dropna().astype(str).str.strip().unique().tolist())

    if "Station" in frame:
        counts = (
            frame["Station"].dropna().astype(str).str.strip()
            .value_counts()
            .head(25)
            .to_dict()
        )
        result["top_stations"] = {str(k): int(v) for k, v in counts.items()}

    candidate_value_cols = [RAIN_HOURLY_COL, RAIN_DAILY_COL, RIVER_HOURLY_COL]
    for col in candidate_value_cols:
        if col in frame:
            values = pd.to_numeric(frame[col], errors="coerce")
            result[col] = {
                "missing": int(values.isna().sum()),
                "non_numeric": int(values.isna().sum() - frame[col].isna().sum()),
                "min": None if values.dropna().empty else float(values.min()),
                "max": None if values.dropna().empty else float(values.max()),
            }

    if "Data Acquisition Time" in frame and "Station" in frame:
        key_columns = ["Station", "Data Acquisition Time"]
        if "Agency" in frame:
            key_columns.append("Agency")
        key = frame[key_columns].astype("string").fillna("<missing>").agg("|".join, axis=1)
        result["duplicate_observation_keys"] = int(key.duplicated().sum())
        result["duplicate_observation_rows"] = int(key.duplicated(keep=False).sum())

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", help="CSV files to audit")
    args = parser.parse_args()

    for file in args.files:
        report = audit_csv(file)
        print(report)


if __name__ == "__main__":
    main()
