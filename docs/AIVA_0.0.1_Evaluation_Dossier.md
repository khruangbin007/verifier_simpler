# AIVA 0.0.1 - Evaluation dossier

Status on 18 September 2026: **everything below was measured offline, on invented sample projects, with the deterministic stand-in for `chat()`.** No result in this dossier comes from a real language model or from a real model package. The parts that only the owner can produce are listed in section 9 and are not claimed here.

## 1. Intended use and limits

AIVA supports an independent reviewer; it does not replace one. It reads a methodology, an R package and the model documentation, links what corresponds, checks formulas, values and stated rules by code, and raises what it could not line up as flagged items for a named person to decide. A status of *Traced to methodology* means "AIVA saw nothing that does not line up", never "confirmed correct". AIVA's output is always reviewed by people and is never the only control. Limits: manual chapter 12.

## 2. Classification of the tool

AIVA never modifies its inputs (rule R6; `test_aiva5_run_report.RunnerAndWorkbook.test_a_run_writes_only_inside_its_own_folder`), so it cannot put a defect into a model. What it can do is fail to flag something. As long as clean statuses are not used to drop other review work, this is the least demanding class of tool in the sense of tool-qualification guidance. If the organisation later wants to reduce human review on the strength of clean statuses, this evaluation has to be strengthened first.

## 3. What the tool is required to do, and where that is enforced

The sixteen SKILL.md contracts, rules R1 to R12 and the data contracts, each traced to functions and tests: manual chapter 21 (generated map from rule to function), chapters 15 to 19 (checklists whose every line names a test), Appendix C (code index). `tools/check_docs.py` fails when any of these references stops existing.

## 4. Known-answer results

**4.1 Mathematical check.** `engine/tests/equivalence_corpus.yaml`: 51 equivalent and 54 differing pairs. Every equivalent pair ends as agreeing; every differing pair ends as differing, each with a counterexample; **no differing pair is reported as agreeing** (`test_aiva4_checks.FormulaComparison.test_the_corpus_no_differing_pair_ever_agrees`).

**4.2 Seeded differences.** `tools/run_harness.py` plants one difference at a time (operators of plan 4.3) and runs the whole pipeline.

| Sample | Mutants | Flagged as expected | Flagged otherwise | Not flagged | False flags on the clean baseline |
|---|---|---|---|---|---|
| F_capital | 56 | 54 | 1 | 1 | 0 of 36 units |
| A_minimal | 49 | 46 | 1 | 2 | 0 of 26 units |
| D_dosing | 16 | 15 | 0 | 1 | 0 of 9 units |

Counts, not only percentages: with at most 12 mutants of one type per sample, these numbers show that every route works on the samples; they do not support a detection rate for real packages. The four mutants that were not flagged are labelled in `evaluation/not_flagged_labels.md`; all four change a step that the methodology states only in prose or as an image. Per-operator tables: `evaluation/harness_F_capital.md`, `evaluation/harness_A_minimal.md`, `evaluation/harness_D_dosing.md`.

**4.3 The six seeded differences of the brief** (`F_capital_known`): all six are raised with the expected Concerns and Category, including the flipped sign in `cond_pd` ("Numerical check: differs" with the inputs and both results); `test_aiva4_checks.SeededSample.test_all_six_seeded_differences_are_flagged_in_an_expected_category`.

**4.4 Recall of the search stage** (`tools/recall_at_k.py`, `evaluation/relatedness_report.md`): recall at 5 is complete on all three samples (56 gold units) already with the field-aware text ranking; on F_capital the anchors lift recall at 3 from 26 to 28 of 28. The samples are small (at most 28 passages), so they cannot show which signal earns its place on a real methodology. No signal was removed on this evidence; the question stays open for Phase 12.

**4.5 Judgement quality** can only be measured with the real model. The tool for it exists (`tools/live_trial.py`) and was exercised with the stand-in (`evaluation/live_trial_2026-09-18_standin.md`); its numbers say nothing about a model.

## 5. The tool's own means of detecting its malfunctions

The coverage identity in four parts, checked on every run, each part proven to stop the run when violated; validators for every answer of the model with a corpus of 22 bad answers; planted control passages in every judge question; the second, oppositely framed question; hash chains over the graph ledger and the determinations; the verification cell, proven to detect a changed input byte, a changed chunk, a broken chain and a deleted status record; a differential test of the restart walk against an independent implementation (networkx).

Not built in 0.0.1: a second, independent decoder of stored R data, and a differential test of the R reader against tree-sitter (neither library was available in the build environment).

