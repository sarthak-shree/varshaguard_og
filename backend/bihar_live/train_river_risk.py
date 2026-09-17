"""Train the Bihar Live river-risk model from local source CSVs.

Usage:
  python backend/bihar_live/train_river_risk.py \
    --river-data rwl_tel_hr_bihar_999_2021_2025.csv \
    --flood-events Bihar_flood_events.csv \
    --output backend/bihar_live/models/flood_probability.json

The script deliberately uses a temporal validation split. It does not use
future observations to construct a row's rolling features. The current source
inventory contains only six Bihar flood-event records from 2021-2023, so the
result is a research prototype rather than an operational warning model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "level", "rise_1h", "rise_3h", "rise_6h", "rise_12h", "rise_24h",
    "mean_6h", "mean_24h", "std_24h", "max_24h", "level_minus_mean24",
    "level_over_mean24", "hour_sin", "hour_cos", "month_sin", "month_cos",
]


def parse_events(path: Path) -> pd.DataFrame:
    events = pd.read_csv(path)
    events["start"] = pd.to_datetime(events["Start Date"], format="%d/%m/%y %H:%M", errors="coerce")
    events = events[events["State"].astype(str).str.strip().eq("Bihar") & events["start"].notna()]
    aliases = {"purba champaran": "east champaran", "pashchim champaran": "west champaran", "kaimur (bhabua)": "kaimur"}
    rows = []
    for _, event in events.iterrows():
        for district in str(event["Districts"]).split(","):
            key = district.strip().casefold()
            rows.append((event["start"], aliases.get(key, key)))
    return pd.DataFrame(rows, columns=["start", "district"]).drop_duplicates()


def make_training_frame(river_path: Path, flood_path: Path) -> pd.DataFrame:
    level_col = "River Water Level Telemetry Hourly (meter)"
    df = pd.read_csv(river_path)
    df["ts"] = pd.to_datetime(df["Data Acquisition Time"], dayfirst=True, errors="coerce")
    df["level"] = pd.to_numeric(df[level_col], errors="coerce")
    df = df.dropna(subset=["ts", "level", "Station", "District"]).copy()
    df["district"] = df["District"].astype(str).str.strip().str.casefold()
    df["station"] = df["Station"].astype(str).str.strip()
    df = df[df["ts"] <= pd.Timestamp("2023-12-31 23:00")]
    events = parse_events(flood_path)

    frames = []
    for (district, station), group in df.groupby(["district", "station"], sort=False):
        g = group.sort_values("ts").copy()
        s = g["level"]
        for hours in (1, 3, 6, 12, 24):
            g[f"rise_{hours}h"] = s.diff(hours)
        g["mean_6h"] = s.rolling(6, min_periods=6).mean()
        g["mean_24h"] = s.rolling(24, min_periods=24).mean()
        g["std_24h"] = s.rolling(24, min_periods=24).std()
        g["max_24h"] = s.rolling(24, min_periods=24).max()
        g["level_minus_mean24"] = s - g["mean_24h"]
        g["level_over_mean24"] = s / g["mean_24h"].replace(0, np.nan)
        g["hour_sin"] = np.sin(2 * np.pi * g["ts"].dt.hour / 24)
        g["hour_cos"] = np.cos(2 * np.pi * g["ts"].dt.hour / 24)
        g["month_sin"] = np.sin(2 * np.pi * (g["ts"].dt.month - 1) / 12)
        g["month_cos"] = np.cos(2 * np.pi * (g["ts"].dt.month - 1) / 12)
        y = np.zeros(len(g), dtype=np.int8)
        for start in events.loc[events["district"].eq(district), "start"]:
            y |= ((g["ts"] >= start - pd.Timedelta(hours=24)) & (g["ts"] < start)).to_numpy(dtype=np.int8)
        g["target"] = y
        frames.append(g)
    return pd.concat(frames, ignore_index=True).dropna(subset=FEATURES)


def train(frame: pd.DataFrame) -> dict:
    train = frame[frame["ts"] < pd.Timestamp("2023-01-01")]
    validation = frame[frame["ts"] >= pd.Timestamp("2023-01-01")]
    positives = train[train["target"] == 1]
    negatives = train[train["target"] == 0]
    negatives = negatives.sample(n=min(len(negatives), max(3000, len(positives) * 20)), random_state=42)
    train_sample = pd.concat([positives, negatives]).sample(frac=1, random_state=42)

    scaler = StandardScaler()
    x_train = scaler.fit_transform(train_sample[FEATURES])
    x_validation = scaler.transform(validation[FEATURES])
    model = LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)
    model.fit(x_train, train_sample["target"])
    probability = model.predict_proba(x_validation)[:, 1]
    y = validation["target"].to_numpy()

    return {
        "model_type": "logistic_regression",
        "model_version": "bihar-river-risk-v0.3.0",
        "horizon_hours": 24,
        "target_definition": "district flood event starts within next 24 hours",
        "feature_names": FEATURES,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": model.coef_[0].tolist(),
        "intercept": float(model.intercept_[0]),
        "thresholds": {"high": 0.70, "medium": 0.40},
        "calibrated": False,
        "training_period": ["2021-09-08", "2023-12-31"],
        "training_rows": int(len(train_sample)),
        "positive_training_rows": int(train_sample["target"].sum()),
        "validation_period": ["2023-01-01", "2023-12-31"],
        "validation_rows": int(len(validation)),
        "validation_positive_rows": int(y.sum()),
        "validation_average_precision": float(average_precision_score(y, probability)),
        "validation_roc_auc": float(roc_auc_score(y, probability)),
        "note": "Research prototype. The current Bihar flood inventory has only six event records from 2021-2023, so this output is not calibrated as an absolute real-world probability. Add more event labels plus rainfall and upstream-basin variables before operational deployment.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--river-data", required=True, type=Path)
    parser.add_argument("--flood-events", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    frame = make_training_frame(args.river_data, args.flood_events)
    model = train(frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(frame), "positive_rows": int(frame.target.sum()), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
