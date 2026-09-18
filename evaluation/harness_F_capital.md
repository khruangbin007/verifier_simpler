# Seeded-difference harness: F_capital

Run on 2026-09-18 with the stand-in chat() (well-behaved). Counts, not only percentages: with 30 mutants of a type, 30 of 30 supports a claim of about 90 percent, not 100.

False-flag rate on the clean baseline: 0 of 36 units listed in gold_clean_units.csv ended flagged.

| Operator | Mutants | Flagged as expected | Flagged otherwise | Not flagged |
|---|---|---|---|---|
| change a cell | 1 | 1 | 0 | 0 |
| change a constant | 12 | 12 | 0 | 0 |
| change a stated default | 2 | 2 | 0 | 0 |
| change a stated value | 3 | 3 | 0 | 0 |
| change a value in the documentation | 6 | 5 | 1 | 0 |
| drop a row | 1 | 1 | 0 | 0 |
| drop the export tag | 6 | 6 | 0 | 0 |
| flip a sign | 4 | 4 | 0 | 0 |
| remove a floor or cap | 2 | 2 | 0 | 0 |
| rename a parameter | 12 | 12 | 0 | 0 |
| swap an operator | 6 | 5 | 0 | 1 |
| swap two values | 1 | 1 | 0 | 0 |

## Every mutant

