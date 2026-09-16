-- VARSHAGUARD Bihar Live v0.3.0
-- Core live/historical river observations plus production-oriented metadata.

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
    source TEXT NOT NULL DEFAULT 'Bihar FMISC/WRD',
    source_url TEXT,
    quality_status TEXT NOT NULL DEFAULT 'unknown',
    CONSTRAINT river_observations_water_level_nonnegative CHECK (water_level_m >= 0)
);

CREATE INDEX IF NOT EXISTS idx_river_observations_station_observed_at
    ON river_observations (station, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_river_observations_district_observed_at
    ON river_observations (district, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_river_observations_observed_at
    ON river_observations (observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_river_observations_source_observed_at
    ON river_observations (source, observed_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_river_observations_river_station_observed_at
    ON river_observations (river, station, observed_at)
    WHERE observed_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS source_health (
    id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL,
    last_success_at TIMESTAMPTZ,
    last_observation_at TIMESTAMPTZ,
    latency_ms DOUBLE PRECISION,
    record_count INTEGER NOT NULL DEFAULT 0,
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    quality_status TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_source_health_source_checked_at
    ON source_health (source_name, checked_at DESC);

CREATE TABLE IF NOT EXISTS model_versions (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    target TEXT,
    training_start DATE,
    training_end DATE,
    validation_method TEXT,
    metrics JSONB,
    feature_names JSONB,
    assumptions JSONB,
    artifact_location TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_name, version)
);
