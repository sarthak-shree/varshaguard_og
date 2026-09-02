import os

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from model import DEFAULT_FEATURES


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")
MODEL_FOLDER = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_FOLDER, "flood_warning_random_forest_v2.pkl")


def main():
    data = pd.read_csv(DATA_PATH)

    x = data[DEFAULT_FEATURES]
    y = data["flood_soon"]

    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(x, y)

    saved_model = {
        "model": model,
        "features": DEFAULT_FEATURES,
        "target": "flood_soon",
        "prediction_horizon_hours": 24,
        "decision_threshold": 0.50,
    }

    os.makedirs(MODEL_FOLDER, exist_ok=True)
    joblib.dump(saved_model, MODEL_PATH)

    print("Model saved to:", MODEL_PATH)


if __name__ == "__main__":
    main()
