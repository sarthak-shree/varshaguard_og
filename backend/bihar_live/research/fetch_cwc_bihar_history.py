"""Download selected Bihar CWC gauge history for the offline research trainer.

The source Parquet files are a public mirror of CWC Flood Forecast System
observations. This script preserves published station thresholds and raw daily
summaries; the trainer applies its own quality filters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / "data" / "bihar_live" / "research" / "cwc_bihar_gauge_history.csv"
STATIONS_URL = "https://diagram-chasing.github.io/cwc-flood-forecasts/stations.parquet"
DAILY_URL = "https://diagram-chasing.github.io/cwc-flood-forecasts/daily.parquet"
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
                d.station_code, d.datatype_code, d.variable, d.unit, d.date_ist,
                d.min, d.mean, d.max, d.sum, d.n_obs,
                s.name, s.lat, s.lon, s.warning_level, s.danger_level,
                s.highest_flow_level
            FROM read_parquet('{DAILY_URL}') AS d
            JOIN read_parquet('{STATIONS_URL}') AS s USING (station_code)
            WHERE d.station_code IN ({station_literals})
              AND d.datatype_code IN ('HHS', 'MPS')
            ORDER BY d.station_code, d.datatype_code, d.date_ist
        ) TO '{output_sql}' (HEADER, DELIMITER ',')
    """
    connection.execute(query)
    metadata = {
        "dataset": "Selected Bihar CWC gauge daily stage and rainfall history",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "output_csv": str(output),
        "output_bytes": output.stat().st_size,
        "output_sha256": sha256_file(output),
        "row_count": connection.execute(
            "SELECT count(*) FROM read_csv_auto(?)", [str(output)]
        ).fetchone()[0],
        "source_upstream": "Central Water Commission Flood Forecast System",
        "mirror_repository": "diagram-chasing/cwc-flood-forecasts",
        "source_urls": [DAILY_URL, STATIONS_URL, "https://ffs.india-water.gov.in/"],
        "station_codes": STATION_CODES,
        "parameters": {
            "HHS": "water level (daily min/mean/max)",
            "MPS": "rainfall (daily sum, millimetres)",
        },
        "license_note": "The mirror states Open Database License and requests CWC attribution; confirm terms before redistribution.",
        "note": "Historical source rows are not pre-cleaned. Use train_cwc_gauge_nextday.py to apply the documented quality screen.",
    }
    output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))
    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


