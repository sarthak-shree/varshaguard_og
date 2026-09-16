# VARSHAGUARD Bihar Live Backend — v0.3.0

This backend is separate from the existing VARSHAGUARD v0.2.0 backend.

## Current scope

Bihar Live currently provides:

- official Bihar FMISC/WRD live-river ingestion
- normalization and deterministic river-level feature processing
- Neon PostgreSQL persistence with duplicate protection
- scheduled GitHub Actions synchronization
- latest/live river API
- historical river API
- station lookup
- freshness and data-health metadata
- model/source roadmap documentation

The Vercel API reads the latest successful FMISC snapshot persisted in Neon rather than scraping FMISC during a user request.

## Current limitation

This is **not yet a complete heavy-rainfall, flood-probability, or inundation-prediction system**. Those capabilities require additional historical datasets, rainfall/forecast integrations, upstream/basin information, terrain/river geometry, flood-extent reference data, model training and backtesting.

## Data truthfulness rules

- Never fabricate unavailable observations.
- Never label cached/fallback data as live.
- Observed, forecast, satellite-derived and model-derived values must remain distinguishable.
- Historical simulation must use only information that would have been available at prediction time.
- Production claims require historical backtesting and documented limitations.

## Planned layers

1. Live hydrology hardening
2. Rainfall intelligence
3. River-level forecasting
4. Bihar flood probability
5. Upstream/basin and Nepal-side information where legitimately accessible
6. DEM/river/floodplain inundation engine
7. Sentinel-1 observed flood mapping and validation
8. Bihar spatial hierarchy and location-aware risk
9. Map/dashboard expansion
10. Alert architecture
11. Reliability/security/observability
12. Backtesting and model registry

See [`docs/BIHAR_LIVE_PRODUCTION_ROADMAP.md`](../../docs/BIHAR_LIVE_PRODUCTION_ROADMAP.md) for the full execution and data requirements.
