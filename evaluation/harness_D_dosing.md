# Seeded-difference harness: D_dosing

Run on 2026-09-18 with the stand-in chat() (well-behaved). Counts, not only percentages: with 30 mutants of a type, 30 of 30 supports a claim of about 90 percent, not 100.

False-flag rate on the clean baseline: 0 of 9 units listed in gold_clean_units.csv ended flagged.

| Operator | Mutants | Flagged as expected | Flagged otherwise | Not flagged |
|---|---|---|---|---|
| change a cell | 1 | 1 | 0 | 0 |
| change a constant | 3 | 3 | 0 | 0 |
| change a stated default | 1 | 1 | 0 | 0 |
| drop a row | 1 | 1 | 0 | 0 |
| drop the export tag | 2 | 2 | 0 | 0 |
| remove a floor or cap | 1 | 1 | 0 | 0 |
| rename a parameter | 4 | 4 | 0 | 0 |
| swap an operator | 2 | 1 | 0 | 1 |
| swap two values | 1 | 1 | 0 | 0 |

## Every mutant

| Id | Operator | File | Line | What changed | Outcome | Categories raised |
|---|---|---|---|---|---|---|
| S-001 | swap an operator | R/dose.R | 8 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-002 | remove a floor or cap | R/dose.R | 9 | 'pmin(dose, 4000)' became 'dose' | flagged as expected | Code differs from methodology |
| S-003 | change a constant | R/dose.R | 9 | 4000 became 4400.0 (a tenth more) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-004 | change a constant | R/dose.R | 9 | 4000 became 4001 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-005 | change a constant | R/dose.R | 9 | 4000 became 2000.0 (halved) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-006 | swap an operator | R/dose.R | 20 | '*' became '/' | not flagged |  |
| S-007 | rename a parameter | R/dose.R | 4 | @param weight became weight_x | flagged as expected | Package documentation differs from code |
| S-008 | rename a parameter | R/dose.R | 5 | @param rate became rate_x | flagged as expected | Package documentation differs from code |
| S-009 | change a stated default | R/dose.R | 5 | default 15 became 7.5 | flagged as expected | Package documentation differs from code; Package documentation differs from methodology |
| S-010 | drop the export tag | R/dose.R | 5 | @export removed | flagged as expected | Package documentation differs from code |
| S-011 | rename a parameter | R/dose.R | 15 | @param dose became dose_x | flagged as expected | Package documentation differs from code |
| S-012 | rename a parameter | R/dose.R | 16 | @param band became band_x | flagged as expected | Package documentation differs from code |
| S-013 | drop the export tag | R/dose.R | 16 | @export removed | flagged as expected | Package documentation differs from code |
| S-014 | change a cell | inst/extdata/band_factors.rds |  | first row of factor times 1.5 | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-015 | drop a row | inst/extdata/band_factors.rds |  | last row removed | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-016 | swap two values | inst/extdata/band_factors.rds |  | first two values of factor swapped | flagged as expected | Documentation differs from code; Value differs from methodology |

Every mutant that ended *not flagged* has to be inspected by hand and labelled *equivalent* or *missed*.
