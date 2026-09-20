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

def load_observations(path: str | Path) -> pd.DataFrame:
    target = Path(path)
    if not target.exists(): raise FileNotFoundError(target)
    frame = pd.read_csv(target)
    required = {"timestamp","district","variable","value","unit","source"}
    missing = required - set(frame.columns)
    if missing: raise ValueError(f"Missing normalized columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame
