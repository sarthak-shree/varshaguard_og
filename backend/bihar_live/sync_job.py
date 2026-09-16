"""Scheduled Bihar Live synchronization job.

Fetch FMISC observations outside Vercel's request path, persist them to Neon,
and maintain a repository snapshot for graceful stale-data fallback.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .ingest import fetch_live_river_observations
from .persist import persist_records

SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "live_snapshot.json"


def _write_snapshot(payload: dict) -> None:
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


def main() -> int:
    payload = fetch_live_river_observations()
    if not payload.get("success") or not payload.get("records"):
        raise RuntimeError("FMISC sync did not return usable river observations")
    if not payload.get("live") or payload.get("source_mode") != "fmisc_live":
        raise RuntimeError(
            "FMISC was not reachable; scheduled sync refuses to persist fallback data as live."
        )

    saved = persist_records(payload["records"])
    _write_snapshot(payload)

    print(
        json.dumps(
            {
                "success": True,
                "source": payload["source"],
                "fetched_at": payload["fetched_at"],
                "fetched_count": len(payload["records"]),
                "persisted_count": saved,
                "snapshot": str(SNAPSHOT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
