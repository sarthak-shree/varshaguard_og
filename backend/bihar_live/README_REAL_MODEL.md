# Bihar 24h flood model

This pipeline requires real temporal overlap between the supplied historical rainfall and river telemetry. It will fail closed when no overlap exists; it does not manufacture overlap.

Training command (with the supplied local files):

```bash
python -m backend.bihar_live.bihar_real_model
```

The trained artifact is `models/bihar_24h_flood_model.pkl` and metadata is `models/bihar_24h_flood_model_metadata.json`.

The target is `flood_next_24h`: a documented flood-event start on the following day for the same district. Probability semantics are therefore the estimated probability of a documented flood event starting in the district within the next 24 hours.

The artifact contains the selected Random Forest or XGBoost model, an isotonic calibrator fitted only on the chronological calibration period, the feature schema, target, periods and validation metrics.

The live endpoint uses the artifact and current rainfall/river observations. It does not re-train on request and does not combine the model output with a separate heuristic river probability.
