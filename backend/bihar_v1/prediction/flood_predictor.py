"""River-flood prediction interface."""
from ..schemas import PredictionOutput


def predict(district: str, features: dict) -> PredictionOutput:
    return PredictionOutput(
        district=district,
        probability=None,
        status="model_not_trained",
        details={"required": "trained river-flood model", "feature_count": len(features)},
    )
