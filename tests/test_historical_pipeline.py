from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from backend.bihar_live.historical_pipeline import (
    FEATURE_COLUMNS,
    build_supervised_rows,
    chronological_split,
    connect,
    export_observations,
    ingest_observations,
    train_and_evaluate,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _observation_rows(hours=320):
    start = datetime(2026, 6, 1, 0, tzinfo=IST)
    rows = []
    for index in range(hours):
        stamp = (start + timedelta(hours=index)).isoformat()
        rows.append({
            "station_id": "TEST-GAUGE", "observed_at": stamp, "source": "synthetic-test",
            "variable": "stage_m", "value": 10 + index * 0.01 + np.sin(index / 7) * 0.1,
            "unit": "m", "quality_flag": "good",
        })
        rows.append({
            "station_id": "TEST-GAUGE", "observed_at": stamp, "source": "synthetic-test",
            "variable": "rainfall_mm", "value": max(0, np.sin(index / 5) * 4),
            "unit": "mm/hour", "quality_flag": "good",
        })
    return rows


def test_observation_store_is_idempotent_and_normalizes_timezone(tmp_path):
    db = tmp_path / "history.sqlite3"
    rows = _observation_rows(3)
    first = ingest_observations(rows, db)
    second = ingest_observations(rows, db)
    frame = export_observations(db)

    assert first["stored_rows"] == 6
    assert second["stored_rows"] == 6
    assert second["database_changes"] == 6
    assert frame["observed_at_utc"].str.endswith("+00:00").all()
    with connect(db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_ingest_rejects_invalid_rainfall_and_unknown_quality(tmp_path):
    result = ingest_observations([
        {"station_id": "x", "observed_at": "2026-06-01T00:00:00+05:30", "source": "test",
         "variable": "rainfall_mm", "value": -1, "unit": "mm"},
        {"station_id": "x", "observed_at": "2026-06-01T01:00:00+05:30", "source": "test",
         "variable": "stage_m", "value": 10, "unit": "m", "quality_flag": "magical"},
    ], tmp_path / "history.sqlite3")

    assert result["rejected_input_rows"] == 2
    assert result["stored_rows"] == 0


def test_supervised_rows_are_timestamp_aligned_and_labels_are_future_only():
    observations = pd.DataFrame(_observation_rows(60)).rename(columns={"observed_at": "observed_at"})
    rows = build_supervised_rows(observations)

    assert not rows.empty
    assert all(column in rows.columns for column in FEATURE_COLUMNS)
    first = rows.iloc[0]
    issue = pd.Timestamp(first["issue_time_utc"])
    assert pd.Timestamp(first["issue_time_ist"]).tz_convert("UTC") == issue
    assert np.isfinite(first["target_stage_1h_m"])
    assert first["target_stage_1h_m"] != first["stage_lag_1h_m"]
    assert "target_stage_24h_m" not in rows.columns


def test_supervised_builder_does_not_forward_fill_missing_stage_lags():
    rows = _observation_rows(40)
    # Remove one required stage lag at an interior timestamp.
    rows = [row for row in rows if not (
        row["variable"] == "stage_m" and row["observed_at"].startswith("2026-06-01T10:00:00")
    )]
    built = build_supervised_rows(pd.DataFrame(rows))

    # Rows whose exact 10:00 stage lag is required are not fabricated by filling.
    assert "2026-06-01T05:30:00+00:00" not in set(built["issue_time_utc"])


def test_chronological_split_never_shuffles_timestamps():
    data = pd.DataFrame({"issue_time_utc": pd.date_range("2026-01-01", periods=100, freq="h").astype(str),
                         "value": range(100)})
    train, validation, test = chronological_split(data)

    assert train["value"].max() < validation["value"].min()
    assert validation["value"].max() < test["value"].min()


def test_training_fails_closed_when_labels_are_insufficient(tmp_path):
    result = train_and_evaluate(pd.DataFrame(), tmp_path)

    assert result["status"] == "insufficient_data"
    assert result["operational"] is False
    assert not list(tmp_path.glob("*.joblib"))


def test_training_uses_validation_for_selection_and_keeps_test_reporting_separate(tmp_path):
    observations = pd.DataFrame(_observation_rows(360))
    supervised = build_supervised_rows(observations)
    report = train_and_evaluate(supervised, tmp_path, min_train_rows=120, min_test_rows=20)

    result = report["models"]["target_stage_1h_m"]
    assert result["status"] == "evaluated_research_only"
    assert result["selected_using"] == "validation_mae_only"
    assert result["test_rows"] >= 20
    assert "selected_model_final_test_metrics" in result
    assert report["operational"] is False
    assert (tmp_path / "training_evaluation.json").exists()
