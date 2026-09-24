"""Adapter selection and fail-closed real-source boundary."""
from __future__ import annotations
from dataclasses import dataclass
from .base import SourceAdapter
from .synthetic import SyntheticAdapter

@dataclass
class UnavailableRealAdapter(SourceAdapter):
    name: str
    description: str
    def fetch(self, *, hours: int = 24):
        raise RuntimeError(f"Real {self.name} adapter is not configured: {self.description}")
    def validate(self, payload) -> None:
        raise RuntimeError(f"Real {self.name} adapter is not configured")
    def normalize(self, payload):
        raise RuntimeError(f"Real {self.name} adapter is not configured")

def build_adapters(mode: str) -> dict[str, SourceAdapter]:
    if mode == "synthetic":
        adapter = SyntheticAdapter()
        return {name: adapter for name in ("satellite", "radar", "observations", "nwp", "static")}
    if mode == "real":
        return {
            "satellite": UnavailableRealAdapter("satellite", "provider credentials/download contract not configured"),
            "radar": UnavailableRealAdapter("radar", "IMD radar access contract not configured"),
            "observations": UnavailableRealAdapter("observations", "IMD/CWC live feed contract not configured"),
            "nwp": UnavailableRealAdapter("nwp", "NWP feed contract not configured"),
            "static": UnavailableRealAdapter("static", "versioned static assets not configured"),
        }
    raise ValueError(f"Unsupported data mode: {mode}")
