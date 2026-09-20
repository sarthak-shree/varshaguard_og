"""Feature engineering shared by training and inference."""
import pandas as pd

RAIN_WINDOWS = (1, 3, 6, 12, 24, 72, 168)
RIVER_LAG_HOURS = (1, 3, 6, 12, 24)

def prepare_hourly_frame(frame: pd.DataFrame, *, timestamp_col: str = "timestamp") -> pd.DataFrame:
    out = frame.copy()
    if timestamp_col not in out.columns:
        raise ValueError(f"Missing required column: {timestamp_col}")
    out[timestamp_col] = pd.to_datetime(out[timestamp_col], utc=True, errors="raise")
    if out[timestamp_col].duplicated().any():
        raise ValueError("Feature engineering requires unique timestamps")
    return out.sort_values(timestamp_col).reset_index(drop=True)

def add_rainfall_features(frame: pd.DataFrame, *, rain_col: str = "rain_mm") -> pd.DataFrame:
    out = prepare_hourly_frame(frame)
    if rain_col not in out.columns:
        raise ValueError(f"Missing required column: {rain_col}")
    rain = pd.to_numeric(out[rain_col], errors="coerce")
    indexed = pd.Series(rain.to_numpy(), index=out["timestamp"])
    hourly = indexed.reindex(pd.date_range(indexed.index.min(), indexed.index.max(), freq="1h", tz="UTC"))
    for hours in RAIN_WINDOWS:
        out[f"rain_{hours}h"] = [hourly.loc[:ts].tail(hours).sum(min_count=hours) for ts in out["timestamp"]]
    out["rain_1h_intensity"] = rain
    out["rain_24h_peak_1h"] = [hourly.loc[:ts].tail(24).max() if hourly.loc[:ts].tail(24).notna().all() else float("nan") for ts in out["timestamp"]]
    return out

def add_river_features(frame: pd.DataFrame, *, level_col: str = "river_level_m") -> pd.DataFrame:
    out = prepare_hourly_frame(frame)
    if level_col not in out.columns:
        raise ValueError(f"Missing required column: {level_col}")
    level = pd.to_numeric(out[level_col], errors="coerce")
    indexed = pd.DataFrame({"timestamp": out["timestamp"], "level": level}).sort_values("timestamp")
    source = indexed.rename(columns={"timestamp": "source_timestamp", "level": "source_level"})
    for hours in RIVER_LAG_HOURS:
        target = indexed[["timestamp"]].copy()
        target["lookup"] = target["timestamp"] - pd.Timedelta(hours=hours)
        matched = pd.merge_asof(target.sort_values("lookup"), source.sort_values("source_timestamp"), left_on="lookup", right_on="source_timestamp", direction="backward", tolerance=pd.Timedelta(minutes=30)).sort_values("timestamp")
        lag = matched["source_level"].to_numpy()
        out[f"river_level_lag_{hours}h"] = lag
        out[f"river_rise_{hours}h"] = level.to_numpy() - lag
    return out

def build_tabular_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = add_rainfall_features(frame) if "rain_mm" in frame.columns else prepare_hourly_frame(frame)
    return add_river_features(out) if "river_level_m" in out.columns else out