## 6. Reproducibility

Two runs give identical audit records apart from time stamps, and the same graph version id. Results do not depend on the number of workers (1, 4, 16). A run resumed after a pause repeats no question. Replaying the recorded answers reproduces graph, statuses and items. Tests: `test_end_to_end.TwoRunsAreTheSame`, `test_aiva5_run_report.TokenRefresh`, `test_aiva5_run_report.ResumeAndBreaker`. Live stability (two runs with a real model) is not measured.

## 7. Recorded environment and dependencies

Built and tested on Python 3.12.3 with PyYAML, openpyxl, python-docx, numpy, scipy, sympy, rdata, pdfplumber and pypdf. `docs/release_manifest.json` holds the SHA-256 of every engine file, the skill versions and the requirements; `python tools/make_release_manifest.py --check` compares a checkout with it.

| Dependency | What AIVA relies on it for | Note |
|---|---|---|
| PyYAML | reading the pipeline, layout, rules and prompts files | `safe_load` only |
| openpyxl | writing and reading the workbook | widely used; format checked by reading the file back |
| python-docx | writing the report and the run summary; never used to read inputs | input .docx files are read as raw XML by AIVA's own code |
| numpy, scipy | the numerical check (normal distribution and its inverse), the sparse walk | results cross-checked by the symbolic step where it applies |
| sympy | the bounded symbolic step | objects are built node by node; no string is parsed |
| rdata | decoding .rda and .rds files without R | pure Python; the only decoder in 0.0.1 |
| pdfplumber, pypdf | reading PDF inputs | optional; PDF is the weakest input form |

## 8. Known limitations and assumptions made while building

Limits of what AIVA can read or decide: manual chapter 12. Assumptions and deviations from the build plan that the owner should confirm:

1. Sheet names, their order, column headers and colours follow the plan's description; no original brief file was available to compare with.
2. The project layout `Projects/<model ID>/<date>/Inputs|Run_*` and the `M-` prefix for model units.
3. Sixteen skills instead of fifteen: the two search passes and the two judge passes share a skill each, and both human steps have a contract.
4. Call records are written and synced after every 100 questions and after every step, not every 200 calls or 60 seconds.
5. A table is shown with one row per line and "; " between cells.
6. No second reader of stored data; R classes and attributes beyond what `rdata` gives are not extracted; missing values of different kinds are not told apart.
7. Figures of the methodology raise an item each (the plan requires this for image equations; AIVA cannot tell the two apart).
8. Code inside vignettes counts as supporting code; a missing data block is only reported for objects under `data/`.
9. Two extensions of the status rules: a statement that does not agree on its own takes the result of the check of its whole function when both are linked to the same passage; a statement without a link counts as traced when the agreeing check of its function ran through it.
10. Docstrings and comments make up 13 to 23 percent of the engine files, below the plan's aim of 30 percent; every public function has a docstring, and the files are within their line budgets.
11. The stand-in `chat()` is a test double with simple, explainable rules. It was adjusted during the build so that it links formulas the way a careful reader would; this makes the samples exercise every route, and is no evidence about a real model.

## 9. What only the owner can do

- The environment probes P-1 to P-13 on the Databricks cluster (`cell 16`, `tools/environment_probe.py`), and the offline suite run on the cluster.
- The live trial with the real `chat()` (`tools/live_trial.py`): share of unreadable answers, rejections by reason, planted-passage acceptance, correctness against the gold files, what the stated percentage means, latency, token pauses.
- The Phase 12 campaign: the harness at scale with the real model, one complete run on a real review project with a triage sample, recall on hand-labelled real units, live stability.
- R-made data fixtures (`make_fixtures.R`), to confirm that files written by R itself decode like the samples written from Python.
- The five reviewers' sign-offs under `docs/review_records/`, each by a person who did not write the bundle. Every bundle of 0.0.1 was written in Claude sessions; this is recorded here as the plan requires.

## 10. Change control

| Change | What is re-run before AIVA is relied on again |
|---|---|
| Any engine file, prompt or rules file | version raised; offline suite; stand-in harness; `tools/check_docs.py`; new release manifest |
| The model behind `chat()`, or its settings | the live trial and a subset of the campaign |
| Databricks runtime, Python or a dependency version | offline suite on the cluster; data fixtures |
| A methodology in an XML schema not seen before | outline confirmation by the analyst; tag rules added are an input of the run |

Proposed for ordinary use: for each real review, seed five differences into a copy of the package, run AIVA on the copy and confirm that all five are flagged (`tools/seed_differences.py`).
