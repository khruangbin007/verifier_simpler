---
name: check-rules
description: "Checks that conditions, floors, caps and thresholds stated in linked passages are present in the code. Use after judge-links."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva4_checks.check_rules"
---
## Purpose
Catch a rule stated only in prose that the code does not apply.

## Inputs
links, expression trees, passages.

## Outputs
rule_checks. Column: Logic consistency.

## Procedure
1. Recognise rule phrases. 2. Look in the code's expression tree first. 3. Only if code cannot settle it, ask the check-rule question and validate the quotations.

## Quality rules
The code route comes first.

## Never
Never report applied on the model's word alone when the tree can be inspected.
