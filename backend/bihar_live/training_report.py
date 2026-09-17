"""Train the Bihar historical model from locally supplied source assets and report metrics."""
from __future__ import annotations

import json
from pathlib import Path

from .bihar_historical_train import build_training_table
from .bihar_historical_model import train_and_compare

REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "bihar" / "bihar_model_report.json"


def main() -> None:
    training = build_training_table()
    model = train_and_compare()
    report = {
        "dataset_rows": int(len(training)),
        "districts": sorted(training["district"].unique().tolist()),
        "positive_next_3d_labels": int(training["flood_next_3d"].sum()),
        "positive_label_rate": round(float(training["flood_next_3d"].mean()), 6),
        "model": model,
        "terrain_dem": "not supplied; no synthetic terrain features used",
        "note": "Validation is chronological. Add a dedicated calibration period before operational probability use.",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
