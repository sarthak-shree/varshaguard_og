import os

import joblib


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "models", "flood_warning_random_forest_v2.pkl")

DEFAULT_FEATURES = [
    "rainfall_1h",
    "rainfall_3h",
    "rainfall_6h",
    "rainfall_12h",
    "rainfall_24h",
    "rainfall_48h",
    "rainfall_72h",
    "rainfall_6h_max",
    "rainfall_24h_max",
    "month",
    "hour_of_day",
    "is_monsoon",
]


def load_model():
    """
    Load the saved Random Forest model.

    This function returns a dictionary with:
    - ok: True or False
    - model: the trained model, if loading worked
    - features: list of input columns
    - error: helpful message, if loading failed
    """
    if not os.path.exists(MODEL_PATH):
        return {
            "ok": False,
            "model": None,
            "features": DEFAULT_FEATURES,
            "target": "flood_soon",
            "prediction_horizon_hours": 24,
            "decision_threshold": 0.50,
            "error": "Model file is missing. Run: python backend/train_model.py",
        }

    try:
        saved = joblib.load(MODEL_PATH)
    except Exception as error:
        return {
            "ok": False,
            "model": None,
            "features": DEFAULT_FEATURES,
            "target": "flood_soon",
            "prediction_horizon_hours": 24,
            "decision_threshold": 0.50,
            "error": "Model file could not be loaded: " + str(error),
        }

    needed_keys = ["model", "features", "target", "prediction_horizon_hours", "decision_threshold"]
    for key in needed_keys:
        if key not in saved:
            return {
                "ok": False,
                "model": None,
                "features": DEFAULT_FEATURES,
                "target": "flood_soon",
                "prediction_horizon_hours": 24,
                "decision_threshold": 0.50,
                "error": "Model file is missing this key: " + key,
            }

    return {
        "ok": True,
        "model": saved["model"],
        "features": saved["features"],
        "target": saved["target"],
        "prediction_horizon_hours": saved["prediction_horizon_hours"],
        "decision_threshold": saved["decision_threshold"],
        "error": None,
    }
