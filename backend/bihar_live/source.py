"""Official Bihar FMISC/WRD live river-data source configuration."""

SOURCE_URL = "https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx"

EXPECTED_FIELDS = (
    "river",
    "station",
    "district",
    "water_level_m",
    "water_level_1h_before_m",
    "warning_level_m",
    "danger_level_m",
    "hfl_m",
    "trend",
    "status",
    "observed_at",
)
