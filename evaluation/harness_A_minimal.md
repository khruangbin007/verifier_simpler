# Seeded-difference harness: A_minimal

Run on 2026-09-18 with the stand-in chat() (well-behaved). Counts, not only percentages: with 30 mutants of a type, 30 of 30 supports a claim of about 90 percent, not 100.

False-flag rate on the clean baseline: 0 of 26 units listed in gold_clean_units.csv ended flagged.

| Operator | Mutants | Flagged as expected | Flagged otherwise | Not flagged |
|---|---|---|---|---|
| change a cell | 1 | 1 | 0 | 0 |
| change a constant | 12 | 12 | 0 | 0 |
| change a stated value | 2 | 2 | 0 | 0 |
| change a value in the documentation | 6 | 6 | 0 | 0 |
| drop a row | 1 | 1 | 0 | 0 |
| drop the export tag | 4 | 4 | 0 | 0 |
| flip a sign | 3 | 2 | 0 | 1 |
| remove a floor or cap | 4 | 3 | 1 | 0 |
| rename a parameter | 10 | 10 | 0 | 0 |
| swap an operator | 5 | 4 | 0 | 1 |
| swap two values | 1 | 1 | 0 | 0 |

## Every mutant

| Id | Operator | File | Line | What changed | Outcome | Categories raised |
|---|---|---|---|---|---|---|
| S-001 | flip a sign | R/price.R | 13 | '+' became '-' | flagged as expected | Code differs from methodology |
| S-002 | swap an operator | R/price.R | 13 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-003 | flip a sign | R/price.R | 14 | '+' became '-' | flagged as expected | Code differs from methodology |
| S-004 | swap an operator | R/price.R | 14 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-005 | change a constant | R/price.R | 14 | 0.125 became 0.1375 (a tenth more) | flagged as expected | Hard-coded number not traced |
| S-006 | change a constant | R/price.R | 14 | 0.125 became 0.126 (last digit plus one) | flagged as expected | Hard-coded number not traced |
| S-007 | change a constant | R/price.R | 14 | 0.125 became 0.0625 (halved) | flagged as expected | Hard-coded number not traced |
| S-008 | flip a sign | R/price.R | 15 | '-' became '+' | not flagged |  |
| S-009 | swap an operator | R/price.R | 15 | '*' became '/' | not flagged |  |
| S-010 | remove a floor or cap | R/price.R | 16 | 'pmax(discounted, 4.50)' became 'discounted' | flagged as expected | Code differs from methodology |
| S-011 | change a constant | R/price.R | 16 | 4.50 became 4.950 (a tenth more) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-012 | change a constant | R/price.R | 16 | 4.50 became 4.51 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-013 | change a constant | R/price.R | 16 | 4.50 became 2.250 (halved) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-014 | swap an operator | R/price.R | 25 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-015 | remove a floor or cap | R/price.R | 25 | 'pmin(0.2, 0.01 * n)' became '0.2' | flagged as expected | AI answer could not be used; Code differs from methodology; Mathematical check undecided |
| S-016 | change a constant | R/price.R | 25 | 0.2 became 0.22 (a tenth more) | flagged as expected | Code differs from methodology |
| S-017 | change a constant | R/price.R | 25 | 0.2 became 0.3 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-018 | change a constant | R/price.R | 25 | 0.2 became 0.10 (halved) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-019 | change a stated value | R/price.R | 3 | 12.5 became 13.75 | flagged as expected | Package documentation differs from code |
| S-020 | rename a parameter | R/price.R | 5 | @param zone became zone_x | flagged as expected | Package documentation differs from code |
| S-021 | rename a parameter | R/price.R | 6 | @param cw became cw_x | flagged as expected | Package documentation differs from code |
| S-022 | rename a parameter | R/price.R | 7 | @param n became n_x | flagged as expected | Package documentation differs from code |
| S-023 | drop the export tag | R/price.R | 7 | @export removed | flagged as expected | Package documentation differs from code |
| S-024 | rename a parameter | R/price.R | 22 | @param n became n_x | flagged as expected | Package documentation differs from code |
| S-025 | drop the export tag | R/price.R | 22 | @export removed | flagged as expected | Package documentation differs from code |
| S-026 | swap an operator | R/weights.R | 11 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-027 | remove a floor or cap | R/weights.R | 21 | 'pmax(aw, dw)' became 'aw' | flagged otherwise | Mathematical check undecided |
| S-028 | remove a floor or cap | R/weights.R | 22 | 'pmax(cw, 0.5)' became 'cw' | flagged as expected | Code differs from methodology |
| S-029 | change a constant | R/weights.R | 22 | 0.5 became 0.55 (a tenth more) | flagged as expected | Hard-coded number not traced |
| S-030 | change a constant | R/weights.R | 22 | 0.5 became 0.6 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-031 | change a constant | R/weights.R | 22 | 0.5 became 0.25 (halved) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-032 | rename a parameter | R/weights.R | 4 | @param l became l_x | flagged as expected | Package documentation differs from code |
| S-033 | rename a parameter | R/weights.R | 5 | @param w became w_x | flagged as expected | Package documentation differs from code |
| S-034 | rename a parameter | R/weights.R | 6 | @param h became h_x | flagged as expected | Package documentation differs from code |
| S-035 | rename a parameter | R/weights.R | 7 | @param divisor became divisor_x | flagged as expected | Package documentation differs from code |
| S-036 | drop the export tag | R/weights.R | 7 | @export removed | flagged as expected | Package documentation differs from code |
| S-037 | change a stated value | R/weights.R | 16 | 0.5 became 0.55 | flagged as expected | Package documentation differs from code; Package documentation differs from methodology |
| S-038 | rename a parameter | R/weights.R | 17 | @param aw became aw_x | flagged as expected | Package documentation differs from code |
| S-039 | rename a parameter | R/weights.R | 18 | @param dw became dw_x | flagged as expected | Package documentation differs from code |
| S-040 | drop the export tag | R/weights.R | 18 | @export removed | flagged as expected | Package documentation differs from code |
| S-041 | change a cell | data/zone_rates.rda |  | first row of base_rate times 1.5 | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-042 | drop a row | data/zone_rates.rda |  | last row removed | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-043 | swap two values | data/zone_rates.rda |  | first two values of base_rate swapped | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-044 | change a value in the documentation | parcelcost_documentation.docx |  | 0.5 became 0.55 | flagged as expected | Documentation differs from methodology |
| S-045 | change a value in the documentation | parcelcost_documentation.docx |  | 3.20 became 3.520 | flagged as expected | Documentation differs from code; Documentation differs from methodology |
| S-046 | change a value in the documentation | parcelcost_documentation.docx |  | 0.85 became 0.935 | flagged as expected | Documentation differs from code; Documentation differs from methodology |
| S-047 | change a value in the documentation | parcelcost_documentation.docx |  | 4.90 became 5.390 | flagged as expected | Documentation differs from code; Documentation differs from methodology |
| S-048 | change a value in the documentation | parcelcost_documentation.docx |  | 1.10 became 1.210 | flagged as expected | Documentation differs from code; Documentation differs from methodology |
| S-049 | change a value in the documentation | parcelcost_documentation.docx |  | 9.50 became 10.450 | flagged as expected | Documentation differs from code; Documentation differs from methodology |

Every mutant that ended *not flagged* has to be inspected by hand and labelled *equivalent* or *missed*.
