"""Bihar Live inundation-engine contract.

This module exposes a conservative interface for future spatial inundation
prediction. It intentionally does not fabricate flood extent or depth from
river thresholds alone.
"""

from __future__ import annotations


def build_inundation_context(record: dict) -> dict:
    return {
        "engine": "bihar_inundation_engine",
        "status": "awaiting_model_inputs",
        "extent_percent": None,
        "depth_m": None,
        "confidence": None,
        "requires": [
            "validated river/hydrology inputs",
            "terrain/DEM",
            "river geometry or floodplain representation",
            "historical flood-extent labels or equivalent spatial supervision",
        ],
        "message": "Inundation extent and depth are not inferred from a station threshold. Connect a validated spatial model when the required terrain and flood-extent data are available.",
    }
