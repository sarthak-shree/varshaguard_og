# CWC gauge threshold crossing: research model

This is an offline research artifact for Bihar Live. It estimates whether a selected CWC gauge that is below its published danger level on one observation day crosses that level on the next observed calendar day. It is not a grid-cell inundation model, and the daily observation convention does not establish an exact rolling 24-hour forecast.

## Source and reproduction

The observations come from the Central Water Commission Flood Forecast System, retrieved through the `diagram-chasing/cwc-flood-forecasts` Parquet mirror. The mirror releases its dataset under the Open Database License and requests attribution to CWC. Do not redistribute the source CSV; the fetch script downloads the selected station rows when needed.

```powershell
python -m pip install -r requirements.txt
python -m pip install "duckdb>=1.4"
python backend/bihar_live/research/fetch_cwc_bihar_history.py
python backend/bihar_live/research/train_cwc_gauge_nextday.py
```

The scripts write the downloaded source and holdout predictions to `data/bihar_live/research/`. The trained joblib artifact and its metadata are in `models/research/`. The artifact is committed for reproducibility, but it is not loaded by the dashboard or live API.

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

This model forecasts a gauge threshold crossing from daily observations and historical rainfall. It does not ingest archived weather forecasts, satellite or radar forecasts, and it does not estimate flood extent or depth. CWC gauge datums and reporting windows need expert verification. The model has not been connected to the application, validated for operational use, or approved for public warning decisions. The existing Bihar Live dashboard and APIs are unchanged by this experiment.

