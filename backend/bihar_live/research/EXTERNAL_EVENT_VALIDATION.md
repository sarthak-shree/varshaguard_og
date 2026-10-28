# Independent flood-event validation protocol

## Purpose

The rolling model predicts a **CWC gauge warning-level crossing within the next 24 hours**. This ledger is a separate evidence stream for checking whether gauge alerts align with independently documented flood impacts. It does not redefine the model target and does not turn a gauge threshold crossing into a verified flood event.

The seed ledger is:

`data/bihar_live/research/independent_flood_events.csv`

Validate its schema and provenance fields from the repository root:

```bash
python backend/bihar_live/research/validate_external_events.py
pytest -q backend/bihar_live/tests/test_external_event_ledger.py
```

## Seed sources and what they prove

1. **NRSC/ISRO satellite map, 27 September 2024.** The document identifies Sentinel-1A SAR observations at 06:00 IST on 27 September and maps inundation/standing water in parts of Bihar. It explicitly says the map is preliminary, standing water can include rainfall accumulation, and no ground verification was performed. The acquisition time is an observation timestamp, **not** the flood's onset. Source: [NRSC flood inundation map (Map ID 2024/FL/BR/48/27092024)](https://ndem.nrsc.gov.in/documents/Disaster_Document/2024/BR/brflood50dsc27092024_0600hrs/brflood50dsc27092024_0600hrs_map.pdf).

2. **Bihar Disaster Management Department situation report, as of 2 August 2025, 18:00 IST.** The published snapshot reports five affected districts and 14 affected gram panchayats. This is a government impact report, but its snapshot time is not the event onset and it does not, by itself, locate inundation at any modelled gauge. Source: [Flood/Heavy Rainfall Report](https://betastate.bihar.gov.in/file_2/FileUpload/2025/Nov/17-Nov-2025/12/DyPage/f1509d65-d1d1-41b8-abf8-7f77dd098fdd.pdf). The PDF URL's upload path differs from the report's stated as-of date, so verify the document and provenance before using it in a scored benchmark.

The ledger preserves these limitations in each row. The records are **not currently matched to station-level predictions** and must not be counted as model true positives or false negatives.

## Inclusion and matching rules

- Keep the source URL, publishing organization, document/map ID, observation or report timestamp, geography, evidence type, and limitations for every record.
- Distinguish **event onset**, **event interval**, **source snapshot time**, and **satellite acquisition time**. Never substitute one for another.
- Prefer observed inundation/impact evidence from NRSC/ISRO, Bihar Disaster Management Department, district administrations, or other independently documented sources. CWC gauge threshold reports are useful corroboration, but they share the model's input family and must not be represented as fully independent inundation labels.
- A station-level match requires a documented spatial relation (coordinates or a defensible river/reach relationship) and a justified time window. District membership alone is not enough to claim that a gauge's nearby area flooded.
- Store ambiguous cases as `needs_review` or `not_spatiotemporally_matched`; do not infer a negative event merely because a source did not mention flooding.
- Positive event matches should be independently reviewed. For each event, retain the evidence supporting the match and the reason the time window was chosen.
- A non-event/control period requires affirmative evidence that the relevant area was observed and not inundated; absence of a report is not a reliable negative label.
- Report event recall, missed-event count, false-alert burden, and lead-time distributions only after matching rules are frozen. Cluster repeated alerts into one event-alert episode before counting.

## Critical temporal limitation

The current model's documented 2026 holdout does not overlap the two seed source timestamps (2024 and 2025). The 2025 record also falls in the model-selection period, not the untouched 2026 test period. Therefore these seed rows establish a reproducible provenance ledger and a matching workflow, **not a new evaluation score**. To produce a defensible independent score, collect events overlapping a genuinely held-out prediction period or rerun an explicitly designed historical backtest with a later event period held out and no tuning against it.

## Validation status

- Ledger schema and provenance fields: machine-checkable.
- Independent source records: starter sample only; coverage is incomplete.
- Station/reach spatial joins: not yet done.
- Event interval/onset matching: not yet done.
- Ground truth verification: not established for the NRSC rapid map; not established at gauge level for the situation-report row.
- Independent flood-event recall: **not computed**.
- Operational/public-warning eligibility: unchanged; this research prototype is not an official warning service.
