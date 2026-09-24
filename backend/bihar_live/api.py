"""Phase 3 API for fusion and synthetic model evaluation."""
from flask import Blueprint, jsonify
from .config import DATA_MODE, PREDICTION_HORIZON_HOURS, SUPPORTED_DISTRICTS
from .adapters.sources import build_adapters
from .synthetic import generate_observations
from .fusion import fuse, weights_for_lead
from .models.training import train_evaluate

bp = Blueprint("bihar_live", __name__, url_prefix="/api/bihar-live")

@bp.get("/health")
def health():
    return jsonify({"success":True,"project":"JalDrishti","mode":DATA_MODE,
        "badge":"Synthetic demo data" if DATA_MODE=="synthetic" else "Real data",
        "horizon_hours":PREDICTION_HORIZON_HOURS,"districts":list(SUPPORTED_DISTRICTS)})

@bp.get("/sources")
def sources():
    adapters=build_adapters(DATA_MODE)
    return jsonify({"success":True,"mode":DATA_MODE,"sources":[
        {"name":name,"status":"synthetic_ready" if DATA_MODE=="synthetic" else "not_configured",
         "description":getattr(adapter,"description","Synthetic demo adapter")}
        for name,adapter in adapters.items()]})

@bp.get("/fusion")
def fusion():
    lead=int(__import__("flask").request.args.get("lead",3))
    values={"radar":20.0,"satellite":18.0,"observations":16.0,"nwp":14.0}
    return jsonify({"success":True,"mode":DATA_MODE,"badge":"Synthetic demo data" if DATA_MODE=="synthetic" else "Real data",
                    "lead_hours":lead,**fuse(values,lead)})

@bp.get("/model/evaluation")
def evaluation():
    rows=generate_observations(hours=96,seed=26071)
    model,metrics=train_evaluate(rows)
    return jsonify({"success":True,"model":"rainfall_baseline","backend":model.backend,**metrics})
