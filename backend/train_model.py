import os
import sys

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

# Support `python backend/train_model.py` from repository root as documented.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from model import DEFAULT_FEATURES

DATA_PATH = os.path.join(ROOT_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")
MODEL_FOLDER = os.path.join(ROOT_DIR, "models")
MODEL_PATH = os.path.join(MODEL_FOLDER, "flood_warning_random_forest_v2.pkl")


def main():
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    data = pd.read_csv(DATA_PATH)
    required = DEFAULT_FEATURES + ["flood_soon"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError("Dataset is missing required columns: " + ", ".join(missing))

    data = data.dropna(subset=required).copy()
    if data.empty:
        raise ValueError("Dataset has no usable rows after dropping missing values")

    x = data[DEFAULT_FEATURES]
    y = data["flood_soon"].astype(int)

    stratify = y if y.nunique() > 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.20,
        random_state=42,
        stratify=stratify,
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1] if len(model.classes_) == 2 else None

    accuracy = accuracy_score(y_test, predictions)
    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
    roc_auc = roc_auc_score(y_test, probabilities) if probabilities is not None and y_test.nunique() == 2 else None

    saved_model = {
        "model": model,
        "features": DEFAULT_FEATURES,
        "target": "flood_soon",
        "prediction_horizon_hours": 24,
        "decision_threshold": 0.50,
        "evaluation": {
            "test_rows": int(len(y_test)),
            "accuracy": round(float(accuracy), 4),
            "roc_auc": round(float(roc_auc), 4) if roc_auc is not None else None,
            "classification_report": report,
        },
    }

    os.makedirs(MODEL_FOLDER, exist_ok=True)
    joblib.dump(saved_model, MODEL_PATH)

    print(f"Model saved to: {MODEL_PATH}")
    print(f"Test rows: {len(y_test)}")
    print(f"Accuracy: {accuracy:.4f}")
    if roc_auc is not None:
        print(f"ROC-AUC: {roc_auc:.4f}")


if __name__ == "__main__":
    main()
