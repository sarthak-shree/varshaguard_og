"""Fetch hourly CWC gauge and rainfall observations for the Bihar 24-hour model."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "data" / "bihar_live" / "research" / "cwc_bihar_gauge_hourly.csv"
STATIONS_URL = "https://diagram-chasing.github.io/cwc-flood-forecasts/stations.parquet"
HOURLY_URL = "https://diagram-chasing.github.io/cwc-flood-forecasts/hourly.parquet"
STATION_CODES = [
    "002-MGD5PTN", "003-MGD5PTN", "004-MGD4PTN", "005-MGD5PTN",
    "009-MGD5PTN", "011-MGD5PTN", "016-MGD4PTN", "017-MGD4PTN",
    "021-MGD5PTN", "026-MGD5PTN", "027-MGD5PTN", "032-MGD4PTN",
    "033-MGD4PTN",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import duckdb
    except ImportError as error:
        parser.error("Install duckdb (pip install duckdb) to fetch the public Parquet source.")

    connection = duckdb.connect()
    connection.execute("INSTALL httpfs")
    connection.execute("LOAD httpfs")
    station_literals = ",".join("'" + code.replace("'", "''") + "'" for code in STATION_CODES)
    output_sql = str(output).replace("'", "''")
    if output.exists():
        output.unlink()
    query = f"""
        COPY (
            SELECT
                h.station_code, h.datatype_code, h.datetime AS timestamp_ist,
                h.value, h.source_type, s.name, s.lat, s.lon,
                s.warning_level, s.danger_level, s.highest_flow_level
            FROM read_parquet('{HOURLY_URL}') AS h
            JOIN read_parquet('{STATIONS_URL}') AS s USING (station_code)
            WHERE h.station_code IN ({station_literals})
              AND h.datatype_code IN ('HHS', 'MPS')
              AND h.source_type = 'gauge'
            ORDER BY h.station_code, h.datatype_code, h.datetime
        ) TO '{output_sql}' (HEADER, DELIMITER ',')
    """
    connection.execute(query)
    row_count = connection.execute("SELECT count(*) FROM read_csv_auto(?)", [str(output)]).fetchone()[0]
    metadata = {
        "dataset": "Hourly Bihar CWC gauge-stage and rainfall observations",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output_csv": str(output),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "row_count": row_count,
        "source_upstream": "Central Water Commission Flood Forecast System",
        "mirror_repository": "diagram-chasing/cwc-flood-forecasts",
        "source_urls": [HOURLY_URL, STATIONS_URL, "https://ffs.india-water.gov.in/"],
        "station_codes": STATION_CODES,
        "parameters": {"HHS": "water level observations", "MPS": "rainfall observations (millimetres)"},
        "license_note": "The mirror states Open Database License and requests CWC attribution; confirm terms before redistribution.",
        "note": "This is a research input archive. The model uses only observations at or before each issue time; future observations define the label only.",
    }
    output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
