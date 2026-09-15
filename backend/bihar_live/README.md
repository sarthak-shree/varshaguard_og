# VARSHAGUARD Bihar Live Backend — Layer 1.1

This backend is separate from the existing VARSHAGUARD v0.2.0 backend.

## Current scope

Layer 1.1 only:

- Fetch live river observations from Bihar FMISC/WRD.
- Normalize the source table into stable JSON records.
- Expose the data through a dedicated Flask API.
- Keep a short in-process cache to avoid repeatedly hitting the source.

## Run locally

From the repository root:

```bash
python -m backend.bihar_live.app
```

The API runs on:

```text
http://127.0.0.1:5002
```

## Endpoints

```text
GET /api/bihar/health
GET /api/bihar/live-rivers
GET /api/bihar/live-rivers?district=Patna
GET /api/bihar/live-rivers?refresh=true
```

## Data source

Bihar Flood Management Information System / Water Resources Department real-time river observations:

https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx

## Important

The source layout can change. Layer 1.1 therefore validates that required fields can be identified before returning records.

The current cache is process-local and intended for the prototype. Production deployment should use persistent storage or a scheduled ingestion service for reliable historical tracking and multi-instance consistency.
