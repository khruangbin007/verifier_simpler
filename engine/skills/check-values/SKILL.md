---
name: check-values
description: "Compares stored and stated values with the methodology under one displayed precision rule. Use after judge-links."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva4_checks.check_values"
---
## Purpose
Cell-by-cell comparison of parameter tables; numbers in code, roxygen and documentation.

## Inputs
parameter_tables, chunks with tables, links.

## Outputs
value_checks. Columns: Parameter completeness, Hard-coded numbers, Value check.

## Procedure
1. Match tables by link and by shape. 2. Map columns by header, then by values, then by a validated AI answer. 3. Align rows by key. 4. Compare every cell under the rule.

## Quality rules
One comparison function everywhere; its rule text is the text shown on Model_Package_Info. No hidden tolerance.

## Never
Never claim anything about numbers that have no counterpart.
