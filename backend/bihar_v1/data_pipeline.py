"""Portable persistence helpers for normalized Bihar v1 observations."""
from pathlib import Path
from typing import Iterable
import pandas as pd
from .config import BIHAR_V1_DATA_ROOT
from .schemas import Observation

def ensure_data_dirs(root: Path | None = None) -> dict[str, Path]:
    base = Path(root or BIHAR_V1_DATA_ROOT)
    paths = {"raw": base / "raw", "processed": base / "processed", "training": base / "training", "fixtures": base / "fixtures"}
    for path in paths.values(): path.mkdir(parents=True, exist_ok=True)
    return paths

def observations_to_frame(observations: Iterable[Observation]) -> pd.DataFrame:
    rows = [x.to_dict() for x in observations]
    columns = ["timestamp","district","variable","value","unit","source","station_id","quality","metadata"]
    return pd.DataFrame(rows, columns=columns)

def save_observations(observations: Iterable[Observation], path: str | Path) -> Path:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    observations_to_frame(observations).to_csv(target, index=False)
    return target

def validate_observations_frame(frame: pd.DataFrame) -> dict:
    """Validate normalized observations without modifying the input frame."""
    required = {"timestamp", "district", "variable", "value", "unit", "source"}
    missing = sorted(required - set(frame.columns))
    result = {"valid": not missing, "rows": int(len(frame)), "missing_columns": missing,
              "invalid_timestamps": 0, "invalid_values": 0, "empty_districts": 0,
              "empty_variables": 0, "duplicate_observations": 0}
    if missing:
        return result
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    values = pd.to_numeric(frame["value"], errors="coerce")
    invalid_value_mask = values.isna() & frame["value"].notna()
    result["invalid_timestamps"] = int(timestamps.isna().sum())
    result["invalid_values"] = int(invalid_value_mask.sum())
    result["empty_districts"] = int(frame["district"].astype("string").str.strip().eq("").sum())
    result["empty_variables"] = int(frame["variable"].astype("string").str.strip().eq("").sum())
    key_columns = ["timestamp", "district", "variable"]
    for column in ("source", "station_id"):
        if column in frame.columns:
            key_columns.append(column)
    result["duplicate_observations"] = int(frame.duplicated(subset=key_columns, keep=False).sum())
    result["valid"] = not any(result[key] for key in (
        "invalid_timestamps", "invalid_values", "empty_districts", "empty_variables", "duplicate_observations"
    ))
    return result


def load_observations(path: str | Path) -> pd.DataFrame:
    target = Path(path)
    if not target.exists(): raise FileNotFoundError(target)
    frame = pd.read_csv(target)
    required = {"timestamp","district","variable","value","unit","source"}
    missing = required - set(frame.columns)
    if missing: raise ValueError(f"Missing normalized columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    validation = validate_observations_frame(frame)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    if not validation["valid"]:
        raise ValueError(f"Invalid normalized observations: {validation}")
    return frame
