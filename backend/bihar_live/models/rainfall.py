"""LightGBM-compatible rainfall baseline with a sklearn fallback."""
from __future__ import annotations
import numpy as np

class RainfallModel:
    def __init__(self):
        self.model = None
        self.backend = None

    def fit(self, X, y):
        try:
            from lightgbm import LGBMRegressor
            self.model = LGBMRegressor(n_estimators=120, learning_rate=0.05, max_depth=5, random_state=42, verbosity=-1)
            self.backend = "lightgbm"
        except ImportError:
            from sklearn.ensemble import HistGradientBoostingRegressor
            self.model = HistGradientBoostingRegressor(max_iter=120, learning_rate=0.05, max_depth=5, random_state=42)
            self.backend = "sklearn_hist_gradient_boosting"
        self.model.fit(np.asarray(X), np.asarray(y))
        return self

    def predict(self, X):
        if self.model is None:
            raise RuntimeError("Rainfall model is not trained")
        return self.model.predict(np.asarray(X))

    def save(self, path):
        import joblib
        joblib.dump({"model": self.model, "backend": self.backend}, path)

    @classmethod
    def load(cls, path):
        import joblib
        payload = joblib.load(path)
        obj = cls()
        obj.model, obj.backend = payload["model"], payload["backend"]
        return obj
