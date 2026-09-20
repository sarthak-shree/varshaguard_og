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
        rows.append({
            "threshold": threshold,
            "positive_predictions": int(predicted.sum()),
            "recall": float(recall_score(y_true, predicted, zero_division=0)),
            "precision": float(precision_score(y_true, predicted, zero_division=0)),
            "f1": float(f1_score(y_true, predicted, zero_division=0)),
        })
    return rows
