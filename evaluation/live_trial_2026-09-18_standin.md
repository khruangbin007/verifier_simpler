# Live trial of the judge questions

Run on 2026-09-18 with the stand-in chat() (a test double, not a model).

## A_minimal

| Measure | Concurrency 1 | Concurrency 4 |
|---|---|---|
| questions | 57 | 57 |
| attempts | 63 | 63 |
| attempts that could not be read | 3 | 3 |
| rejected, by reason | {'it named a passage that was not shown': 2, 'it could not be read': 1} | {'it named a passage that was not shown': 2, 'it could not be read': 1} |
| questions without any answer | 0 | 0 |
| planted passage accepted | 0 of 14 | 0 of 14 |
| accepted links to the methodology that are in the gold file | 23 of 34 | 23 of 34 |
| gold units with an accepted gold link | 17 of 20 | 17 of 20 |
| stated confidence against correctness | {'50-75': '2 of 5 right', '75-100': '21 of 29 right'} | {'50-75': '2 of 5 right', '75-100': '21 of 29 right'} |
| second-question disagreements | 1 | 1 |
| median seconds per call | 0.0 | 0.0 |
| seconds for the run | 1.7 | 1.2 |

The two runs accepted the same links: **yes**.

