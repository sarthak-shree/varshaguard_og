# VARSHAGUARD

VarshaGuard is an SIH26071 research prototype for heavy-rainfall and flood-risk early warning.

> **Safety status:** This is not an operational government warning service. Do not use prototype probabilities, risk bands, or inundation proxies for safety-critical decisions. Follow official CWC, IMD, and disaster-management guidance.

## Bihar Live: what is connected today

The dashboard in `frontend/bihar-live.html` calls:

```http
GET /api/bihar-live/model/live
```

That endpoint is implemented in `backend/bihar_live/api.py` and delegates to `backend/bihar_live/research/live_prediction.py`. It loads the checked-in research artifact:

```
models/research/cwc_bihar_gauge_24h_stage_research.joblib
models/research/cwc_bihar_gauge_24h_stage_research.metadata.json
```

The model estimates whether one of 13 CWC river gauges will reach its published **warning level** during the next rolling 24 hours. The dashboard highlights Patna Gandhighat and Muzaffarpur Sikandarpur. It is a gauge threshold-crossing estimate—not a district-wide, neighborhood, inundation-extent, or flood-depth probability. CWC input freshness and coverage affect whether the API returns an estimate.

The live inference path fetches observed CWC HHS stage and MPS rainfall records. The dashboard separately displays an Open-Meteo next-24-hour rainfall outlook. Forecast rainfall is **not** blended into the CWC model probability because the saved model was not trained and validated with forecast-rain inputs. The CWC feed is a public endpoint, not a documented stable production API; inference is cached briefly and fails closed when data/model inputs are unavailable or stale.


### Backend-driven 24-hour probability selector

The frontend now requests a compact summary from:

```http
GET /api/bihar-live/probability?district=patna&type=flood
GET /api/bihar-live/probability?district=muzaffarpur&type=flood
GET /api/bihar-live/probability?district=patna&type=heavy_rainfall
```

The browser displays only the selected forecast's percentage and status; live CWC retrieval and model inference remain in the backend. The flood percentage is only the experimental probability that the selected CWC gauge reaches its published warning level in the next 24 hours. When the gauge is already at/above a threshold, or inputs are stale/unavailable, the endpoint withholds a forecast percentage and reports the observed/unavailable state instead. Heavy-rainfall probability is explicitly unavailable until a separate rainfall model is implemented and validated; the UI does not substitute the flood score or invent a number. The Open-Meteo discharge panel is not displayed as a frontend probability.

### Live Open-Meteo river-discharge context

Bihar Live also exposes a separate daily hydrological forecast endpoint:

```http
GET /api/bihar-live/flood-discharge?district=patna
GET /api/bihar-live/flood-discharge?district=muzaffarpur
```

