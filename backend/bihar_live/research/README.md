# Bihar rolling 24-hour CWC gauge model

## Target and scope

The dashboard estimates whether one of 13 Bihar CWC gauges, currently focused on Patna Gandhighat and Muzaffarpur Sikandarpur, will reach its published **warning level** in the next rolling 24 hours. This is a gauge-level threshold-crossing estimate, not a forecast of flooded streets, blocks, or grid cells.

## Rebuild the historical dataset and model

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m pip install duckdb
python backend/bihar_live/research/fetch_cwc_bihar_hourly.py
python backend/bihar_live/research/train_cwc_gauge_rolling_24h.py
```

The trainer reads `data/bihar_live/research/cwc_bihar_gauge_hourly.csv`. It writes the model and metadata to `models/research/` and writes holdout predictions to `data/bihar_live/research/`. The metadata records the source CSV SHA-256, selected model, feature list, split counts, metrics, and artifact paths.

## Label and leakage controls

- Issue rows are sampled every six hours when a valid CWC stage reading is available and the current stage is below the published warning level.
- A positive target means at least one valid HHS stage observation in `(issue time, issue time + 24 hours]` reaches the warning threshold.
- A row is excluded unless there are at least 18 valid future stage observations, the first arrives within 3 hours, no gap between future observations exceeds 6 hours, and the final observation is at least 23 hours after issue time. This reduces, but cannot eliminate, bias from irregular or missing observations.
- The timestamp of the first observed crossing is retained only for evaluation and is excluded from model features.
- Training uses labels whose horizons end before 2025; 2025 selects the model and decision threshold; 2026 is the untouched time-based holdout. The script checks that training label horizons do not overlap validation and validation horizons do not overlap test.

## Metrics and interpretation

The training run reports precision, recall, average precision, ROC-AUC, Brier score against a training-prevalence baseline, confusion matrix, reliability bins, expected calibration error (ECE), and per-station holdout metrics. It also reports lead-time statistics for detected positive **issue windows** based on the first observed crossing timestamp.

Six-hourly issue windows overlap. Multiple true-positive windows may refer to the same threshold-crossing episode, so window counts are not independent event counts. A gauge with only one class in the test period is explicitly marked as not reliably estimable rather than assigned a misleading station-specific score. Review positive counts and confidence limitations alongside every metric.

### Latest measured holdout snapshot (28 October 2026)

GitHub Actions fetched the current public CWC mirror and retrained the pipeline with explicit target-window coverage checks: at least 18 future observations, first observation within 3 hours, no gap over 6 hours, and final observation at least 23 hours after issue time. The selected model was Random Forest. The 2026 holdout had 5,884 issue windows and 132 positive labels (2.24% prevalence).

- Precision: **34.20%**; recall: **69.70%** at the 2025-validation-selected threshold of **0.206491**.
- Average precision: **0.5506**; ROC-AUC: **0.9760**.
- Brier score: **0.01506**, compared with **0.02200** for the training-prevalence baseline.
- Confusion matrix: **5,575 TN, 177 FP, 40 FN, 92 TP**.
- Expected calibration error: **0.01309** (10 equal-width bins).
- Median time from issue time to first observed crossing among detected positive windows: **9 hours**, across 92 detected positive issue windows.

The deduplicated holdout episode proxy found **33 observed gauge warning-level crossing episodes**, with **32 detected** (episode recall **96.97%**) and a **17-hour median lead time** from the earliest predicted-positive issue window. Episodes are grouped by station and first observed crossing timestamp; these are not verified flood events. Patna Gandhighat had only 8 positive test windows (recall 5/8 = 62.5%; precision 5/9 = 55.6%). Muzaffarpur Sikandarpur had no positive test windows, so its local sensitivity is not estimable. These are overlapping issue-window metrics, not independent flood-event counts; the aggregate results cannot establish operational safety or neighborhood-level flood prediction skill. The trainer additionally deduplicates rows into observed gauge-threshold crossing episodes using (station code, first observed crossing timestamp), then reports episode recall and lead-time distribution. This is an episode proxy from gauge observations, not a verified flood-event catalogue.

The current classifier does not fit a probability calibration model. ECE/reliability bins are diagnostics only, and the F2 decision threshold is selected on the separate 2025 validation set. After changing source data or label rules, rerun the trainer before quoting metrics; historical numbers from older label definitions are not comparable.

The model is experimental and **not operationally eligible**. Validate with more independent flood seasons and CWC/IMD/disaster-management domain experts before considering public-safety use.

## Source and attribution

The hourly archive is mirrored from CWC Flood Forecast System records by [diagram-chasing/cwc-flood-forecasts](https://github.com/diagram-chasing/cwc-flood-forecasts). The mirror documentation states ODbL and requests CWC attribution; confirm the applicable terms before redistributing data.

`train_cwc_gauge_nextday.py` is a separate legacy research trainer and writes a separate artifact. It does not train or overwrite the rolling model used by the dashboard.
