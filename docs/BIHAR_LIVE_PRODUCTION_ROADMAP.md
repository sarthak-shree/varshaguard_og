# VARSHAGUARD Bihar Live — Production Roadmap

This document defines the engineering roadmap for the Bihar Live v0.3.0 branch. The existing SIH v0.2.0 Assam/Uttarakhand prototype remains stable and is not modified by this roadmap.

## Current baseline

The Bihar Live branch currently has a separate Flask API, FMISC/WRD live-river ingestion, processing, Neon PostgreSQL persistence, scheduled GitHub Actions synchronization, and a live river dashboard. The live API reads the latest successful FMISC snapshot from Neon rather than scraping FMISC on the Vercel request path.

## Target system

FMISC/CWC river observations + rainfall/weather + upstream basin/Nepal information + barrage/gate/discharge + satellite/radar where authorized + forecast rainfall + terrain/river geometry
→ quality control and storage
→ time/space alignment
→ rainfall intelligence
→ river-level forecasting
→ flood probability
→ spatial inundation prediction
→ validation with observed satellite flood extent
→ location-aware risk and alerts
→ API + dashboard.

## Engineering rules

1. Never fabricate observations or unavailable feeds.
2. Never label cached or simulated values as live.
3. Never call flood probability inundation prediction.
4. Use temporal validation for time-dependent ML.
5. Prevent future-data and event leakage.
6. Evaluate imbalanced classifiers with precision/recall/F1, PR-AUC, ROC-AUC and calibration rather than accuracy alone.
7. Compare simple baselines before complex models.
8. Separate observed, forecast, satellite-derived and model-derived values.
9. Every prediction exposes timestamp, source context, model version, freshness and confidence where available.
10. A production claim requires historical backtesting and documented limitations.

## Phase plan

### Phase A — baseline
- Inspect current branch and preserve v0.2.0.
- Run unit/integration tests.
- Verify FMISC ingestion, Neon persistence, API and frontend.
- Add regression tests before major expansion.

### Phase B — hydrology hardening
- Add source-health, stale-data and quality metadata.
- Improve retries/timeouts and malformed-record handling.
- Add official CWC/upstream/barrage/gate/discharge adapters only where accessible.
- Preserve source and observation timestamps.

### Phase C — rainfall intelligence
- Add rainfall observation schema and ingestion adapters for legitimately accessible IMD and satellite rainfall data.
- Store observed/forecast/source distinctions.
- Derive 1h/3h/6h/12h/24h/48h accumulation, intensity, anomaly and trend features.
- Add rainfall APIs and map layers.

### Phase D — river forecasting
- Build dedicated Bihar river-level models.
- Establish persistence baseline.
- Compare appropriate models using chronological validation.
- Predict +1h/+3h/+6h/+12h/+24h water levels and threshold exceedance probabilities where data supports it.

### Phase E — flood probability
- Build Bihar-specific flood labels from historical events.
- Use temporal splits and leakage checks.
- Compare models and calibrate probabilities.
- Support 6h/12h/24h horizons where feasible.

### Phase F — basin/upstream intelligence
- Incorporate upstream rainfall, upstream river levels, basin accumulation, Nepal-side information where legitimate, barrage/gate state and discharge.
- Model propagation effects rather than relying only on local rain.

### Phase G — inundation
- Add DEM, river network, floodplain and drainage/geographic layers.
- Implement a documented spatial inundation engine.
- Prefer physically defensible hydraulic/geospatial methods where data supports them.
- Where an approximation is used, expose that limitation.
- Output inundated cells/extent and depth where possible, with confidence and model version.

### Phase H — satellite validation
- Add Sentinel-1 SAR acquisition/processing interfaces where feasible.
- Use it primarily for historical/observed flood extent and validation.
- Account for revisit/acquisition/processing latency.
- Compare predicted inundation with observed flood masks using suitable metrics such as IoU, precision, recall and F1.

### Phase I — spatial intelligence
- Add Bihar state/basin/district/block/panchayat/village/grid hierarchy.
- Implement location-to-nearest-station/grid/basin queries.
- Support location-specific rainfall, river, flood and inundation responses.

### Phase J — dashboard
- Add rainfall, river forecast, flood probability, inundation and satellite layers to the map.
- Keep layer timestamps, sources and data status visible.
- Add location search and forecast timeline.

### Phase K — alerts
- Add transparent dashboard/API/location alert rules.
- Design future SMS/email integrations without automatically sending operational alerts until configured.

### Phase L — reliability/security
- Add source health, retry/stale/failure monitoring, test fixtures, API validation and secret hygiene.
- Keep live-source failures explicit.

### Phase M — backtesting/documentation
- Build historical replay/backtesting.
- Produce reproducible evaluation reports.
- Record model versions, training periods, features, assumptions and limitations.
- Distinguish prototype capability from production-ready capability.

## Acceptance flow

For a selected Bihar location the system should eventually answer:

1. Current rainfall and source.
2. Recent rainfall accumulation.
3. Forecast rainfall when available.
4. Nearest river.
5. Current river level and trend.
6. Warning/danger threshold status.
7. Forecast river level.
8. Flood probability for supported horizons.
9. Predicted inundation area.
10. Predicted depth where supported.
11. Satellite-observed flood availability.
12. Confidence/freshness.
13. Source and model version.

## Manual data still required for higher accuracy

Code alone cannot create accurate event forecasting without suitable local training and validation data. The highest-value future inputs are:

- High-frequency historical rainfall observations for Bihar and relevant upstream/Nepal basins.
- Historical river level time series with station metadata and threshold levels.
- Flood event start/end dates and geospatial extent.
- Historical barrage/reservoir releases and gate status where available.
- River discharge where available.
- DEM/elevation and river/floodplain geometry.
- Historical Sentinel-1 flood masks or other trusted flood-extent reference data.
- Administrative boundaries and optional exposure layers.
- Any institution-provided ground-truth flood depths/extent for validation.

Do not commit sensitive credentials or restricted source material. Prefer public, official or explicitly authorized datasets.
