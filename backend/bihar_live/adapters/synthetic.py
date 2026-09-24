"""Synthetic adapter implementing the same interface as real adapters."""
from ..synthetic import generate_observations
from .base import SourceAdapter

class SyntheticAdapter(SourceAdapter):
    name = "synthetic"
    def fetch(self, *, hours: int = 24):
        return generate_observations(hours=hours)
    def validate(self, payload) -> None:
        if not isinstance(payload, list):
            raise ValueError("Synthetic payload must be a list")
        for item in payload:
            if getattr(item, "timestamp_utc", None) is None:
                raise ValueError("Synthetic observation missing timestamp_utc")
    def normalize(self, payload):
        self.validate(payload)
        return payload
