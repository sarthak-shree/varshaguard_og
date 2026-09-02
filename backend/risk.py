def get_risk(probability, decision_threshold=0.50):
    """
    Turn the model's probability into a simple risk level.

    probability is a number between 0 and 1.
    Example: 0.84 means 84%.
    """
    if probability >= max(decision_threshold, 0.70):
        return "HIGH"

    if probability >= 0.40:
        return "MEDIUM"

    return "LOW"


def get_warning(risk):
    """Return a human-friendly warning message for the dashboard."""
    if risk == "HIGH":
        return "Flood likely soon. Take precautionary measures and follow local authority guidance."

    if risk == "MEDIUM":
        return "Moderate flood risk detected. Stay alert and monitor local conditions."

    return "Flood risk is currently low. Continue monitoring conditions."
