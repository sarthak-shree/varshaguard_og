# VarshaGuard Bihar v1

Bihar v1 is isolated from the historical v0.2.0 prototype. The first geography is Patna and Muzaffarpur with a 24-hour forecast horizon.

## Dataset assembly

Use `backend.bihar_v1.dataset_assembler` to turn local source CSVs into filtered, normalized evidence and leakage-safe training tables.

Example:

```bash
python -m backend.bihar_v1.dataset_assembler \
  --hourly-rainfall /path/hourly_rainfall.csv \
  --daily-rainfall /path/daily_rainfall.csv \
  --river /path/river_level.csv \
  --events /path/flood_inventory.csv
```

Value-column names are configurable with `--*-value-column`.

The assembler writes only derived datasets under `data/bihar_v1/processed` and `data/bihar_v1/training` when no `--output-root` is supplied. Raw source files are never copied into the repository.

Daily rainfall is retained as a separate processed dataset. It is not repeated across hourly timestamps, because that would manufacture temporal resolution and leak assumptions into the model.

A district is marked `trainable` only when its assembled training table contains both positive and negative samples. Muzaffarpur is not granted synthetic river coverage when the source registry has no supported river station.

The existing v0.2.0 prototype remains untouched.
