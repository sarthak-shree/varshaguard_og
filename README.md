# VARSHAGUARD

AI/ML-based integrated heavy-rainfall early-warning and inundation-prediction prototype for SIH26071.

> **Prototype status:** This is a research/demo system, not an operational government warning service. Do not use prototype probabilities or inundation proxies for safety-critical decisions.

## Bihar Live: current architecture

```text
Live Bihar district rainfall (last 14 days)
                 |
                 v
       Same feature schema as training
                 |
                 v
  Calibrated Bihar flood-event ML model
                 |
                 +----> P(documented flood-event start in next 24h)
                 |
Live Bihar river level + warning/danger + 1h trend
                 |
                 v
        Hydrologic confirmation
                 |
                 +----> Integrated LOW / MEDIUM / HIGH alert
                 |
                 v
       Inundation spatial proxy

Flask API --> Leaflet dashboard
```

The Bihar endpoint now has a real **flood-event target** rather than relabelling a heavy-rain classifier as flood probability. The saved model is trained from the supplied historical Bihar rainfall table and the supplied India flood inventory. The live endpoint fetches current district rainfall and current Bihar river observations at request time.

### Important data limitation

The supplied historical rainfall and river telemetry periods overlap only sparsely at the district/event level. There are not enough overlapping 24-hour flood-event labels to honestly train a joint rainfall+river supervised classifier. Therefore the calibrated ML probability is rainfall/flood-inventory trained, while current river level, warning/danger status and 1-hour trend are kept as independent hydrologic evidence for the integrated alert. The API does **not** pretend that river features were learned when they were not.

The supplied files also do not contain a Bihar DEM, complete floodplain geometry, or hydraulic simulation inputs. Inundation extent/depth shown by the dashboard is consequently a clearly labelled spatial proxy, not a physical flood map.

## Bihar 24-hour ML endpoint

```http
GET /api/bihar-live/ml-risk
```

Optional district forecast:

```http
GET /api/bihar-live/forecast?district=PATNA
```

or:

```http
POST /api/bihar-live/forecast
Content-Type: application/json

{"district":"PATNA"}
```

The response contains:

- `flood_probability` and `flood_probability_percent`
- prediction horizon (`24` hours)
- calibrated model metadata and validation metrics
- current rainfall features and data timestamp
- live river level, warning/danger counts and 1-hour rise
- `river_confirmation` (`NORMAL`, `RISING`, `WARNING`, or `DANGER`)
- integrated `risk` state
- explicitly labelled inundation proxy
- source URLs and live-fetch timestamp

## Model target

The Bihar model target is:

```text
P(documented Bihar flood event starts in the target district within the next 24 hours)
```

The historical flood inventory is used only as the event label source. The trainer uses chronological train/calibration/test periods and isotonic calibration; the final test period is not used to fit the calibrator.

## Data and training

The runtime model artifact is stored at:

```text
models/bihar_flood_24h_rainfall_model.pkl.b64
```

The artifact is loaded at runtime and the API never retrains the model on a request.

The current model was trained offline from the supplied `bihar_historical_rainfall_ml_ready.csv` and `IndiaFloodInventory.csv` assets. RF/XGBoost comparison was performed during model development; the saved compact artifact contains the selected XGBoost model and isotonic calibrator.

Because the available historical labels are event-inventory records rather than a dense operational flood-observation series, validation metrics should be treated as prototype research diagnostics, not evidence of operational accuracy.

## SIH26071 expansion path

The problem statement calls for integration of satellite, radar, observational weather and numerical weather prediction inputs. The current repository does not contain sufficient live/training assets for all of those channels. The architecture is therefore prepared for additional feature groups without fabricating them.

To move from this prototype to a stronger SIH26071 implementation, add:

1. aligned historical rainfall + river + flood/inundation labels across more Bihar districts and years;
2. satellite precipitation features;
3. Doppler-radar precipitation/echo features;
4. NWP/QPF forecast features for the next 24 hours;
5. Bihar DEM and floodplain/river geometry;
6. observed flood-extent labels for spatial inundation validation;
7. rolling backtests and per-district calibration/skill reporting.

## Run locally

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
python backend/app.py
```

The Flask app serves the dashboard and API from the same origin.
