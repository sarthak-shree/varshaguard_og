# Bihar Live ML model layout

The Bihar Live flood-probability model is a separate model family from the frozen v0.2.0 Assam/Uttarakhand prototype.

## 24-hour flood-probability model

**Target:** `1` when a river station reaches or exceeds its configured danger level at least once during the next 24 hourly observations; otherwise `0`.

This is a **station-level flood-warning probability**, not a spatial inundation prediction.

### Features

- current water level
- level / warning ratio
- level / danger ratio
- 1h, 3h, 6h, 12h and 24h level changes
- 6h and 24h means
- 24h variability
- 6h and 24h maxima
- hour and month

### Validation

The training script uses a chronological 80/20 holdout and model comparison between Random Forest and logistic regression. The selected classifier is probability-calibrated on the training period with a time-series split. Selection is based on PR-AUC, with ROC-AUC, Brier score, precision, recall and F1 also recorded.

### Train

```bash
python -m backend.bihar_live.train_flood_probability --input <BIHAR_RIVER_LEVEL_CSV>
```

The command writes:

- `flood_probability.joblib`
- `flood_probability.json`

The runtime loads these artifacts automatically. If they are absent or the station has fewer than 25 usable hourly observations, the API deliberately falls back to the transparent operational score and does **not** call it an ML probability.

### Data source

The initial training pipeline is designed for Bihar Water Department hourly river-level data published through the National Water Data Portal (NWDP/NWIC). The portal currently exposes Bihar hourly telemetry datasets for historical periods and current years. Keep the downloaded source CSV outside Git if it is large or restricted by repository policy.

Do not copy the v0.2.0 model into this directory.
