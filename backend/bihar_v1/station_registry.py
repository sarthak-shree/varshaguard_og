"""Source-supported station registry for the first Bihar v1 geography.

Rainfall and river stations are kept separate because the supplied historical
rainfall data are mostly daily and do not provide hourly Patna/Muzaffarpur
coverage for the 2021-2025 telemetry period. Cross-source station pairs are
explicit rather than inferred from coincident timestamps.
"""
PATNA_RAINFALL_DAILY_STATIONS = {"Gandhighat", "Koelwar"}
PATNA_RAINFALL_HOURLY_STATIONS = set()
PATNA_RIVER_STATIONS = {"Kharuara_1"}

MUZAFFARPUR_RAINFALL_DAILY_STATIONS = {"Sikandarpur (Muzzafarpur)"}
MUZAFFARPUR_RAINFALL_HOURLY_STATIONS = set()
MUZAFFARPUR_RIVER_STATIONS = set()
MUZAFFARPUR_RAINFALL_RIVER_STATION_PAIRS = set()

PATNA_RAINFALL_RIVER_STATION_PAIRS = set()


def stations_for_district(district: str) -> dict[str, set[str]]:
    key = district.strip().lower()
    if key == "patna":
        return {
            "rainfall_daily": PATNA_RAINFALL_DAILY_STATIONS,
            "rainfall_hourly": PATNA_RAINFALL_HOURLY_STATIONS,
            "river": PATNA_RIVER_STATIONS,
            "rainfall_river_pairs": PATNA_RAINFALL_RIVER_STATION_PAIRS,
        }
    if key == "muzaffarpur":
        return {
            "rainfall_daily": MUZAFFARPUR_RAINFALL_DAILY_STATIONS,
            "rainfall_hourly": MUZAFFARPUR_RAINFALL_HOURLY_STATIONS,
            "river": MUZAFFARPUR_RIVER_STATIONS,
            "rainfall_river_pairs": MUZAFFARPUR_RAINFALL_RIVER_STATION_PAIRS,
        }
    raise ValueError(f"Unsupported district: {district}")
