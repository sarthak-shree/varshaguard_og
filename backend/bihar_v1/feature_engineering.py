"""Feature engineering shared by training and inference."""
import pandas as pd

RAIN_WINDOWS = (1, 3, 6, 12, 24, 72, 168)
RIVER_LAG_HOURS = (1, 3, 6, 12, 24)

def prepare_hourly_frame(frame: pd.DataFrame, *, timestamp_col: str = "timestamp") -> pd.DataFrame:
    out = frame.copy()
    if timestamp_col not in out.columns:
        raise ValueError(f"Missing required column: {timestamp_col}")
    out[timestamp_col] = pd.to_datetime(out[timestamp_col], utc=True, errors="raise")
    return out.sort_values(timestamp_col).reset_index(drop=True)

def add_rainfall_features(frame: pd.DataFrame, *, rain_col: str = "rain_mm") -> pd.DataFrame:
    out = prepare_hourly_frame(frame)
    if rain_col not in out.columns:
        raise ValueError(f"Missing required column: {rain_col}")
    rain = pd.to_numeric(out[rain_col], errors="coerce")
    for hours in RAIN_WINDOWS:
        out[f"rain_{hours}h"] = rain.rolling(hours, min_periods=hours).sum()
    out["rain_1h_intensity"] = rain
    out["rain_24h_peak_1h"] = rain.rolling(24, min_periods=24).max()
    return out

def add_river_features(frame: pd.DataFrame, *, level_col: str = "river_level_m") -> pd.DataFrame:
    out = prepare_hourly_frame(frame)
    if level_col not in out.columns:
        raise ValueError(f"Missing required column: {level_col}")
    level = pd.to_numeric(out[level_col], errors="coerce")
    for hours in RIVER_LAG_HOURS:
        out[f"river_level_lag_{hours}h"] = level.shift(hours)
        out[f"river_rise_{hours}h"] = level - level.shift(hours)
    return out

def build_tabular_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = add_rainfall_features(frame) if "rain_mm" in frame.columns else prepare_hourly_frame(frame)
    return add_river_features(out) if "river_level_m" in out.columns else out
