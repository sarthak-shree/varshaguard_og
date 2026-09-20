"""Chronological and event-aware dataset splitting for Bihar v1."""
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
    out = out.sort_values("timestamp").reset_index(drop=True)
    if out["timestamp"].duplicated().any():
        raise ValueError("Training table must contain unique timestamps before splitting")
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


def enforce_event_isolation(splits: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Remove positive rows whose flood event appears in another split.

    The split remains chronological, but an event cannot contribute positive
    examples to more than one partition. This is an evaluation safeguard, not
    a substitute for event-aware sampling of the underlying observations.
    """
    if not any("flood_event_uei" in frame.columns for frame in splits.values()):
        return {name: frame.copy() for name, frame in splits.items()}

    event_sets = {
        name: set(
            frame.loc[
                frame.get("flood_event_start_next_24h", pd.Series(dtype="int8")) == 1,
                "flood_event_uei",
            ].dropna().astype(str)
        )
        for name, frame in splits.items()
    }

    isolated = {}
    for name, frame in splits.items():
        other_events = set().union(*(events for other, events in event_sets.items() if other != name))
        keep = ~(
            (frame.get("flood_event_start_next_24h", pd.Series(0, index=frame.index)) == 1)
            & frame["flood_event_uei"].astype("string").isin(other_events)
        )
        isolated[name] = frame.loc[keep].copy().reset_index(drop=True)
    return isolated


def split_summary(splits: dict[str, pd.DataFrame]) -> dict:
    result = {}
    for name, frame in splits.items():
        positives = int(frame.get("flood_event_start_next_24h", pd.Series(dtype="int8")).sum())
        event_ids = (
            frame.loc[frame["flood_event_start_next_24h"] == 1, "flood_event_uei"]
            .dropna().astype(str).nunique()
            if "flood_event_uei" in frame.columns else 0
        )
        result[name] = {
            "rows": int(len(frame)),
            "positive": positives,
            "negative": int(len(frame) - positives),
            "positive_rate": (positives / len(frame)) if len(frame) else 0.0,
            "positive_events": int(event_ids),
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
    minimum_events_train: int = 5,
    minimum_events_validation: int = 2,
    minimum_events_test: int = 2,
) -> dict:
    """Gate evaluation on both positive samples and independent flood events."""
    minimums = {
        "train": (minimum_positive_train, minimum_events_train),
        "validation": (minimum_positive_validation, minimum_events_validation),
        "test": (minimum_positive_test, minimum_events_test),
    }
    result = {}
    ready = True
    for name, (minimum_positive, minimum_events) in minimums.items():
        frame = splits.get(name, pd.DataFrame())
        positives = int(frame.get(
            "flood_event_start_next_24h", pd.Series(dtype="int8")
        ).sum())
        negatives = int(len(frame) - positives)
        event_ids = (
            frame.loc[frame["flood_event_start_next_24h"] == 1, "flood_event_uei"]
            .dropna().astype(str).nunique()
            if "flood_event_uei" in frame.columns else 0
        )
        ok = (
            len(frame) > 0
            and positives >= minimum_positive
            and event_ids >= minimum_events
            and negatives > 0
        )
        result[name] = {
            "ready": ok,
            "positive_samples": positives,
            "positive_events": int(event_ids),
            "negative_samples": negatives,
            "minimum_positive_samples": minimum_positive,
            "minimum_positive_events": minimum_events,
        }
        ready = ready and ok
    if ready:
        return {"ready_for_model_evaluation": True, "splits": result, "reason": None}

    blocked = []
    for name, details in result.items():
        if not details["ready"]:
            blocked.append(f"{name}: positives={details['positive_samples']}/{details['minimum_positive_samples']}, events={details['positive_events']}/{details['minimum_positive_events']}, negatives={details['negative_samples']}")
    return {"ready_for_model_evaluation": False, "splits": result, "reason": "Evaluation readiness thresholds not met: " + "; ".join(blocked)}
