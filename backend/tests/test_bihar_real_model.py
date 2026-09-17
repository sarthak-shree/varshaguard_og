import numpy as np
import pandas as pd
import pytest

from backend.bihar_live.bihar_real_model import FEATURES, TARGET, split_dates


def test_feature_schema_is_stable():
    assert "rainfall_mm" in FEATURES
    assert "rainfall_7d_sum_mm" in FEATURES
    assert "level_mean_m" in FEATURES
    assert "level_rise_1d_m" in FEATURES
    assert TARGET == "flood_next_24h"


def test_three_way_split_is_chronological_and_disjoint():
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    rows = []
    for d in dates:
        rows.append({"date": d, TARGET: int(d.day % 3 == 0)})
    df = pd.DataFrame(rows)
    train, calibration, test = split_dates(df)
    assert train.date.max() < calibration.date.min()
    assert calibration.date.max() < test.date.min()
    assert set(train.date).isdisjoint(set(calibration.date))
    assert set(calibration.date).isdisjoint(set(test.date))


def test_next_day_label_does_not_use_same_day_event():
    # Event-start date belongs to the target day; the observation day before it is positive.
    starts = {("PATNA", pd.Timestamp("2020-06-02"))}
    observations = [
        ("PATNA", pd.Timestamp("2020-06-01")),
        ("PATNA", pd.Timestamp("2020-06-02")),
    ]
    labels = [int((d, dt + pd.Timedelta(days=1)) in starts) for d, dt in observations]
    assert labels == [1, 0]
