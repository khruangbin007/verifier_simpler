---
name: build-graph
description: "Builds the append-only graph of chunks, model units and anchors, and harvests the bridge vocabulary. Use after all three corners are read."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva3_mapping.build_graph"
---
## Purpose
Give the search and the checks one tamper-evident graph to walk.

## Inputs
chunks_canon, chunks_doc, model_units, parameter_tables; the optional glossary.

## Outputs
graph_ledger (nodes and structural edges, hash-chained); bridge_vocabulary.

## Procedure
1. Add nodes. 2. Add structural edges in a fixed order. 3. Resolve cross-references as written. 4. Harvest the bridge vocabulary with where each entry was seen.

## Quality rules
Records are appended in a fixed order, never in the order work happened to finish.

## Never
Never change or remove a ledger record.
