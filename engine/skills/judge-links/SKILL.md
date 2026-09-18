---
name: judge-links
description: "Asks the language model narrow, lettered questions about one unit and its shortlist, and validates every answer by code. Use after find-candidates."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva3_mapping.judge_links"
---
## Purpose
Precision: decide which proposed passages a unit corresponds to, and how.

## Inputs
candidates, units, the prompt templates in references/prompts.

## Outputs
corresponds edges in graph_ledger with provenance; call records. Columns: refs, relations, How established.

## Procedure
1. Build each question within its token budget. 2. Plant control passages. 3. Order passages by hash. 4. Ask. 5. Validate: strict JSON, letters shown, verbatim quotations, no planted passage accepted. 6. Write accepted links in a fixed order.

## Quality rules
A rejected or failed question leaves the unit without a link; the run continues.

## Never
Never accept an identifier the model wrote. Never repair malformed JSON. Never let the model's answer be the last word where a deterministic check exists.
