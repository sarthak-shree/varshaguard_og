-- VARSHAGUARD Bihar Live v0.3.0
-- Layer 1.3B: PostgreSQL historical river observation schema.

CREATE TABLE IF NOT EXISTS river_observations (
    id BIGSERIAL PRIMARY KEY,
    river TEXT NOT NULL,
    station TEXT NOT NULL,
    district TEXT NOT NULL,
    observed_at TIMESTAMPTZ,
    water_level_m DOUBLE PRECISION NOT NULL,
    warning_level_m DOUBLE PRECISION,
    danger_level_m DOUBLE PRECISION,
    hfl_m DOUBLE PRECISION,
    trend TEXT,
    water_level_1h_before_m DOUBLE PRECISION,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT river_observations_water_level_nonnegative
        CHECK (water_level_m >= 0)
);

CREATE INDEX IF NOT EXISTS idx_river_observations_station_observed_at
    ON river_observations (station, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_river_observations_district_observed_at
    ON river_observations (district, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_river_observations_observed_at
    ON river_observations (observed_at DESC);

-- Prevent duplicate source snapshots for the same river/station/time.
-- NULL timestamps are intentionally excluded because a missing source timestamp
-- must not collapse otherwise distinct records.
CREATE UNIQUE INDEX IF NOT EXISTS uq_river_observations_river_station_observed_at
    ON river_observations (river, station, observed_at)
    WHERE observed_at IS NOT NULL;
