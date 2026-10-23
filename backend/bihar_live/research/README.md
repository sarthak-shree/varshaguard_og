# Bihar rolling 24-hour gauge model

The dashboard estimates whether one of 13 Bihar CWC river gauges will reach its published **warning level** during the 24 hours after the latest accepted reading. This is a gauge threshold estimate, not a forecast of flooded streets, blocks, or grid cells.

## Refresh historical training data

From the repository root, install the optional downloader and fetch the public hourly archive:

```powershell
python -m pip install duckdb
python backend/bihar_live/research/fetch_cwc_bihar_hourly.py
python backend/bihar_live/research/train_cwc_gauge_rolling_24h.py
```

Training uses CWC HHS stage and MPS rainfall observations. Training rows are sampled every six hours; labels require at least 18 future stage observations over the rolling horizon. The 2023–2024 rows train candidate models, 2025 selects the model and risk threshold, and 2026 is kept as a time-based holdout. The deployed artifact is then refit using all available historical rows.

## Current evaluation limits

On the 2026 holdout, 76 of 88 positive six-hour issue windows were detected at the selected threshold, with 167 false positive windows. These overlapping windows are not independent flood events. Patna had 8 positive test windows; Muzaffarpur had none, so local Muzaffarpur accuracy could not be measured. Treat the percentages as experimental and follow official CWC, IMD, and local authority updates.

The source archive is a public mirror of CWC FFS records at [diagram-chasing/cwc-flood-forecasts](https://github.com/diagram-chasing/cwc-flood-forecasts). Its documentation requests CWC attribution and states ODbL; confirm terms before redistributing data.

`train_cwc_gauge_nextday.py` remains available for historical research but writes only a separate legacy artifact; it cannot overwrite the rolling model used by the dashboard.
