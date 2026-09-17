# VARSHAGUARD

AI/ML-based integrated heavy-rainfall early-warning and inundation-prediction prototype for SIH26071.

> **Prototype status:** This repository is a demonstration system, not an operational government warning service. Probabilities and inundation values are prototype outputs and must not be used for safety-critical decisions.

## Architecture

```text
Historical rainfall dataset
        |
        +--> Daily feature engineering --> Random Forest --> rainfall flood probability
                                                           |
Live Bihar district rainfall ------------------------------+
                                                           |
Live Bihar river observations --> threshold/rise signal --+--> district risk fusion
                                                           |
                                                           +--> Bihar dashboard

Flask API --> Leaflet/Chart.js dashboard
```

The original rainfall ML prototype supports the two study regions present in the processed training dataset: **Assam** and **Uttarakhand**. Bihar Live now has a district-level Random Forest inference path that converts the historical rainfall table into daily training examples and compares live Bihar district rainfall against that learned historical pattern. Live Bihar river observations are fused as a separate hydrological signal.

**Important:** the current historical rainfall table is not documented as a Bihar-labeled flood-outcome dataset. Therefore the Bihar Random Forest is explicitly reported as **cross-region and not Bihar-calibrated**. Do not describe its probability as a validated Bihar probability until Bihar historical flood outcomes are added and the model is retrained/evaluated on a Bihar-specific time split.

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
    ml_engine.py

data/
  processed/
    flood_warning_ml_ready_v2.csv

models/
  flood_warning_random_forest_v2.pkl

frontend/
  index.html
  bihar-live.html
  script.js
  style.css

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

## Train the original ML model

Run this from the repository root:

```bash
python backend/train_model.py
```

The trainer performs an 80/20 train/test split and reports accuracy and ROC-AUC when the test set contains both classes. The saved model is written to:

```text
models/flood_warning_random_forest_v2.pkl
```

## Bihar Live Random Forest engine

The Bihar ML endpoint is:

```http
GET /api/bihar-live/ml-risk
```

It performs the following pipeline on the backend:

1. Reads the historical rainfall training table.
2. Aggregates the hourly records into daily training examples.
3. Trains a `RandomForestClassifier` using rainfall accumulation/intensity features plus month/monsoon timing.
4. Fetches the latest three daily Bihar district rainfall snapshots from the open IMD rainfall mirror.
5. Builds matching 24h/48h/72h rainfall features for each Bihar district.
6. Fetches live Bihar river observations from the Bihar FMIS / WRD sources.
7. Calculates a separate river threshold/rise pressure per district.
8. Fuses rainfall-model probability and river pressure into the displayed district risk.

The response includes the historical holdout accuracy/ROC-AUC, training/test row counts, live rainfall values, river signal, and an explicit `bihar_calibrated` flag.

### Current limitation

The Random Forest can only be called Bihar-calibrated after it has been trained and evaluated using historical **Bihar** flood outcomes. The repository's current processed dataset is documented as Assam/Uttarakhand study data. The current Bihar endpoint therefore provides a **cross-region prototype signal**, not a validated operational Bihar forecast.

## Bihar Live river endpoint

```http
GET /api/bihar-live/stations
```

The backend uses Bihar FMIS first and a Bihar WRD CWC-station table as fallback. It does not silently serve the old dated rainfall CSV when the live source fails.

## Run the API and dashboard

```bash
python backend/app.py
```

Open:

```text
http://127.0.0.1:5001/
```

The Flask app serves the dashboard and API from the same origin.
