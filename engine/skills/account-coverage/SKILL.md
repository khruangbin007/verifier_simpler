---
name: account-coverage
description: "Gives every unit exactly one status, raises the flagged items and checks the coverage identity. Use after all checks."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva4_checks.account_coverage"
---
## Purpose
Closed accounting.

## Inputs
All units, links and check records.

## Outputs
unit_status; flagged_items; coverage. Sheets: Mapping_Coverage, Flagged_Items; columns Overall status and Flagged item(s).

## Procedure
1. Apply the ordered status rules. 2. Raise one item per unit and category. 3. Number items once, in a fixed order. 4. Check the identity.

## Quality rules
If the identity fails the run stops and says this is a defect in AIVA.

## Never
Never rate how much an item matters.
