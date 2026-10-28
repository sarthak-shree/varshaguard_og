"""Download and inventory public source datasets without silently training on unknown schemas.

Usage:
  python scripts/fetch_public_sources.py --source bihar_hourly_rainfall
  python scripts/fetch_public_sources.py --all

The downloaded files are raw snapshots, not yet normalized training data. Inspect headers,
station identifiers, units and timestamp semantics before importing with --import-csv.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "public_sources"
USER_AGENT = "VarshaGuard/0.1 (public flood research; source provenance enabled)"

SOURCES = {
    "bihar_hourly_rainfall": {
        "agency": "Bihar Water Department via National Water Data Portal / NWIC",
        "period": "2021-2025",
        "variable": "hourly rainfall observations",
        "url": "https://nwdp.nwic.gov.in/dataset/b6ee5954-2c41-482d-9ff5-0db02708e259/resource/3caa008a-af7a-4d2f-aad9-1a4e83e736c7/download/rainfall_tel_hr_bihar_br_2021_2025.csv",
        "landing_page": "https://www.nwdp.nwic.gov.in/dataset/rainfall-bihar-telemetry-hourlydata",
        "unit_expected": "mm (verify CSV schema)",
    },
    "cwc_bihar_hourly_rainfall": {
        "agency": "Central Water Commission via National Water Data Portal / NWIC",
        "period": "2021-2025",
        "variable": "hourly rainfall observations",
        "url": "https://nwdp.nwic.gov.in/dataset/792f0818-bedf-42ab-a119-dc7002ceb312/resource/057109a7-abb1-4c4b-97db-6bd17c537588/download/rainfall_tel_hr_cwc_br_2021_2025.csv",
        "landing_page": "https://nwdp.nwic.gov.in/en/dataset/rainfall-cwc-telemetry-hourly",
        "unit_expected": "mm (verify CSV schema)",
    },
    "bihar_daily_water_level": {
        "agency": "Bihar Water Department via National Water Data Portal / NWIC",
        "period": "2020-2025",
        "variable": "daily manually observed surface water level",
        "url": "https://nwdp.nwic.gov.in/dataset/02593231-24d9-450b-b9a9-d17940bc5fe7/resource/e7c7afd1-b829-4cba-a8ff-b84b94299631/download/bihar_sw_daily_water_level_manual.csv",
        "landing_page": "https://nwdp.nwic.gov.in/en/dataset/surface-water-level-manual-daily-bihar",
        "unit_expected": "m (verify CSV schema)",
    },
}

RESEARCH_SOURCES = [
    {"kind": "official_event_report", "title": "MHA/NDMI Bihar flood situation report, 30 Sep 2024",
     "url": "https://www.ndmindia.mha.gov.in/ndmi/viewUploadedDocument?uid=NEW2208",
     "use": "Candidate event context only; spatial/time matching and label extraction still required."},
    {"kind": "government_research_portal", "title": "FMISC, Water Resources Department, Government of Bihar",
     "url": "https://www.fmiscwrdbihar.gov.in/",
     "use": "Discover CWC gauge, RTDAS, River Watch and remote-sensing products; terms and access must be checked."},
    {"kind": "private_research_site", "title": "Bihar River Forecast (BIRA / RAP)",
     "url": "https://bihar.rap.ucar.edu/flow",
     "use": "Experimental observed/forecast stage comparison; not official, validate station/time data before use."},
    {"kind": "github_research", "title": "India Flood Inventory (HydroSense Lab, IIT Delhi)",
     "url": "https://github.com/hydrosenselab/India-Flood-Inventory",
     "use": "Independent geospatial event inventory; inspect license, spatial/time resolution and Bihar coverage."},
    {"kind": "github_research", "title": "India Water Data Resources API client",
     "url": "https://github.com/DrJagadeeshG/india-water-data",
     "use": "Community client for WRIS; inspect implementation and API terms before use."},
    {"kind": "github_research", "title": "Bangladesh Flood Forecasting Dataset",
     "url": "https://github.com/Srabon-bot/Bangladesh-flood-data-set",
     "use": "Methodology reference only; Bangladesh stations are not Bihar training labels."},
    {"kind": "reddit_context", "title": "Hydrology discussion: weather API vs local rain gauge",
     "url": "https://www.reddit.com/r/Hydrology/comments/1w0p0t3/weather_api_or_tipping_bucket_for_flood_prediction/",
     "use": "Qualitative advice on source mismatch and train/serve skew; never use as measurement labels."},
    {"kind": "reddit_context", "title": "Bihar flood relief-map discussion",
     "url": "https://www.reddit.com/r/bihar/comments/1wih7oe/i_built_an_interactive_3d_relief_map_of_bihar_for/",
     "use": "Discovery lead only; verify claims and use cited primary sources for event labels."},
]


def download(url: str, target: Path) -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        digest = hashlib.sha256()
        count = 0
        with target.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
    return count, digest.hexdigest()


def inspect_csv(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader, [])
            samples = [next(reader, []) for _ in range(3)]
        return {"columns": header, "sample_rows": samples}
    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        return {"inspection_error": str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=sorted(SOURCES))
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    selected = list(SOURCES) if args.all else ([args.source] if args.source else [])
    if not selected:
        parser.error("choose --source ID or --all")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except ValueError:
            manifest = {}
    else:
        manifest = {}
    manifest.setdefault("schema_version", 1)
    manifest.setdefault("research_sources", RESEARCH_SOURCES)
    manifest.setdefault("downloads", {})
    for source_id in selected:
        metadata = dict(SOURCES[source_id])
        target = OUT / f"{source_id}.csv"
        try:
            size, digest = download(metadata["url"], target)
            metadata.update({
                "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                "local_file": target.name, "bytes": size, "sha256": digest,
                "inspection": inspect_csv(target),
                "normalized_for_training": False,
                "note": "Raw source snapshot only. Confirm schema, units, station IDs, timestamp timezone and license before normalization.",
            })
            manifest["downloads"][source_id] = metadata
            print(json.dumps({"source": source_id, "status": "downloaded", "bytes": size,
                              "sha256": digest, "inspection": metadata["inspection"]}, indent=2))
        except Exception as exc:
            manifest["downloads"][source_id] = {
                **metadata, "status": "download_failed", "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
                "error": f"{type(exc).__name__}: {exc}",
                "note": "Retry from a machine with network access; no data was fabricated.",
            }
            print(json.dumps({"source": source_id, "status": "download_failed", "error": str(exc)}, indent=2))
        time.sleep(1)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Source manifest: {manifest_path}")


if __name__ == "__main__":
    main()
