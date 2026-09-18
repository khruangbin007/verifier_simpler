---
name: find-candidates
description: "Proposes, for every unit and target corner, a short list of passages with a plain reason. Use before each judge-links pass."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva3_mapping.find_candidates"
---
## Purpose
Recall: the right passage should be somewhere in the shortlist.

## Inputs
The graph, the units, the bridge vocabulary; in pass 2, the links accepted in pass 1.

## Outputs
candidates; search_records. Columns: What was searched.

## Procedure
1. Turn each unit into named fields. 2. Rank by each signal. 3. Fuse ranks. 4. Always include explicitly cited chunks. 5. Write the reason and the search record, also when nothing was proposed.

## Quality rules
Fully deterministic. Every candidate has a reason. A propagated candidate is a suggestion only.

## Never
Never create a link. Never call the language model.
