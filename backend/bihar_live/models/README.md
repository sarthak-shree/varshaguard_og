# Bihar Live ML model layout

This directory reserves separate model artifacts and metadata for Bihar Live. Do not copy the existing v0.2.0 Assam/Uttarakhand model into this area.

Planned model families:

- `river_level/` — water-level forecasting by station/horizon.
- `flood_probability/` — calibrated probability of the defined flood event.
- `inundation/` — spatial extent/depth model or hydraulic/geospatial engine.

Every trained model must have a metadata record containing training period, target, features, validation method, metrics, model version and limitations. Models should be selected on evidence from temporal backtesting rather than complexity.
