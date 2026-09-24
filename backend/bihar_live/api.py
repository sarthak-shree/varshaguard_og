"""Phase 1 API for the isolated JalDrishti live-system shell."""
from flask import Blueprint, jsonify
from .config import DATA_MODE, PREDICTION_HORIZON_HOURS, SUPPORTED_DISTRICTS
from .adapters.sources import build_adapters

bp = Blueprint("bihar_live", __name__, url_prefix="/api/bihar-live")

@bp.get("/health")
def health():
    return jsonify({
        "success": True,
        "project": "JalDrishti",
        "mode": DATA_MODE,
        "badge": "Synthetic demo data" if DATA_MODE == "synthetic" else "Real data",
        "horizon_hours": PREDICTION_HORIZON_HOURS,
        "districts": list(SUPPORTED_DISTRICTS),
    })

@bp.get("/sources")
def sources():
    adapters = build_adapters(DATA_MODE)
    return jsonify({
        "success": True,
        "mode": DATA_MODE,
        "sources": [
            {"name": name, "status": "synthetic_ready" if DATA_MODE == "synthetic" else "not_configured",
             "description": getattr(adapter, "description", "Synthetic demo adapter")}
            for name, adapter in adapters.items()
        ],
    })
