"""Verified local station registry for the first Bihar v1 training geography.

This file is deliberately explicit: station influence must be reviewed before
training rather than inferred from station names alone.
"""
PATNA_RAINFALL_STATIONS = {
    "Arrah Chhapra Bridge",
}
PATNA_RIVER_STATIONS = {
    "Kharuara_1",
    "Dighaghat",
    "Hathidah",
}
MUZAFFARPUR_RAINFALL_STATIONS = set()
MUZAFFARPUR_RIVER_STATIONS = {
    "Benibad",
    "Sikandarpur",
    "Rewaghat",
    "Runisaidpur",
    "Sakra",
    "Kanti",
}


def stations_for_district(district: str) -> dict[str, set[str]]:
    key = district.strip().lower()
    if key == "patna":
        return {"rainfall": PATNA_RAINFALL_STATIONS, "river": PATNA_RIVER_STATIONS}
    if key == "muzaffarpur":
        return {"rainfall": MUZAFFARPUR_RAINFALL_STATIONS, "river": MUZAFFARPUR_RIVER_STATIONS}
    raise ValueError(f"Unsupported district: {district}")
