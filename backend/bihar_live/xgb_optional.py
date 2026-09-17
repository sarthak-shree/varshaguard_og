"""Optional XGBoost adapter.

XGBoost is intentionally optional so the core VARSHAGUARD deployment does not
fail when the extra package is unavailable. Use this only after adding
xgboost to requirements and validating it on Bihar's chronological holdout.
"""
from __future__ import annotations


def build_xgb_classifier():
    try:
        from xgboost import XGBClassifier
    except ImportError as exc:
        raise RuntimeError("XGBoost is optional; install xgboost before using this adapter.") from exc
    return XGBClassifier(
        n_estimators=400,
        max_depth=6,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=4,
    )
