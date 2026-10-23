# CWC gauge threshold crossing: research model and live display

The saved model estimates whether a selected CWC gauge that is below its published danger level on one observation day reaches that level on the next observed calendar day. The Bihar Live dashboard loads this model for Gandhighat (Patna) and Sikandarpur (Muzaffarpur) and fetches current CWC gauge inputs. It is not a grid-cell inundation model, and the daily observation convention does not establish an exact rolling 24-hour forecast.

## Live integration

The dashboard calls `GET /api/bihar-live/model/live`. The service reads the model artifact and metadata from `models/research/`, then queries the public CWC Flood Forecast System for `HHS` stage observations and `MPS` rainfall observations across the 13 model gauges. It aggregates readings by India-local calendar day and applies the stage/rain quality checks described below. The response includes the latest observation times, whether the current day is incomplete, per-target feature coverage, the historical test metrics, and limitations. Data is cached in each server process for five minutes.

The CWC FFS endpoint used by the application is on the official CWC domain, but the specific query route is not a documented stable API contract. If it changes or is unavailable, the dashboard hides model estimates and reports the feed unavailable. Vercel bundles the model artifact and its metadata with the Flask function.

The returned probability is an experimental estimate of a CWC gauge reaching its published danger stage on the next calendar day. It is not a flood probability, an inundation estimate, or an official warning. Only live CWC stage and rainfall observations are used; the system does not ingest IMD radar, satellite rainfall, or numerical weather predictions. Current-day rainfall and stage summaries may be incomplete, and missing inputs are median-imputed. The dashboard shows feature coverage so missing data is visible.

The dashboard labels the model percentage **Low** below the validation-selected F2 decision threshold, **Medium** from that threshold up to 50%, and **High** at 50% or above. The threshold currently stored with the model is 5.7717%. A danger-stage crossing that is already present in the latest observations is marked **High / 100% observed**, rather than presented as a future estimate. These are explanatory display bands, not official CWC warning levels; stale and unavailable readings do not receive a risk percentage.

## Source and reproduction

Historical training observations come from the Central Water Commission Flood Forecast System, retrieved through the `diagram-chasing/cwc-flood-forecasts` Parquet mirror. The mirror releases its dataset under the Open Database License and requests attribution to CWC. Do not redistribute the source CSV; the fetch script downloads the selected station rows when needed.

```powershell
python -m pip install -r requirements.txt
python -m pip install "duckdb>=1.4"
python backend/bihar_live/research/fetch_cwc_bihar_history.py
python backend/bihar_live/research/train_cwc_gauge_nextday.py
```

The scripts write the downloaded source and holdout predictions to `data/bihar_live/research/`. The trained joblib artifact and its metadata are in `models/research/`.

Sources:

- [CWC Flood Forecast System](https://ffs.india-water.gov.in/)
- [CWC observations mirror and ODbL attribution](https://github.com/diagram-chasing/cwc-flood-forecasts)

## Experiment design

- 13 Bihar gauges; target gauges include Gandhighat in Patna and Sikandarpur in Muzaffarpur.
- Daily water-level (`HHS`) and rainfall (`MPS`) values, with same-day readings from the local gauge network as context.
- Training target years through 2015, validation years 2016–2019, and untouched test years from 2020 onward.
- Only gauge-days still below danger are eligible. The positive label is a next-calendar-day maximum at or above danger. Missing dates are not treated as negative.
- Stage and rainfall quality screens are documented in the artifact metadata. 9,264 of 169,736 raw stage rows and 4 of 71,348 raw rainfall rows were excluded.

## Held-out results

The selected random forest uses a decision threshold chosen on validation data to maximize F2. On the untouched test period it achieved average precision 0.393417 against a 0.006953 event prevalence and Brier score 0.005457 against a 0.006906 training-prevalence baseline. At that threshold, precision was 0.192737 and recall was 0.737968: 578 false alarms and 49 missed crossings among 26,895 eligible gauge-days, including 187 crossings.

Patna Gandhighat had 14 positive test days and Muzaffarpur Sikandarpur had 4; those station-specific results are too sparse to establish dependable local performance. The pooled scores are research diagnostics and do not establish warning accuracy.

## Limits

This model forecasts a gauge threshold crossing from daily observations and historical rainfall. It does not ingest archived weather forecasts, satellite or radar forecasts, and it does not estimate flood extent or depth. CWC gauge datums and reporting windows need expert verification. Live feature coverage, probability calibration, and district-level usefulness have not been validated for operational use. The model is not approved for public warning decisions.