This endpoint calls the [Open-Meteo Flood API](https://open-meteo.com/en/docs/flood-api) at the existing Patna Gandhighat and Muzaffarpur Sikandarpur focus-point coordinates. It requests daily river discharge, mean, median, maximum, minimum, 25th/75th percentiles, six GloFAS v3/v4 model variants, and ensemble output. Results include source, fetch timestamp, units, and model metadata; the response is cached for up to 15 minutes and network failures return an explicit unavailable state. The seven-day forecast and three-day past window keep the request bounded.

**Interpretation limit:** this is modelled river-discharge context, not a flood probability, CWC warning-level prediction, neighborhood inundation estimate, or official alert. It is deliberately kept separate from the CWC classifier and does not change its probability. Use the provider's returned units and metadata; do not assume the API's discharge series is directly interchangeable with a CWC gauge stage reading.

## Model training and validation

Training entry point:

```bash
python backend/bihar_live/research/fetch_cwc_bihar_hourly.py
python backend/bihar_live/research/train_cwc_gauge_rolling_24h.py
```

The trainer consumes `data/bihar_live/research/cwc_bihar_gauge_hourly.csv`, writes the artifact and metadata under `models/research/`, and exports time-holdout predictions under `data/bihar_live/research/`. Install the project requirements first; the historical downloader also requires `duckdb`.

The target is defined only at six-hourly issue times when the gauge is still below its published warning level. A positive label means a valid observed stage reaches that warning level in the following rolling 24 hours. Training excludes issue windows without sufficient future observations: at least 18 observations, first future observation within 3 hours, no observation gap over 6 hours, and final observation at least 23 hours into the target horizon. The label's first observed crossing time is retained for lead-time diagnostics and is never used as a model feature.

The split is chronological: training labels end before 2025, 2025 is used for model/threshold selection, and 2026 is held out for evaluation. Explicit boundary checks fail training if label horizons cross split boundaries. The trainer reports precision, recall, average precision (PR-AUC-style ranking diagnostic), ROC-AUC, Brier score, a prevalence-baseline Brier score, confusion matrix, reliability bins / expected calibration error, and per-gauge holdout metrics. It also reports lead time for detected positive issue windows. These windows overlap and must not be counted as independent flood events.

**Important:** The model probabilities are not currently calibrated by a fitted calibration model. Reliability bins and expected calibration error are diagnostics, not a calibration step. Model metrics are generated by a training run and should not be copied from old documentation after changing data or label rules. Sparse positive examples—especially at individual focus gauges—make station-specific estimates uncertain. The model remains research-only.

See [rolling-model training notes](backend/bihar_live/research/README.md) for dataset and evaluation caveats.

### Latest reproducible holdout run (28 October 2026)

The CWC hourly archive was fetched and the rolling trainer completed in GitHub Actions with explicit future-coverage checks: at least 18 future observations, the first within 3 hours, no gap longer than 6 hours, and the final observation at least 23 hours after issue time. The selected candidate was **Random Forest**, with a decision threshold of **0.206491** selected on 2025 validation data. The 2026 holdout contained 5,884 issue windows, of which 132 (2.24%) were positive.

| 2026 holdout metric | Result |
|---|---:|
| Precision at validation-selected threshold | 34.20% |
| Recall at validation-selected threshold | 69.70% |
| Average precision (PR ranking metric) | 0.5506 |
| ROC-AUC | 0.9760 |
| Brier score | 0.01506 |
| Brier score for training-prevalence baseline | 0.02200 |
| Confusion matrix (TN / FP / FN / TP) | 5,575 / 177 / 40 / 92 |
| Expected calibration error (10 equal-width bins, occupied bins) | 0.01309 |
| Median lead time among detected positive issue windows | 9 hours |

The trainer's deduplicated episode proxy found **33 observed gauge warning-level crossing episodes** in the 2026 holdout, of which **32 were detected** (episode recall **96.97%**); median lead time from the earliest predicted-positive issue window to the first observed crossing was **17 hours**. This groups by station and first observed crossing timestamp and is not a verified flood-event metric. The Patna Gandhighat slice had only **8 positive windows** in 351 test rows: recall was 62.5% (5/8) and precision was 55.6% (5/9). Muzaffarpur Sikandarpur had **zero positive test windows**, so local recall/precision cannot be estimated. The aggregate holdout contains overlapping issue windows—not independent flood events. The trainer now also reports deduplicated observed gauge-crossing episodes, grouping rows by station and first observed crossing timestamp; event-level recall and lead time are in the model metadata. These are gauge-threshold episodes, not verified flood events. The ECE is only a coarse diagnostic. The classifier is not probability-calibrated. These results are a research backtest, not operational validation.

Run metadata, including the input CSV SHA-256, full reliability bins, station-level metrics, split counts, and threshold, is stored in `models/research/cwc_bihar_gauge_24h_stage_research.metadata.json`. The training workflow also publishes the source snapshot and holdout predictions as a short-lived GitHub Actions artifact for reproducibility.

## Rainfall and river-stage forecast pipeline (research baseline)

The current forecast additions are deliberately conservative and do not claim a newly trained ML model:

- `/api/bihar-live/data-quality?district=patna` reports CWC stage freshness and independent Open-Meteo rainfall/discharge source status, timestamps, cache age when available, and units.
- `/api/bihar-live/forecast/rainfall?district=patna` exposes the Open-Meteo provider forecast, hourly rainfall, and derived 1/3/6/12/24-hour accumulation totals. This is a numerical weather forecast from the provider, not a locally trained rainfall model or an independently validated Bihar rainfall prediction.
- `/api/bihar-live/forecast/river-stage?district=patna` fits a simple least-squares trend to recent CWC gauge readings and extrapolates 1/3/6/12 hours. It requires at least three distinct readings spanning two hours and otherwise returns an explicit unavailable state. This is a transparent baseline, not a trained ML model, and its in-sample residual RMSE is not a confidence interval.
- The dashboard keeps rainfall accumulation, observed CWC stage, and Open-Meteo discharge in separate units and panels. Stage (m) and discharge (flow per unit time) are not averaged together. Patna Gandhighat and Muzaffarpur Sikandarpur are not assumed to be an upstream/downstream pair.
- The public source adapters use bounded in-process caches and return source timestamps/quality metadata where available. A serverless process can restart, so this is not a durable historical data warehouse.

#### End-to-end acquisition and evaluation job

A GitHub Actions workflow at `.github/workflows/public-data-pipeline.yml` downloads the catalogued public CSV snapshots, inspects them, attempts schema-aware normalization, builds coverage reports, trains only targets that pass the minimum-label gate, and uploads raw files plus reports as a 30-day artifact. It runs on relevant pushes to this feature branch and can be started manually with the workflow-dispatch action.

The local equivalent after download is:

```bash
python scripts/fetch_public_sources.py --all
python scripts/process_public_sources.py
```

The pipeline writes `data/processed/public_sources/pipeline_report.json`. Source schema mismatches are recorded as `schema_review_required`; they are not silently coerced. Cross-agency station matching is disabled unless a reviewed explicit mapping is supplied. The observation normalizer records missingness, duplicate conflicts, timestamp assumptions and median sample interval. Exact-hour labels are required by the training builder, so daily stage sources will not be treated as hourly forecast labels.

The source pipeline now normalizes the published NWIC columns `Station`, `Data Acquisition Time`, `Telemetry Hourly Rainfall (mm)`, and `River Water Level Telemetry Hourly (meter)`. The downloaded rainfall files contain 15-minute timestamp snapshots despite the hourly rainfall field name; the alignment policy uses the **last snapshot in each Asia/Kolkata clock hour**, never sums repeated values, and never fills missing hours. This assumption is explicitly recorded in coverage output and should be reviewed against the data producer's documentation.

The manually observed daily dataset's downloaded columns contain `Date`, `Discharge (M3/s)`, and `Zero of Gauge (Mts)` metadata, but no measured water-level column. It is retained for inspection and deliberately excluded from stage training.

The training pipeline saves `chronological_test_predictions.csv` only for eligible real-data targets. Rainfall test-event precision/recall uses a 95th-percentile threshold learned from training-period rainfall, clearly marked as a research threshold rather than an official warning threshold. Model selection is validation-only; a 24-hour embargo separates chronological partitions to reduce horizon overlap. No live inference model is replaced.

To convert held-out stage predictions into warning-level event flags, copy `data/bihar_live/research/station_warning_levels.template.csv` to `station_warning_levels.csv` and fill it only with reviewed, official gauge warning levels and the exact normalized `station_id`. Do not guess station IDs or warning levels. The current independent-event ledger has no eligible ground-verified station-level events with explicit onset times, so event recall/lead time remain `not_estimable`; event precision/false-alarm rate additionally require a complete negative-event ledger.

For the current independent-event ledger, run:

```bash
python scripts/evaluate_independent_events.py --predictions predictions.csv --official-ledger data/bihar_live/research/independent_flood_events.csv
```

The ledger currently has broad-area reports/rapid maps without ground-verified station-level event onset. The expected and scientifically correct status is `not_estimable` until event records are independently verified and spatially/time matched. Event precision and false-alarm rates additionally require a complete matched negative-event ledger.

### Public source discovery and download

The public-source downloader is `scripts/fetch_public_sources.py`. It downloads raw CSV snapshots when run from a machine with network access, computes SHA-256 hashes, captures column names/sample rows, and records provenance in `data/raw/public_sources/manifest.json`. It deliberately does **not** silently convert unknown columns into training labels.

```bash
python scripts/fetch_public_sources.py --all
# or one source at a time
python scripts/fetch_public_sources.py --source bihar_hourly_rainfall
```

Initial catalog:
- Bihar Water Department hourly telemetry rainfall (2021–2025): https://www.nwdp.nwic.gov.in/dataset/rainfall-bihar-telemetry-hourlydata
- CWC Bihar hourly telemetry rainfall (2021–2025): https://nwdp.nwic.gov.in/en/dataset/rainfall-cwc-telemetry-hourly
- Bihar Water Department manual daily river stage (2020–2025): https://nwdp.nwic.gov.in/en/dataset/surface-water-level-manual-daily-bihar
- Official MHA/NDMI flood situation report (30 Sep 2024): https://www.ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=NEW2208
- Bihar WRD/FMISC data services: https://www.fmiscwrdbihar.gov.in/
- Research-only river-stage comparison portal (BIRA/RAP): https://bihar.rap.ucar.edu/flow
- GitHub India Flood Inventory: https://github.com/hydrosenselab/India-Flood-Inventory
- GitHub WRIS API client (community maintained): https://github.com/DrJagadeeshG/india-water-data
- Reddit is recorded only as qualitative source-discovery context, never as an observation/label source.

Data acquisition caveats: official portals expose distinct temporal resolutions and station schemas. Daily stage cannot be relabeled as hourly stage. CWC and Bihar WRD station IDs must be reconciled through documented station metadata, not guessed from names. Event reports need station/river-specific time windows before they become score-eligible flood labels. Community repositories require license, provenance and target-scope checks; Bangladesh datasets are not Bihar training labels.

### Historical collection and chronological research training

The repository now includes `backend/bihar_live/historical_pipeline.py` for idempotent observation storage, timestamp alignment, future-label construction, and chronological baseline evaluation.

1. Configure `VARSHAGUARD_HISTORY_DB` to a durable database file on a persistent mounted volume. The default SQLite path is for local development; Vercel/serverless local files are ephemeral and are **not** a durable history store.
2. On a persistent worker/host, run `python -m backend.bihar_live.historical_pipeline --collect-live` on a schedule (for example, hourly). It uses the existing CWC FFS adapter and persists quality-screened HHS stage and MPS rainfall observations with station identity, source, units, UTC-normalized timestamps, source timestamp, quality flag and schema version. The upstream endpoint only returns a recent window; repeat collection and retain the store.
3. Alternatively, import normalized CSV rows containing `station_id,observed_at,source,variable,value,unit` and optional `quality_flag,source_timestamp` with `--import-csv path.csv`.
4. Run `python -m backend.bihar_live.historical_pipeline --train` after enough aligned observations have accumulated. It builds exact-hour lag features and exact future labels, does not fill missing target labels, uses chronological train/validation/test partitions, selects candidate model by validation MAE, and reports final test metrics against persistence. Targets without enough labels are explicitly marked `insufficient_labels`; all outputs remain research-only.
5. Check `/api/bihar-live/model/evaluation` for the persisted real-data evaluation status. The old generated-data example is available separately at `/api/bihar-live/model/evaluation/synthetic-demo` and is never treated as evidence of real forecast skill.

Important limitations: CWC observations may be irregular rather than hourly, and the builder intentionally refuses to fabricate exact-hour labels. This means some/all targets may remain untrainable until enough timestamped records exist at the required horizons. Open-Meteo weather forecasts are not substituted for observed rainfall labels. A training report alone does not qualify a model for operational alerts; use independent event evaluation and a documented review before deployment.

### Requirements before training a new ML forecast

Persist timestamped source snapshots with source/model version, coordinate/grid mapping, units, and quality flags. Build aligned training rows with future rainfall-gauge totals and future CWC stage labels at each horizon; avoid leakage by splitting chronologically by event/time, not randomly. Compare persistence and trend baselines against any LightGBM/XGBoost model on a held-out season and independent events. Report MAE/RMSE for stage and rainfall, event precision/recall and lead time for threshold crossings, calibration and false-alarm rates where appropriate. Until these steps are complete, forecast outputs remain research-only and are not official warnings.

## Separate prototype scaffold endpoints

The same Flask app also exposes `/api/bihar-live/health`, `/sources`, `/fusion`, `/weather`, and `/model/evaluation`.

- `/weather` fetches Open-Meteo forecast rainfall for the selected focus gauge.
- `/health` and `/sources` describe the separate prototype scaffold's `DATA_MODE`.
- `/fusion` currently passes fixed demonstration values into a heuristic fusion function. It is **not** real radar/satellite/observational/NWP fusion.
- `/model/evaluation` generates synthetic observations and evaluates a demo baseline. Its metrics are **not evidence** of the live CWC model's predictive performance.
- The real-mode adapters in the scaffold fail closed when sources are not configured; they do not silently turn synthetic observations into real data.

These scaffold routes should not be described as operational multi-source data integration.

## Other legacy model and documentation

The repository also contains a separate older daily danger-level research model documented in [CWC stage research notes](docs/bihar_live/cwc-stage-research.md). Its metrics refer to that separate model and must not be presented as metrics for the rolling 24-hour warning-level model used by Bihar Live.

The older README description of `/api/bihar-live/ml-risk`, a calibrated rainfall/flood-inventory model, and `models/bihar_flood_24h_rainfall_model.pkl.b64` does not describe the current Bihar Live dashboard inference path. The current dashboard calls `/api/bihar-live/model/live` and uses the CWC gauge artifact listed above.

## SIH26071 next priorities

1. **P0 — trustworthy evaluation:** Rebuild labels from the source CSV, rerun the chronological backtest, inspect per-gauge calibration/precision/recall and lead time, and validate on more independent flood seasons. Do not make operational claims from overlapping windows.
2. **P1 — real multi-source inputs:** Add timestamp-aligned satellite precipitation, Doppler radar, and numerical weather prediction forecasts, with source freshness/quality flags and historical equivalents for training.
3. **P2 — inundation modelling:** Obtain Bihar DEM, river/floodplain geometry, and observed flood-extent labels; validate any spatial output against observed inundation. A map overlay alone is not hydraulic inundation prediction.
4. **P3 — operational readiness:** Add monitored source health, versioned data/model lineage, alert delivery and escalation tests, fail-safe handling, security review, and approval from relevant domain authorities.

## Run locally

```bash
python -m venv .venv
```

Windows:

```powershell
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

The Flask app serves the dashboard and API from the same origin. Run tests with `pytest -q`.

## Voice assistant

The dashboard voice assistant records up to 20 seconds in the browser, sends audio to Groq Whisper for transcription, uses the existing Groq chat model for a response, and uses Microsoft's online Edge TTS service for spoken output. Configure `GROQ_API_KEY` on the server; `GROQ_STT_MODEL` is optional and defaults to `whisper-large-v3`. Microphone access requires HTTPS or localhost. Do not speak sensitive personal information into the assistant.
