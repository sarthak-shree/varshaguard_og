# VARSHAGUARD

VARSHAGUARD is a beginner-friendly Smart India Hackathon prototype for:

AI/ML-Based Integrated Heavy Rainfall Early Warning & Inundation Prediction System.

This is a prototype only. It is not an operational government-grade flood warning system.

## What It Does

The demo flow is:

Historical/prototype rainfall data -> data processing -> Random Forest model -> flood probability -> risk level -> Flask API -> web dashboard.

The main question is:

Based on recent rainfall conditions, is flooding likely to occur soon in this study region?

## Tech Stack

- Python
- Flask
- Flask-CORS
- Pandas
- scikit-learn
- joblib
- HTML
- CSS
- JavaScript
- Leaflet.js
- Chart.js

## Project Structure

```text
backend/
  app.py
  model.py
  prediction.py
  risk.py
  train_model.py
data/
  processed/
    flood_warning_ml_ready_v2.csv
frontend/
  index.html
  script.js
  style.css
models/
requirements.txt
README.md
```

## Important Data Note

This workspace did not contain the original supplied SIH datasets when this beginner version was created.

So this repo includes a tiny clearly labeled prototype CSV so the app can run locally. Replace `data/processed/flood_warning_ml_ready_v2.csv` with your real processed dataset when you have it.

## Install

```bash
pip install -r requirements.txt
```

## Train The Demo Model

```bash
python backend/train_model.py
```

This creates:

```text
models/flood_warning_random_forest_v2.pkl
```

## Run Backend

```bash
python backend/app.py
```

Backend URL:

```text
http://127.0.0.1:5001
```

## Run Frontend

Open a second terminal:

```bash
python -m http.server 5500 --directory frontend
```

Frontend URL:

```text
http://127.0.0.1:5500
```

## API Endpoints

- `GET /api/health`
- `GET /api/regions`
- `GET /api/flood-risk?region=Assam`
- `GET /api/rainfall?region=Assam`
- `GET /api/history?region=Assam`
- `GET /api/stations?region=Assam`

Supported regions:

- Assam
- Uttarakhand

## Example API Response

```json
{
  "success": true,
  "region": "Assam",
  "prediction_horizon_hours": 24,
  "flood_probability": 0.84,
  "risk": "HIGH",
  "warning": "Flood likely soon. Take precautionary measures and follow local authority guidance."
}
```

## Prototype Limitations

- Uses historical/prototype data
- Only two study regions
- Uses a baseline Random Forest model
- Does not use live radar
- Does not use satellite ingestion
- Does not use numerical weather prediction
- Does not perform hydraulic simulation
- Does not calculate DEM-based inundation depth
- Does not send operational alerts

## Future Production Upgrade Path

Future versions could use satellite data, radar, ground gauges, weather forecasts, data quality control, spatio-temporal fusion, advanced AI/ML, rainfall nowcasting, terrain-aware inundation modelling, PostGIS, GIS dashboards, and alert/evacuation support.
