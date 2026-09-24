"""File-backed real-mode adapter boundary."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .base import SourceAdapter
from .contracts import validate_observation_records

@dataclass
class FileSourceAdapter(SourceAdapter):
    name: str
    path: str

    def fetch(self, *, hours: int = 24) -> Any:
        from pathlib import Path
        import json, csv
        file = Path(self.path)
        if not file.exists():
            raise FileNotFoundError(f"Real source file not found: {file}")
        if file.suffix.lower() == ".json":
            payload = json.loads(file.read_text(encoding="utf-8"))
        elif file.suffix.lower() == ".csv":
            with file.open("r", encoding="utf-8", newline="") as handle:
                payload = list(csv.DictReader(handle))
        else:
            raise ValueError(f"Unsupported real source file format: {file.suffix}")
        self.validate(payload)
        return payload

    def validate(self, payload: Any) -> None:
        validate_observation_records(payload)

    def normalize(self, payload: Any) -> Any:
        self.validate(payload)
        return payload
