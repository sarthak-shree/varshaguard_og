"""Threshold analysis for Bihar v1 flood probabilities.

This module reports validation performance across candidate thresholds. It does not
silently choose an operational alert threshold; that decision must be explicitly
configured after reviewing validation performance and false-alarm/miss trade-offs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

TARGET_COLUMN = "flood_event_start_next_24h"


def threshold_analysis(
    frame: pd.DataFrame,
    probability: np.ndarray,
    *,
    thresholds: list[float] | None = None,
) -> list[dict]:
    if TARGET_COLUMN not in frame.columns:
        raise ValueError(f"Frame has no {TARGET_COLUMN} target")

    y_true = frame[TARGET_COLUMN].to_numpy(dtype=int)
    if len(np.unique(y_true)) < 2:
        raise ValueError("Threshold analysis requires both positive and negative validation samples")
    probabilities = np.asarray(probability, dtype=float)
    if len(y_true) != len(probabilities):
        raise ValueError("Probability length must match frame length")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Probabilities must be finite and within [0, 1]")

    candidates = thresholds if thresholds is not None else [round(x, 2) for x in np.arange(0.10, 1.00, 0.05)]
    rows = []
    for threshold in candidates:
        threshold = float(threshold)
        if not 0.0 < threshold < 1.0:
            raise ValueError("Candidate thresholds must be strictly between 0 and 1")
        predicted = (probabilities >= threshold).astype(int)
        tp = int(((predicted == 1) & (y_true == 1)).sum())
        fp = int(((predicted == 1) & (y_true == 0)).sum())
        fn = int(((predicted == 0) & (y_true == 1)).sum())
        tn = int(((predicted == 0) & (y_true == 0)).sum())
        event_metrics = _event_level_metrics(frame, predicted)
        rows.append({
            "threshold": threshold,
            "positive_predictions": int(predicted.sum()),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "false_alarm_rate": float(fp / (fp + tn)) if (fp + tn) else None,
            "miss_rate": float(fn / (fn + tp)) if (fn + tp) else None,
            "recall": float(recall_score(y_true, predicted, zero_division=0)),
            "precision": float(precision_score(y_true, predicted, zero_division=0)),
            "f1": float(f1_score(y_true, predicted, zero_division=0)),
            **event_metrics,
        })
    return rows


def _event_level_metrics(frame: pd.DataFrame, predicted: np.ndarray) -> dict:
    """Measure earliest predicted warning per event without choosing a threshold."""
    required = {"flood_event_uei", "flood_event_start_timestamp", "timestamp"}
    if not required.issubset(frame.columns):
        return {
            "events_with_predicted_positive": None,
            "mean_lead_hours": None,
            "median_lead_hours": None,
        }

    work = frame.copy()
    work["_predicted"] = predicted
    work["_timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce")
    work["_event_start"] = pd.to_datetime(
        work["flood_event_start_timestamp"], utc=True, errors="coerce"
    )
    work = work[
        (work[TARGET_COLUMN] == 1)
        & (work["_predicted"] == 1)
        & work["flood_event_uei"].notna()
    ].dropna(subset=["_timestamp", "_event_start"])
    if work.empty:
        return {
            "events_with_predicted_positive": 0,
            "mean_lead_hours": None,
            "median_lead_hours": None,
        }

    earliest = (
        work.sort_values("_timestamp")
        .groupby("flood_event_uei", as_index=False)
        .first()
    )
    lead = (
        earliest["_event_start"] - earliest["_timestamp"]
    ).dt.total_seconds() / 3600.0
    lead = lead[lead >= 0]
    return {
        "events_with_predicted_positive": int(len(lead)),
        "mean_lead_hours": float(lead.mean()) if not lead.empty else None,
        "median_lead_hours": float(lead.median()) if not lead.empty else None,
    }
