"""Build a Bihar district-day historical flood training table from supplied data.

The supplied river telemetry is the historical hydrological input. The supplied
Bihar flood inventory is the outcome label. A flood day is labeled only when
that district is explicitly present in the inventory; no threshold-derived or
synthetic flood labels are created.

Note: the provided telemetry files cover only a subset of Bihar districts.
District geometry/DEM data was not present in the supplied files, so terrain
features are intentionally absent rather than invented.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "bihar"
OUTPUT = DATA_DIR / "bihar_district_day_training.csv"

RAIN_FILES = [
    os.getenv("BIHAR_TELE_1961_1990", "/mnt/data/rwl_tele_hr_bihar_999_1961_1990(1).csv"),
    os.getenv("BIHAR_TELE_1991_2020", "/mnt/data/rwl_tele_hr_bihar_999_1991_2020(1).csv"),
    os.getenv("BIHAR_TELE_2021_2025", "/mnt/data/rwl_tel_hr_bihar_999_2021_2025(1).csv"),
    os.getenv("BIHAR_TELE_2026_2030", "/mnt/data/rwl_tel_hr_bihar_999_2026_2030(1).csv"),
]
FLOOD_ZIP = os.getenv("BIHAR_FLOOD_INVENTORY", "/mnt/data/Bihar_flood_inventory_extracted(2).zip")

ALIASES = {
    "PASHCHIM CHAMPARAN": "WEST CHAMPARAN",
    "PURBA CHAMPARAN": "EAST CHAMPARAN",
    "PURNEA": "PURNIA",
    "KAIMUR (BHABUA)": "KAIMUR",
    "JAHANABAD": "JEHANABAD",
}


def norm_district(value: object) -> str:
    text = " ".join(str(value or "").upper().replace("*", " ").split())
    return ALIASES.get(text, text)


def load_telemetry() -> pd.DataFrame:
    frames = []
    for raw_path in RAIN_FILES:
        path = Path(raw_path)
        if not path.exists():
            continue
        df = pd.read_csv(path)
        frames.append(pd.DataFrame({
            "timestamp": pd.to_datetime(df["Data Acquisition Time"], dayfirst=True, errors="coerce"),
            "station": df["Station"].astype(str).str.strip(),
            "district": df["District"].map(norm_district),
            "level_m": pd.to_numeric(df["River Water Level Telemetry Hourly (meter)"], errors="coerce"),
        }).dropna(subset=["timestamp", "level_m"]))
    if not frames:
        raise FileNotFoundError("No Bihar telemetry source files found.")
    data = pd.concat(frames, ignore_index=True)
    data = data[(data["level_m"] >= 0) & (data["level_m"] <= 1100)].copy()
    data["date"] = data["timestamp"].dt.normalize()
    return data.sort_values("timestamp")


def load_flood_labels() -> pd.DataFrame:
    if not Path(FLOOD_ZIP).exists():
        raise FileNotFoundError("Bihar flood inventory ZIP not found.")
    with zipfile.ZipFile(FLOOD_ZIP) as z:
        with z.open("Bihar_flood_events_by_district.csv") as f:
            events = pd.read_csv(f)
    start = pd.to_datetime(events["Start Date"], errors="coerce")
    end = pd.to_datetime(events["End Date"], errors="coerce")
    rows = []
    work = events.assign(_start=start, _end=end).dropna(subset=["_start"])
    for _, row in work.iterrows():
        district = norm_district(row.get("Bihar District"))
        if not district:
            continue
        finish = row["_end"] if pd.notna(row["_end"]) else row["_start"]
        for day in pd.date_range(row["_start"].normalize(), finish.normalize(), freq="D"):
            rows.append({"district": district, "date": day, "flood_event": 1})
    return pd.DataFrame(rows).drop_duplicates(["district", "date"]) if rows else pd.DataFrame(columns=["district", "date", "flood_event"])


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

    # Forecast target: a known historical flood event begins during the next 1-3 days.
    future = labels[["district", "date"]].drop_duplicates()
    for horizon in (1, 2, 3):
        shifted = future.copy()
        shifted["date"] = shifted["date"] - pd.Timedelta(days=horizon)
        shifted[f"target_{horizon}d"] = 1
        daily = daily.merge(shifted, on=["district", "date"], how="left")
        daily[f"target_{horizon}d"] = daily[f"target_{horizon}d"].fillna(0).astype(int)
    daily["flood_next_3d"] = daily[["target_1d", "target_2d", "target_3d"]].max(axis=1)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    daily.to_csv(OUTPUT, index=False)
    return daily


if __name__ == "__main__":
    df = build_training_table()
    print(f"Wrote {len(df):,} district-day rows to {OUTPUT}")
    print(f"Positive next-3-day labels: {int(df['flood_next_3d'].sum()):,}")
    print(df.groupby("district")["flood_next_3d"].sum().sort_values(ascending=False).to_string())
