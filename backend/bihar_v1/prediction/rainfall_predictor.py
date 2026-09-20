"""Heavy-rainfall prediction interface."""
from ..schemas import PredictionOutput


def predict(district: str, features: dict) -> PredictionOutput:
    # Model inference is intentionally unavailable until a trained artifact exists.
    return PredictionOutput(
        district=district,
        probability=None,
        status="model_not_trained",
        details={"required": "trained heavy-rainfall model", "feature_count": len(features)},
    )
