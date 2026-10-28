"""Report which external flood events are eligible for independent model scoring.

This is an eligibility audit, not an event-matching algorithm. It deliberately refuses
to infer event onset, spatial overlap, or negative labels from source snapshots alone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.bihar_live.research.validate_external_events import DEFAULT_LEDGER, validate_ledger


def event_scoring_eligibility(rows: list[dict[str, str]]) -> dict:
    """Count records meeting the frozen minimum requirements for event-level scoring."""
    eligible_ids: list[str] = []
    excluded: dict[str, list[str]] = {}
    for row in rows:
        reasons: list[str] = []
        if row["independent_of_model_gauge_inputs"].strip().lower() != "true":
            reasons.append("not_independent_of_model_gauge_inputs")
        if row["ground_verified"].strip().lower() != "true":
            reasons.append("ground_verification_missing")
        if row["matching_status"] != "matched":
            reasons.append("spatiotemporal_match_not_reviewed")
        if row["station_level_match_ready"].strip().lower() != "true":
            reasons.append("station_level_match_not_ready")
        if not row["event_start_time_ist"].strip():
            reasons.append("event_onset_missing")
        if reasons:
            excluded[row["event_id"]] = reasons
        else:
            eligible_ids.append(row["event_id"])

    return {
        "records_reviewed": len(rows),
        "eligible_event_count": len(eligible_ids),
        "eligible_event_ids": eligible_ids,
        "excluded_event_count": len(excluded),
        "excluded": excluded,
        "interpretation": (
            "Eligibility audit only. No model score is computed. Event-level scoring also "
            "requires prediction rows for the held-out period and a documented matching window."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    rows = validate_ledger(args.ledger.expanduser().resolve())
    print(json.dumps(event_scoring_eligibility(rows), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
