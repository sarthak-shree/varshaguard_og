# VARSHAGUARD

AI/ML-based integrated heavy-rainfall early-warning and inundation-prediction prototype for SIH26071.

> **Prototype status:** This repository is a demonstration system, not an operational government warning service. Probabilities and inundation values are prototype outputs and must not be used for safety-critical decisions.

## Architecture

```text
Prototype / live inputs
        |
        +--> Rainfall dataset --> Random Forest --> Flood probability --> Risk
        |
        +--> Bihar river observations --> 24h transparent baseline
                                      --> Inundation spatial proxy
        |
        +--> Flask API --> Web dashboard (Leaflet + Chart.js)
```

The main rainfall ML prototype currently supports the two study regions present in the processed dataset: **Assam** and **Uttarakhand**. Bihar Live now uses a backend live-station service rather than the dated rainfall-training CSV. The source observation timestamp is retained in the backend response for audit/debugging but is intentionally not rendered in the public Bihar Live table.

## Project Structure

```text
backend/
  app.py
  model.py
  prediction.py
  risk.py
  train_model.py
  bihar_live/
    data_service.py
    forecast_engine.py

data/
  processed/
    flood_warning_ml_ready_v2.csv

frontend/
  index.html
  bihar-live.html
  script.js
  style.css

models/
  flood_warning_random_forest_v2.pkl

requirements.txt
vercel.json
README.md
```

## Install

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

## Train the ML model

Run this from the repository root:

```bash
python backend/train_model.py
```

The trainer now performs an 80/20 train/test split and reports accuracy and ROC-AUC when the test set contains both classes. The saved model also stores its evaluation metadata.

Output:

```text
models/flood_warning_random_forest_v2.pkl
```

## Run the API and dashboard

```bash
python backend/app.py
```

Open:

```text
http://127.0.0.1:5001/
```

The Flask app serves the dashboard and API from the same origin, so no second frontend server is required.

## API

### Health

```http
GET /api/health
```

### Supported study regions

```http
GET /api/regions
```

### Station list

```http
GET /api/stations?region=Assam
GET /api/stations?region=Bihar
GET /api/bihar-live/stations
```

`Bihar` station requests are fetched at request time from the configured CWC/India-WRIS source. API responses are sent with no-store cache headers to avoid Vercel/browser reuse of an old response.

### Flood risk

```http
GET /api/flood-risk?region=Assam&station=...
```

### Station risk map

```http
GET /api/flood-risk-map?region=Assam
```

### Rainfall history/trend

```http
GET /api/rainfall?region=Assam&station=...
GET /api/history?region=Assam&station=...
```

### Bihar Live 24-hour baseline

```http
POST /api/bihar-live/forecast
Content-Type: application/json
```

Example body:

```json
{
  "water_level_m": 52.4,
  "warning_level_m": 52.0,
  "danger_level_m": 53.0,
  "water_level_1h_before_m": 52.2
}
```

The Bihar endpoint returns two clearly separated outputs:

1. `flood_forecast`: transparent hydrological baseline using current river level, warning/danger thresholds, and one-hour rise.
2. `inundation_forecast`: spatial proxy, **not** a validated DEM/hydraulic inundation map.

## Live Bihar data design

The Bihar Live page calls `/api/bihar-live/stations` on every initial load and manual refresh, with a cache-busting query parameter and `cache: "no-store"`. It automatically refreshes every 15 minutes.

The backend performs the external source request, normalizes station names, river/district, water levels, thresholds and coordinates, and retains the source observation time as an internal field. The frontend deliberately does not show that raw timestamp.

The live-source integration depends on the configured CWC/India-WRIS endpoint returning a compatible JSON station feed. If that upstream service is unavailable or changes its response schema, the API returns an explicit 502 error rather than silently showing the old dated CSV as live data.

## Data and model caveats

The repository contains a processed prototype rainfall dataset and a saved Random Forest model. The current ML pipeline is a study-region prototype; it does **not** yet ingest live satellite imagery, Doppler radar, NWP forecasts, or validated Bihar flood labels.

The Bihar Live forecasting code explicitly reports that its probability is not calibrated and that its inundation output is a proxy rather than physical hydraulic/DEM modelling. Do not describe those outputs as operational or physically validated forecasts.

## What remains for a stronger SIH implementation

- Live satellite/radar ingestion and data-quality checks
- Real NWP forecast features
- Bihar-specific historical rainfall + river + flood labels
- Proper temporal/spatial train-validation-test design
- Calibrated probabilistic ML evaluation
- DEM + river network + historical flood-extent data
- A real spatial inundation model
- Alert delivery and audit logging
- Automated API/model tests
- Production deployment monitoring
