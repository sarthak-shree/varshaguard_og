# Layer 1.3A — Historical River Storage Contract

## Purpose

Define the canonical storage model before connecting a real database.
This layer does **not** connect PostgreSQL and does not pretend that local
process memory is historical storage.

## Canonical record

`RiverObservation` contains:

- `river`
- `station`
- `district`
- `observed_at`
- `water_level_m`
- `warning_level_m`
- `danger_level_m`
- `hfl_m`
- `trend`
- `water_level_1h_before_m`
- `fetched_at`

## Repository operations

`save_observations(observations)` stores a batch and returns the number accepted.

`get_history(...)` retrieves observations with optional station, district and
time filters plus a bounded result limit.

## Database design

The PostgreSQL schema is in `schema.sql`.
The primary historical query path is station + observation time, so the schema
includes an index on `(station, observed_at DESC)`. District/time and global
time indexes are also included for dashboard queries.

A unique partial index on `(station, observed_at)` prevents the same source
observation from being inserted repeatedly when the same snapshot is fetched
more than once. Records without an observation timestamp are not deduplicated
by that constraint; the ingestion layer must resolve source timestamps before
historical storage is enabled.

## Next layer

Layer 1.3B will implement this contract with PostgreSQL and wire it to the
Bihar Live ingestion pipeline.
