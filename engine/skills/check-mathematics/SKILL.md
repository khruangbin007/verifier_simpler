---
name: check-mathematics
description: "Compares linked formulas symbolically and numerically. Use after judge-links."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva4_checks.check_mathematics"
---
## Purpose
Confirm or contradict every link that involves a formula.

## Inputs
corresponds edges; expression trees of code, equations and roxygen formulas; stored parameter values.

## Outputs
math_checks; check edges. Column: Math check.

## Procedure
1. Fix the symbol alignment. 2. Bounded symbolic step. 3. Numeric sampling with a recorded seed and boundary points. 4. Otherwise could not be decided, with one reason from the fixed list.

## Quality rules
Differs is only reported with a counterexample. Could not be decided is never clean.

## Never
Never let SymPy parse a string. Never choose an alignment because it makes the comparison agree.
