"""Scheduled Bihar Live synchronization job."""

from __future__ import annotations

import json
from pathlib import Path

from .ingest import fetch_live_river_observations
from .persist import _to_observation
from .processing import process_river_records

SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "live_snapshot.json"


def main() -> int:
    from .postgres import PostgreSQLRiverObservationRepository

    payload = fetch_live_river_observations()
    if not payload.get("success") or not payload.get("records"):
        raise RuntimeError("FMISC sync did not return usable river observations")
    if not payload.get("live") or payload.get("source_mode") != "fmisc_live":
        raise RuntimeError("FMISC was not reachable; refusing to persist fallback data as live")

    processed = process_river_records(payload["records"])
    observations = [_to_observation(record) for record in processed]
    repository = PostgreSQLRiverObservationRepository.from_env()
    repository.ensure_schema()
    persisted_count = repository.save_observations(observations)

    snapshot = {
        "source": payload["source"],
        "source_url": payload["source_url"],
        "snapshot_at": payload["fetched_at"],
        "records": payload["records"],
    }
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "success": True,
        "fetched_count": len(payload["records"]),
        "processed_count": len(processed),
        "persisted_count": persisted_count,
        "snapshot_at": payload["fetched_at"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
