"""Small Layer 1.3A contract tests; no database is required."""

from datetime import datetime, timezone

from storage import RiverObservation, UnconfiguredRepository


def test_canonical_observation():
    observation = RiverObservation(
        river="Ganga",
        station="Digha Ghat",
        district="Patna",
        observed_at=datetime.now(timezone.utc),
        water_level_m=48.2,
        warning_level_m=48.5,
        danger_level_m=49.0,
        hfl_m=50.0,
        trend="rising",
        water_level_1h_before_m=47.9,
    )
    assert observation.station == "Digha Ghat"
    assert observation.water_level_m == 48.2


def test_unconfigured_repository_fails_explicitly():
    repository = UnconfiguredRepository()
    try:
        repository.save_observations([])
    except RuntimeError as exc:
        assert "storage is not configured" in str(exc).lower()
    else:
        raise AssertionError("Unconfigured repository must not pretend to persist data")


if __name__ == "__main__":
    test_canonical_observation()
    test_unconfigured_repository_fails_explicitly()
    print("Layer 1.3A contract tests: PASS")
