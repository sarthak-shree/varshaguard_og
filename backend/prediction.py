import os

import pandas as pd


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")

REGIONS = ["Assam", "Uttarakhand"]


def load_data():
    """Load the processed rainfall/flood dataset and normalize its schema."""
    if not os.path.exists(DATA_PATH):
        return None, "Processed data file is missing."

    try:
        data = pd.read_csv(DATA_PATH)
    except Exception as error:
        return None, "Processed data could not be read: " + str(error)

    required_source_columns = [
        "state",
        "Station",
        "Latitude",
        "Longitude",
        "hour",
    ]
    missing_source = [column for column in required_source_columns if column not in data.columns]

    # The older prototype CSV already uses the normalized names. Keep it compatible.
    if missing_source:
        normalized_columns = ["region", "station", "latitude", "longitude", "timestamp"]
        missing_normalized = [column for column in normalized_columns if column not in data.columns]
        if missing_normalized:
            return None, "Data schema is missing columns: " + ", ".join(missing_source)
    else:
        data["region"] = data["state"].astype(str).str.strip()
        data["station"] = data["Station"].astype(str).str.strip()
        data["latitude"] = pd.to_numeric(data["Latitude"], errors="coerce")
        data["longitude"] = pd.to_numeric(data["Longitude"], errors="coerce")
        data["timestamp"] = pd.to_datetime(data["hour"], errors="coerce")

    return data, None


def clean_data(data):
    """Clean the in-memory API copy without changing the source CSV."""
    data = data.copy()

    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data = data.dropna(subset=["timestamp", "region", "station", "latitude", "longitude"])

    rainfall_columns = [
        column
        for column in data.columns
        if column.startswith("rainfall_") and column != "rainfall_mm"
    ]
    for column in rainfall_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
        data[column] = data[column].fillna(0)
        data = data[data[column] >= 0]
        data = data[data[column] <= 1000]

    duplicate_columns = [
        "region",
        "station",
        "latitude",
        "longitude",
        "timestamp",
    ]
    data = data.drop_duplicates(subset=duplicate_columns, keep="last")

    return data.sort_values("timestamp")


def filter_by_region(data, region):
    """Return rows for one supported region."""
    if region not in REGIONS:
        return None, "Unsupported region"

    region_data = data[
        data["region"].astype(str).str.strip().str.lower() == region.lower()
    ].copy()

    if region_data.empty:
        return None, "No data available for " + region

    return region_data.sort_values("timestamp"), None


def filter_by_station(region_data, station):
    """Return rows for one station inside the selected region."""
    station_data = region_data[
        region_data["station"].astype(str).str.strip().str.lower()
        == station.strip().lower()
    ].copy()

    if station_data.empty:
        return None, "No data available for station: " + station

    return station_data.sort_values("timestamp"), None


def get_latest_record(region, station=None):
    """Get the latest row for a region and optional station."""
    data, error = load_data()
    if error:
        return None, error

    data = clean_data(data)
    region_data, error = filter_by_region(data, region)
    if error:
        return None, error

    if station:
        region_data, error = filter_by_station(region_data, station)
        if error:
            return None, error

    return region_data.iloc[-1].to_dict(), None


def prepare_features(record, features):
    """Build the exact columns the ML model expects."""
    missing = []
    values = {}

    for feature in features:
        if feature not in record:
            missing.append(feature)
        else:
            values[feature] = record[feature]

    if missing:
        return None, "Missing model feature: " + ", ".join(missing)

    return pd.DataFrame([values], columns=features), None


def predict_probability(model_info, region, station=None):
    """Run model.predict_proba() for a region and optional station."""
    if not model_info["ok"]:
        return None, None, model_info["error"]

    record, error = get_latest_record(region, station)
    if error:
        return None, None, error

    model_input, error = prepare_features(record, model_info["features"])
    if error:
        return None, None, error

    try:
        probabilities = model_info["model"].predict_proba(model_input)[0]
        flood_probability = float(probabilities[1])
    except Exception as error:
        return None, None, "Prediction failed: " + str(error)

    return flood_probability, record, None


def get_rainfall_series(region, station=None):
    """Return the latest rainfall values for a region or selected station."""
    data, error = load_data()
    if error:
        return None, error

    data = clean_data(data)
    region_data, error = filter_by_region(data, region)
    if error:
        return None, error

    if station:
        region_data, error = filter_by_station(region_data, station)
        if error:
            return None, error

    rows = region_data.tail(24)
    result = []
    for _, row in rows.iterrows():
        result.append({
            "timestamp": str(row.get("timestamp", "")),
            "station": str(row.get("station", "")),
            "rainfall_1h": float(row.get("rainfall_1h", 0)),
            "rainfall_24h": float(row.get("rainfall_24h", 0)),
        })

    return result, None


def get_history(region, station=None):
    """Return recent prototype prediction records."""
    data, error = load_data()
    if error:
        return None, error

    data = clean_data(data)
    region_data, error = filter_by_region(data, region)
    if error:
        return None, error

    if station:
        region_data, error = filter_by_station(region_data, station)
        if error:
            return None, error

    columns = [
        "timestamp",
        "region",
        "station",
        "rainfall_24h",
        "rainfall_72h",
        "flood_soon",
    ]
    available_columns = [column for column in columns if column in region_data.columns]

    rows = region_data.tail(12)[available_columns].copy()
    if "timestamp" in rows.columns:
        rows["timestamp"] = rows["timestamp"].astype(str)

    return rows.to_dict(orient="records"), None


def get_stations(region):
    """Return unique station points for the selected region."""
    data, error = load_data()
    if error:
        return None, error

    data = clean_data(data)
    region_data, error = filter_by_region(data, region)
    if error:
        return None, error

    needed = ["station", "latitude", "longitude"]
    stations = (
        region_data[needed]
        .dropna()
        .drop_duplicates(subset=needed)
        .sort_values("station")
    )

    return stations.to_dict(orient="records"), None
