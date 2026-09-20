"""Chronological and event-aware dataset splitting for Bihar v1.

Splits are made by time, never randomly. A purge gap prevents feature windows
near the validation/test boundary from leaking across partitions.
"""
from __future__ import annotations

import pandas as pd


def chronological_split(
    frame: pd.DataFrame,
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    purge_hours: int = 168,
) -> dict[str, pd.DataFrame]:
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must be below 1")
    if purge_hours < 0:
        raise ValueError("purge_hours cannot be negative")
    if "timestamp" not in frame.columns:
        raise ValueError("Training table must contain timestamp")

    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="raise")
    out = out.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    if len(out) < 3:
        raise ValueError("At least 3 unique timestamps are required")

    start = out["timestamp"].min()
    end = out["timestamp"].max()
    span = end - start
    train_cut = start + span * train_fraction
    validation_cut = start + span * (train_fraction + validation_fraction)
    purge = pd.Timedelta(hours=purge_hours)

    train = out[out["timestamp"] < train_cut].copy()
    validation = out[
        (out["timestamp"] >= train_cut + purge)
        & (out["timestamp"] < validation_cut)
    ].copy()
    test = out[out["timestamp"] >= validation_cut + purge].copy()

    return {"train": train, "validation": validation, "test": test}


def split_summary(splits: dict[str, pd.DataFrame]) -> dict:
    result = {}
    for name, frame in splits.items():
        positives = int(frame.get("flood_event_start_next_24h", pd.Series(dtype="int8")).sum())
        result[name] = {
            "rows": int(len(frame)),
            "positive": positives,
            "negative": int(len(frame) - positives),
            "positive_rate": (positives / len(frame)) if len(frame) else 0.0,
            "start": frame["timestamp"].min().isoformat() if len(frame) else None,
            "end": frame["timestamp"].max().isoformat() if len(frame) else None,
        }
    return result


def validate_split_readiness(
    splits: dict[str, pd.DataFrame],
    *,
    minimum_positive_train: int = 10,
    minimum_positive_validation: int = 3,
    minimum_positive_test: int = 3,
) -> dict:
    """Report whether each partition contains enough positive events/samples.

    This is a gate for model evaluation, not a claim that a dataset is
    statistically sufficient. Positive sample counts are deliberately
    conservative because adjacent lead-window rows can belong to one event.
    """
    minimums = {
        "train": minimum_positive_train,
        "validation": minimum_positive_validation,
        "test": minimum_positive_test,
    }
    result = {}
    ready = True
    for name, minimum in minimums.items():
        frame = splits.get(name, pd.DataFrame())
        positives = int(frame.get(
            "flood_event_start_next_24h", pd.Series(dtype="int8")
        ).sum())
        negatives = int(len(frame) - positives)
        ok = len(frame) > 0 and positives >= minimum and negatives > 0
        result[name] = {
            "ready": ok,
            "positive_samples": positives,
            "negative_samples": negatives,
            "minimum_positive_samples": minimum,
        }
        ready = ready and ok
    return {"ready_for_model_evaluation": ready, "splits": result}
