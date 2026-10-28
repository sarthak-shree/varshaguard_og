import csv

import pytest

from backend.bihar_live.research.validate_external_events import DEFAULT_LEDGER, validate_ledger


def test_seed_external_event_ledger_has_provenance_and_explicit_match_status():
    rows = validate_ledger(DEFAULT_LEDGER)

    assert len(rows) == 3
    assert all(row["source_url"].startswith("https://") for row in rows)
    assert all(row["matching_status"] == "not_spatiotemporally_matched" for row in rows)
    assert all(row["station_level_match_ready"] == "false" for row in rows)
    assert any("NRSC" in row["source_org"] and "2025-10-06" in row["source_observation_time_ist"] for row in rows)


def test_ledger_rejects_timestamp_without_timezone(tmp_path):
    with DEFAULT_LEDGER.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        rows = list(reader)
    rows[0]["source_observation_time_ist"] = "2024-09-27T06:00:00"

    path = tmp_path / "events.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="timezone offset"):
        validate_ledger(path)


def test_ledger_rejects_duplicate_event_ids(tmp_path):
    with DEFAULT_LEDGER.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames
        rows = list(reader)
    rows.append(dict(rows[0]))

    path = tmp_path / "events.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="Duplicate event_id"):
        validate_ledger(path)
