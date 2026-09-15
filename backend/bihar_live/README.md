# VARSHAGUARD Bihar Live Backend — Layer 1.3A

This backend is separate from the existing VARSHAGUARD v0.2.0 backend.

## Current scope

Layer 1.3A defines the historical river-observation storage contract:

- Canonical `RiverObservation` data model.
- Database-independent repository interface.
- PostgreSQL table schema in `schema.sql`.
- Station/time, district/time and observation-time indexes.
- Duplicate protection for timestamped station observations.

Layer 1.3A does **not** connect a database or claim historical persistence yet.

## Files

- `storage.py` — canonical model and repository contract.
- `schema.sql` — PostgreSQL schema to be used in Layer 1.3B.
- `storage_contract.md` — design decisions and query contract.

## Next step

Layer 1.3B will implement the repository with PostgreSQL and connect it to
the ingestion pipeline.
