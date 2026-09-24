"""Shared adapter interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class SourceAdapter(ABC):
    name: str
    @abstractmethod
    def fetch(self, *, hours: int = 24) -> Any:
        raise NotImplementedError
    @abstractmethod
    def validate(self, payload: Any) -> None:
        raise NotImplementedError
    @abstractmethod
    def normalize(self, payload: Any) -> Any:
        raise NotImplementedError
