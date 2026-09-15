# VARSHAGUARD Bihar Live Backend — Layer 1.3B

This backend is separate from the existing VARSHAGUARD v0.2.0 backend.

## Current scope

Layer 1.3B implements PostgreSQL persistence for historical river observations:

- Canonical `RiverObservation` records from `storage.py`.
- PostgreSQL repository in `postgres.py`.
- Schema creation through `ensure_schema()`.
- Batch inserts with duplicate protection.
- Historical queries by station, district and observation time.
- Configured through the `DATABASE_URL` environment variable.
- PostgreSQL driver supplied by `psycopg[binary]`.

The repository uses lazy database connections: importing the module does not
attempt to contact PostgreSQL. A real database connection requires a valid
`DATABASE_URL`.

## Files

- `storage.py` — canonical model and repository contract.
- `schema.sql` — PostgreSQL table and indexes.
- `postgres.py` — Layer 1.3B PostgreSQL repository.
- `test_postgres.py` — dependency-light repository configuration tests.
- `storage_contract.md` — persistence design and query contract.

## Example configuration

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
```

The repository can then be created with:

```python
from backend.bihar_live.postgres import get_configured_repository

repository = get_configured_repository()
repository.ensure_schema()
```

## Scope boundary

Layer 1.3B implements the database repository only. It does not yet wire the
live FMISC/WRD ingestion job into PostgreSQL. That integration belongs to the
next persistence layer so ingestion and storage remain independently testable.
