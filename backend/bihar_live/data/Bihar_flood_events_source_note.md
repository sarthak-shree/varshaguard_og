# Bihar flood-event training source

Source: user-provided extraction from India Flood Inventory-Impacts, derived from the uploaded Zenodo dataset archive.

The source extraction contains 177 records whose `State` field mentions Bihar. These records were used to produce Bihar-specific files locally. This repository copy is a seed/source file and should not be treated as a complete training table until all 177 extracted records are imported.

For model training, event dates must be parsed carefully and labels should only be created when river/rainfall observations precede the event start. Do not use event duration or post-event observations as predictors for the same event because that would create temporal leakage.
