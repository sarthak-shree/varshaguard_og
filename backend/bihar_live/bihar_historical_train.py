"""Build a Bihar district-day historical flood training table from supplied data.

This script is intentionally conservative about the uploaded legacy flood
inventory: a district mentioned in a multi-state historical event is treated
as an event label for that district-day. River telemetry is aggregated from
supplied files. No synthetic labels are created.
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "bihar"
OUTPUT = DATA_DIR / "bihar_district_day_training.csv"

RAINFALL_FILES = [
    Path(os.getenv("BIHAR_RAINFALL_2021_2025", "/mnt/data/rwl_tel_hr_bihar_999_2021_2025(1).csv")),
    Path(os.getenv("BIHAR_RAINFALL_2026_2030", "/mnt/data/rwl_tel_hr_bihar_999_2026_2030(1).csv")),
    Path(os.getenv("BIHAR_RAINFALL_1991_2020", "/mnt/data/rwl_tele_hr_bihar_999_1991_2020(1).csv")),
    Path(os.getenv("BIHAR_RAINFALL_1961_1990", "/mnt/data/rwl_tele_hr_bihar_999_1961_1990(1).csv")),
]
FLOOD_ZIP = Path(os.getenv("BIHAR_FLOOD_INVENTORY", "/mnt/data/Bihar_flood_inventory_extracted(2).zip"))

DISTRICT_ALIASES = {
    "PASHCHIM CHAMPARAN": "WEST CHAMPARAN",
    "PURBA CHAMPARAN": "EAST CHAMPARAN",
    "Kaimur (bhabua)": "KAIMUR",
    "Kaimur": "KAIMUR",
    "Purnia": "PURNIA",
    "PURNEA": "PURNIA",
    "Jehanabad": "JEHANABAD",
    "Jahanabad": "JEHANABAD",
    "Arwal": "ARWAL",
}


def norm_district(value: object) -> str:
    text = " ".join(str(value or "").upper().replace("*", " ").split())
    return DISTRICT_ALIASES.get(text, text)


def load_telemetry() -> pd.DataFrame:
    frames = []
    for path in RAINFALL_FILES:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        ts = pd.to_datetime(df["Data Acquisition Time"], dayfirst=True, errors="coerce")
        level = pd.to_numeric(df["River Water Level Telemetry Hourly (meter)"], errors="coerce")
        out = pd.DataFrame({
            "timestamp": ts,
            "station": df["Station"].astype(str).str.strip(),
            "district": df["District"].map(norm_district),
            "level_m": level,
        })
        frames.append(out.dropna(subset=["timestamp", "level_m"]))
    if not frames:
        raise FileNotFoundError("No Bihar telemetry files were found.")
    data = pd.concat(frames, ignore_index=True)
    data = data[(data["level_m"] >= 0) & (data["level_m"] <= 1100)].copy()
    data["date"] = data["timestamp"].dt.floor("D")
    return data.sort_values("timestamp")


def load_flood_labels() -> pd.DataFrame:
    if not FLOOD_ZIP.exists():
        raise FileNotFoundError("Bihar flood inventory ZIP was not found.")
    with zipfile.ZipFile(FLOOD_ZIP) as z:
        with z.open("Bihar_flood_events_by_district.csv") as f:
            events = pd.read_csv(f)
    start = pd.to_datetime(events["Start Date"], dayfirst=False, errors="coerce")
    end = pd.to_datetime(events["End Date"], dayfirst=False, errors="coerce")
    rows = []
    for _, row in events.assign(_start=start, _end=end).dropna(subset=["_start"]).iterrows():
        district = norm_district(row.get("Bihar District"))
        if not district:
            continue
        finish = row["_end"] if pd.notna(row["_end"]) else row["_start"]
        for day in pd.date_range(row["_start"].normalize(), finish.normalize(), freq="D"):
            rows.append({"district": district, "date": day, "flood_event": 1})
    if not rows:
        return pd.DataFrame(columns=["district", "date", "flood_event"])
    labels = pd.DataFrame(rows).drop_duplicates(["district", "date"])
    return labels


def build_training_table() -> pd.DataFrame:
    telemetry = load_telemetry()
    daily = telemetry.groupby(["district", "date"], as_index=False).agg(
        level_min_m=("level_m", "min"),
        level_mean_m=("level_m", "mean"),
        level_max_m=("level_m", "max"),
        level_std_m=("level_m", "std"),
        station_count=("station", "nunique"),
    )
    daily["level_std_m"] = daily["level_std_m"].fillna(0.0)
    daily = daily.sort_values(["district", "date"])
    for window in (3, 7, 14):
        daily[f"level_max_{window}d"] = daily.groupby("district")["level_max_m"].transform(lambda s: s.rolling(window, min_periods=1).max())
        daily[f"level_mean_{window}d"] = daily.groupby("district")["level_mean_m"].transform(lambda s: s.rolling(window, min_periods=1).mean())
    daily["level_rise_1d_m"] = daily.groupby("district")["level_mean_m"].diff().fillna(0.0)
    daily["month"] = daily["date"].dt.month
    daily["is_monsoon"] = daily["month"].isin([6, 7, 8, 9]).astype(int)

    labels = load_flood_labels()
    daily = daily.merge(labels, on=["district", "date"], how="left")
    daily["flood_event"] = daily["flood_event"].fillna(0).astype(int)

    # Prediction target: event starts within the next 3 days, excluding the current day.
    future = labels.copy()
    if not future.empty:
        future_dates = future[["district", "date"]].drop_duplicates()
        for horizon in (1, 2, 3):
            shifted = future_dates.copy()
            shifted["date"] = shifted["date"] - pd.Timedelta(days=horizon)
            shifted[f"flood_next_{horizon}d"] = 1
            daily = daily.merge(shifted, on=["district", "date"], how="left")
            daily[f"flood_next_{horizon}d"] = daily[f"flood_next_{horizon}d"].fillna(0).astype(int)
    else:
        for horizon in (1, 2, 3):
            daily[f"flood_next_{horizon}d"] = 0
    daily["flood_next_3d"] = daily[["flood_next_1d", "flood_next_2d", "flood_next_3d"]].max(axis=1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    daily.to_csv(OUTPUT, index=False)
    return daily


if __name__ == "__main__":
    result = build_training_table()
    print(f"Wrote {len(result):,} district-day rows to {OUTPUT}")
    print(result.groupby("district")["flood_next_3d"].sum().sort_values(ascending=False).head(10))