| Id | Operator | File | Line | What changed | Outcome | Categories raised |
|---|---|---|---|---|---|---|
| S-001 | flip a sign | R/capital.R | 12 | '-' became '+' | flagged as expected | Code differs from methodology |
| S-002 | swap an operator | R/capital.R | 13 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-003 | swap an operator | R/capital.R | 23 | '*' became '/' | not flagged |  |
| S-004 | change a constant | R/capital.R | 23 | 12.5 became 13.75 (a tenth more) | flagged as expected | Hard-coded number not traced |
| S-005 | change a constant | R/capital.R | 23 | 12.5 became 12.6 (last digit plus one) | flagged as expected | Hard-coded number not traced |
| S-006 | change a constant | R/capital.R | 23 | 12.5 became 6.25 (halved) | flagged as expected | Hard-coded number not traced |
| S-007 | remove a floor or cap | R/capital.R | 32 | 'pmax(m, 1)' became 'm' | flagged as expected | Code differs from methodology |
| S-008 | change a constant | R/capital.R | 32 | 5 became 5.5 (a tenth more) | flagged as expected | Hard-coded number not traced |
| S-009 | change a constant | R/capital.R | 32 | 5 became 6 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-010 | change a constant | R/capital.R | 32 | 5 became 2.5 (halved) | flagged as expected | Hard-coded number not traced |
| S-011 | rename a parameter | R/capital.R | 4 | @param pd became pd_x | flagged as expected | Package documentation differs from code |
| S-012 | rename a parameter | R/capital.R | 5 | @param lgd became lgd_x | flagged as expected | Package documentation differs from code |
| S-013 | rename a parameter | R/capital.R | 6 | @param segment became segment_x | flagged as expected | Package documentation differs from code |
| S-014 | drop the export tag | R/capital.R | 6 | @export removed | flagged as expected | Package documentation differs from code |
| S-015 | change a stated value | R/capital.R | 18 | 12.5 became 13.75 | flagged as expected | Package documentation differs from code; Package documentation differs from methodology |
| S-016 | rename a parameter | R/capital.R | 19 | @param k became k_x | flagged as expected | Package documentation differs from code |
| S-017 | rename a parameter | R/capital.R | 20 | @param ead became ead_x | flagged as expected | Package documentation differs from code |
| S-018 | drop the export tag | R/capital.R | 20 | @export removed | flagged as expected | Package documentation differs from code |
| S-019 | rename a parameter | R/capital.R | 29 | @param m became m_x | flagged as expected | Package documentation differs from code |
| S-020 | drop the export tag | R/capital.R | 29 | @export removed | flagged as expected | Package documentation differs from code |
| S-021 | flip a sign | R/correlation.R | 7 | '-' became '+' | flagged as expected | Code differs from methodology |
| S-022 | swap an operator | R/correlation.R | 7 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-023 | change a constant | R/correlation.R | 7 | 50 became 55.0 (a tenth more) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-024 | change a constant | R/correlation.R | 7 | 50 became 51 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-025 | change a constant | R/correlation.R | 7 | 50 became 25.0 (halved) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-026 | flip a sign | R/correlation.R | 8 | '+' became '-' | flagged as expected | Code differs from methodology |
| S-027 | swap an operator | R/correlation.R | 8 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-028 | change a constant | R/correlation.R | 8 | 0.12 became 0.132 (a tenth more) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-029 | change a constant | R/correlation.R | 8 | 0.12 became 0.13 (last digit plus one) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-030 | change a constant | R/correlation.R | 8 | 0.12 became 0.060 (halved) | flagged as expected | Code differs from methodology; Hard-coded number not traced |
| S-031 | change a stated value | R/correlation.R | 3 | 0.12 became 0.132 | flagged as expected | Package documentation differs from code; Package documentation differs from methodology |
| S-032 | rename a parameter | R/correlation.R | 4 | @param pd became pd_x | flagged as expected | Package documentation differs from code |
| S-033 | drop the export tag | R/correlation.R | 4 | @export removed | flagged as expected | Package documentation differs from code |
| S-034 | remove a floor or cap | R/pd.R | 8 | 'pmax(pd, floor)' became 'pd' | flagged as expected | Code differs from methodology |
| S-035 | swap an operator | R/pd.R | 21 | '*' became '/' | flagged as expected | Code differs from methodology |
| S-036 | flip a sign | R/pd.R | 22 | '+' became '-' | flagged as expected | Code differs from methodology |
| S-037 | swap an operator | R/pd.R | 22 | '/' became '*' | flagged as expected | Code differs from methodology |
| S-038 | change a stated value | R/pd.R | 3 | 0.03 became 0.033 | flagged as expected | Package documentation differs from code |
| S-039 | rename a parameter | R/pd.R | 4 | @param pd became pd_x | flagged as expected | Package documentation differs from code |
| S-040 | rename a parameter | R/pd.R | 5 | @param floor became floor_x | flagged as expected | Package documentation differs from code |
| S-041 | change a stated default | R/pd.R | 5 | default 0.0003 became 0.00015 | flagged as expected | Package documentation differs from code |
| S-042 | drop the export tag | R/pd.R | 5 | @export removed | flagged as expected | Package documentation differs from code |
| S-043 | rename a parameter | R/pd.R | 15 | @param pd became pd_x | flagged as expected | Package documentation differs from code |
| S-044 | rename a parameter | R/pd.R | 16 | @param rho became rho_x | flagged as expected | Package documentation differs from code |
| S-045 | rename a parameter | R/pd.R | 17 | @param q became q_x | flagged as expected | Package documentation differs from code |
| S-046 | change a stated default | R/pd.R | 17 | default 0.999 became 0.4995 | flagged as expected | Package documentation differs from code |
| S-047 | drop the export tag | R/pd.R | 17 | @export removed | flagged as expected | Package documentation differs from code |
| S-048 | change a cell | data/lgd_floors.rda |  | first row of lgd_floor times 1.5 | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-049 | drop a row | data/lgd_floors.rda |  | last row removed | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-050 | swap two values | data/lgd_floors.rda |  | first two values of lgd_floor swapped | flagged as expected | Documentation differs from code; Value differs from methodology |
| S-051 | change a value in the documentation | capreq_model_documentation.docx |  | 0.03 became 0.033 | flagged otherwise | Documentation statement not traced |
| S-052 | change a value in the documentation | capreq_model_documentation.docx |  | 99.9 became 109.89 | flagged as expected | Documentation differs from methodology |
| S-053 | change a value in the documentation | capreq_model_documentation.docx |  | 0.12 became 0.132 | flagged as expected | Documentation differs from methodology |
| S-054 | change a value in the documentation | capreq_model_documentation.docx |  | 0.15 became 0.165 | flagged as expected | Documentation differs from code; Documentation differs from methodology |
| S-055 | change a value in the documentation | capreq_model_documentation.docx |  | 0.25 became 0.275 | flagged as expected | Documentation differs from code; Documentation differs from methodology |
| S-056 | change a value in the documentation | capreq_model_documentation.docx |  | 0.45 became 0.495 | flagged as expected | Documentation differs from code; Documentation differs from methodology |

Every mutant that ended *not flagged* has to be inspected by hand and labelled *equivalent* or *missed*.
