"""Leakage-safe XGBoost training and evaluation for Bihar v1 flood prediction."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

from .splitting import validate_split_readiness
from .threshold_analysis import threshold_analysis

TARGET_COLUMN = "flood_event_start_next_24h"
NON_FEATURE_COLUMNS = {
    "timestamp",
    TARGET_COLUMN,
    "flood_event_ongoing",
    "flood_event_uei",
}


def _load_split(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "timestamp" not in frame.columns:
        raise ValueError(f"Split {path} has no timestamp column")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if TARGET_COLUMN not in frame.columns:
        raise ValueError(f"Split {path} has no {TARGET_COLUMN} target")
    frame[TARGET_COLUMN] = pd.to_numeric(frame[TARGET_COLUMN], errors="raise").astype("int8")
    return frame.sort_values("timestamp").reset_index(drop=True)


def load_splits(training_dir: str | Path, district: str) -> dict[str, pd.DataFrame]:
    root = Path(training_dir) / district
    return {
        name: _load_split(root / f"{name}.csv")
        for name in ("train", "validation", "test")
    }


def _feature_columns(splits: dict[str, pd.DataFrame]) -> list[str]:
    common = set(splits["train"].columns)
    for frame in splits.values():
        common &= set(frame.columns)

    excluded = NON_FEATURE_COLUMNS
    columns = [
        column for column in splits["train"].columns
        if column in common and column not in excluded
    ]
    if not columns:
        raise ValueError("No shared model feature columns were found")
    return columns


def _numeric_matrix(frame: pd.DataFrame, columns: list[str], split_name: str) -> pd.DataFrame:
    matrix = frame[columns].apply(pd.to_numeric, errors="coerce")
    if matrix.isna().any().any():
        bad = matrix.columns[matrix.isna().any()].tolist()
        raise ValueError(f"{split_name} contains non-numeric or missing feature values: {bad}")
    return matrix.astype(float)


def _readiness_reason(readiness: dict) -> list[str]:
    reasons = []
    for name, info in readiness["splits"].items():
        if not info["ready"]:
            reasons.append(
                f"{name}: positives={info['positive_samples']} "
                f"(min {info['minimum_positive_samples']}), "
                f"events={info['positive_events']} "
                f"(min {info['minimum_positive_events']}), "
                f"negatives={info['negative_samples']}"
            )
    return reasons


def _calibration_bins(y_true: np.ndarray, probability: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows = []
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (
            (probability >= lower)
            & (probability < upper if upper < 1.0 else probability <= upper)
        )
        if not np.any(mask):
            continue
        rows.append({
            "lower": float(lower),
            "upper": float(upper),
            "count": int(mask.sum()),
            "mean_predicted_probability": float(probability[mask].mean()),
            "observed_positive_rate": float(y_true[mask].mean()),
        })
    return rows


def _calibration_error(y_true: np.ndarray, probability: np.ndarray, bins: int = 10) -> float | None:
    """Return weighted mean absolute calibration error across populated bins."""
    if len(np.unique(y_true)) < 2:
        return None
    rows = _calibration_bins(y_true, probability, bins=bins)
    if not rows:
        return None
    total = len(y_true)
    return float(sum(
        (row["count"] / total)
        * abs(row["mean_predicted_probability"] - row["observed_positive_rate"])
        for row in rows
    ))


def _safe_metric(metric, y_true, values) -> float | None:
    try:
        if len(np.unique(y_true)) < 2:
            return None
        return float(metric(y_true, values))
    except ValueError:
        return None


def evaluate_predictions(
    frame: pd.DataFrame,
    probability: np.ndarray,
    *,
    threshold: float = 0.5,
) -> dict:
    y_true = frame[TARGET_COLUMN].to_numpy(dtype=int)
    predicted = (probability >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()

    return {
        "rows": int(len(frame)),
        "positive_samples": int(y_true.sum()),
        "positive_events": int(
            frame.loc[frame[TARGET_COLUMN] == 1, "flood_event_uei"]
            .dropna().astype(str).nunique()
        ) if "flood_event_uei" in frame.columns else 0,
        "threshold": float(threshold),
        "recall": float(recall_score(y_true, predicted, zero_division=0)),
        "precision": float(precision_score(y_true, predicted, zero_division=0)),
        "f1": float(f1_score(y_true, predicted, zero_division=0)),
        "pr_auc": _safe_metric(average_precision_score, y_true, probability),
        "roc_auc": _safe_metric(roc_auc_score, y_true, probability),
        "brier_score": float(brier_score_loss(y_true, probability)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "calibration_bins": _calibration_bins(y_true, probability),
        "calibration_error": _calibration_error(y_true, probability),
    }


def _label_window_lead_time(frame: pd.DataFrame, probability: np.ndarray, threshold: float) -> dict:
    """Measure lead time only for correctly predicted positive label rows.

    This is a label-window metric, not a claim of first operational alert time.
    The inventory event start is intentionally not reconstructed from the label.
    """
    if "flood_event_uei" not in frame.columns:
        return {"events_with_predicted_positive": 0, "mean_hours": None, "median_hours": None}

    work = frame.copy()
    work["_probability"] = probability
    work["_predicted"] = (probability >= threshold).astype(int)
    positives = work[
        (work[TARGET_COLUMN] == 1)
        & (work["_predicted"] == 1)
        & work["flood_event_uei"].notna()
    ]
    if positives.empty:
        return {"events_with_predicted_positive": 0, "mean_hours": None, "median_hours": None}

    # The positive label means the event starts within the next 24h. Without
    # event start timestamps in the split, exact event lead time is unknowable.
    return {
        "events_with_predicted_positive": int(positives["flood_event_uei"].astype(str).nunique()),
        "mean_hours": None,
        "median_hours": None,
        "status": "requires_event_start_timestamp_for_exact_lead_time",
    }


def train_patna_flood_model(
    *,
    training_dir: str | Path,
    district: str = "patna",
    output_dir: str | Path | None = None,
    threshold: float = 0.5,
    random_state: int = 42,
) -> dict:
    splits = load_splits(training_dir, district)
    readiness = validate_split_readiness(splits)

    report = {
        "status": "not_trainable",
        "district": district,
        "model": "xgboost",
        "target": TARGET_COLUMN,
        "readiness": readiness,
    }

    if not readiness["ready_for_model_evaluation"]:
        report["reason"] = "Insufficient independent positive events/samples for leakage-safe model evaluation."
        report["blocking_details"] = _readiness_reason(readiness)
        return report

    features = _feature_columns(splits)
    matrices = {
        name: _numeric_matrix(frame, features, name)
        for name, frame in splits.items()
    }
    targets = {name: frame[TARGET_COLUMN].to_numpy(dtype=int) for name, frame in splits.items()}

    positives = int(targets["train"].sum())
    negatives = int(len(targets["train"]) - positives)
    if positives == 0 or negatives == 0:
        report["reason"] = "Training split contains only one target class."
        return report

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="logloss",
        scale_pos_weight=negatives / positives,
        random_state=random_state,
        n_jobs=2,
    )
    model.fit(
        matrices["train"],
        targets["train"],
        eval_set=[(matrices["validation"], targets["validation"])],
        verbose=False,
    )

    probabilities = {
        name: model.predict_proba(matrices[name])[:, 1]
        for name in ("train", "validation", "test")
    }
    metrics = {
        name: evaluate_predictions(splits[name], probabilities[name], threshold=threshold)
        for name in ("train", "validation", "test")
    }
    metrics["test"]["lead_time"] = _label_window_lead_time(
        splits["test"], probabilities["test"], threshold
    )
    validation_thresholds = threshold_analysis(
        splits["validation"], probabilities["validation"]
    )

    report.update({
        "status": "trained",
        "feature_columns": features,
        "class_balance": {
            "train_positive": positives,
            "train_negative": negatives,
            "scale_pos_weight": negatives / positives,
        },
        "metrics": metrics,
        "validation_threshold_analysis": validation_thresholds,
        "operational_threshold": None,
    })

    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        model_path = destination / f"{district}_flood_xgboost.joblib"
        report_path = destination / f"{district}_flood_training_report.json"
        joblib.dump(model, model_path)
        report["model_path"] = str(model_path)
        report["report_path"] = str(report_path)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train/evaluate Bihar v1 XGBoost flood model.")
    parser.add_argument("--training-dir", required=True)
    parser.add_argument("--district", default="patna")
    parser.add_argument("--output-dir")
    parser.add_argument("--threshold", type=float, default=0.5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = train_patna_flood_model(
        training_dir=args.training_dir,
        district=args.district,
        output_dir=args.output_dir,
        threshold=args.threshold,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
