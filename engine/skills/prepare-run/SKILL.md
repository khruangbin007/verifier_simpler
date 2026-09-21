---
name: prepare-run
description: "Fingerprints the inputs and opens the run record. Use as the first step of every review run."
metadata:
  version: "0.0.2"
  carried-out-by: "aiva5_run_report.prepare_run"
---
## Purpose
Record exactly what is under review before anything is read, so every later citation can be re-checked.

## Inputs
The three input folders of the project; the optional glossary.xlsx and tag_rules.yaml; the allow-listed settings.

## Outputs
run_manifest (engine, Python and package versions, settings, input fingerprints, what changed since the previous run). Model_Package_Info: identity rows.

## Procedure
1. List every input file, walking into folders, in name order; leave out what an operating system or an editor leaves behind and the support folder of a saved web page, and name each file left out. 2. Compute SHA-256 and the content identifier of each. 3. Compare with the previous run of the same project. 4. Write the manifest.

## Quality rules
Settings are written through the allow-list only. File order is file-name order, never folder order.

## Never
Never record the access token. Never modify, move or rename an input.
