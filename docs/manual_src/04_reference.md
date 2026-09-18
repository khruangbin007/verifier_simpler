# Part IV. Reference

## 20. Data contracts

Records are plain dictionaries in JSON Lines files; the dataclasses that produce them are in `aiva0_shared.py` (Appendix C lists them). The most important ones:

| Record | File in `_audit` | Main fields |
|---|---|---|
| Chunk | chunks_canon.jsonl, chunks_doc.jsonl | ref, corner, kind, text, level, heading_chain, numbering, caption, locator, table, equation, refs_out, checkable, content_hash |
| Model unit | model_units.jsonl | ref, kind, name, inside, parent_ref, file, lines, text, code (formals, symbols, numbers, calls, expression, composed, reads_data, exported, plumbing), roxygen, helppage, data, content_hash |
| Parameter table | parameter_tables.jsonl | unit_ref, object_name, header, rows, row_key, column_types |
| Ledger record | graph_ledger.jsonl | node: ref, node_kind, corner. edge: source, target, kind, relation, how, confidence, evidence, provenance. Both: prev_hash, record_hash |
| Candidate | candidates.jsonl | unit_ref, target_ref, target_corner, rank, fused_score, signals, reason, search_pass |
| Search record | search_records.jsonl | unit_ref, target_corner, searched_text, shortlist, ranked_anywhere, note |
| Call record | llm_calls_001.jsonl.gz and following | question_id, question_type, unit_ref, attempt, letters, planted, prompts (token removed), response_text, outcome, answer, final, seconds |
| Math check | math_checks.jsonl | check_id, unit_ref, target_ref, both formulas in linear notation, formula_source, alignment, symbolic, numeric, counterexample, outcome, undecided_reason, seed, points_valid |
| Value check | value_checks.jsonl | check_id, unit_ref, target_ref, what, column_map, key_map, cells, rows on one side only, outcome, sentences, rule_text |
| Rule check | rule_checks.jsonl | check_id, unit_ref, target_ref, rule_as_stated, rule_kind, rule_number, located_by, outcome, where_in_code |
| Package documentation check | package_doc_checks.jsonl | check_id, unit_ref, about_ref, check, outcome, detail |
| Unit status | unit_status.jsonl | unit_ref, corner, status, clean, decided_by_rule, reason_shown, item_ids, cells |
| Flagged item | flagged_items.jsonl | item_id, category, concerns, unit_refs, item, observed, the three side-by-side texts, suggested_next_step, evidence_path, from_checks |
| Determination | determinations.jsonl | item_id, decision, reviewer, role, rationale, recorded_at, recorded_by, workbook_sha256, prev_hash, record_hash |

## 21. Skills and the pipeline

A skill is the written contract of one step (`engine/skills/<name>/SKILL.md`: purpose, inputs, outputs, procedure, quality rules, what it never does). `engine/pipeline.yaml` lists the steps in order; each names its skill and one plain function from the explicit dictionary in `aiva5_run_report.py`. There is no loading of scripts by path, and the runner refuses to start when a SKILL.md version differs from the version its bundle declares.

{{skills}}

**Design rules and the functions that enforce them** (from the "Enforces:" lines of the docstrings):

{{rules_to_functions}}

## 22. Settings

Settings are an allow-list: a name that is not in this table is refused. The notebook sets the concurrency limit, the token cap, the reviewer id and the reviewer role from its widgets.

{{settings}}

## 23. The files in _audit

| File | Content |
|---|---|
| run_manifest.json | model ID, dates, engine version, every input with its SHA-256, what changed since the previous run, who confirmed the outline, hashes of the last workbook written and the last workbook read in |
| run_log.txt | one line per event; texts that were withheld from cells |
| step_records.jsonl | one record per finished step: skill, version, counts, notes, seconds |
| chunks_canon.jsonl, chunks_doc.jsonl, outline.jsonl, read_repairs.jsonl, info_rows.jsonl | what the document reader produced |
| model_units.jsonl, parameter_tables.jsonl, package_info.json | what the package reader produced |
| graph_ledger.jsonl, bridge_vocabulary.jsonl, unresolved_references.jsonl | the graph and what was harvested for the search |
| candidates.jsonl, search_records.jsonl | the search stage |
| llm_calls_001.jsonl.gz and following | every exchange with `chat()`, every attempt, with the token removed |
| judgement_problems.jsonl, doc_judgements.jsonl, second_opinions.jsonl | what the judge step recorded besides links |
| math_checks.jsonl, value_checks.jsonl, rule_checks.jsonl, package_doc_checks.jsonl | the deterministic checks |
| unit_status.jsonl, flagged_items.jsonl, coverage.json | the accounting |
| determinations.jsonl, uploads/ | the human half |
| exports/nodes.csv, exports/edges.csv, exports/graph.graphml | the graph for loading elsewhere |
| Run_Summary.docx | where the run stands, refreshed after every step |

## 24. Prompts

One template per question type under `engine/references/prompts/`; each has a version line, a SYSTEM part and a MAIN part with slots. Every prompt has one purpose, names no domain concept, shows passages under letters in an order derived from a hash, and asks for one JSON object with a closed set of fields.

{{prompts}}

## 25. Tests and sample projects

Run everything with `python -m unittest discover -s engine/tests`.

{{tests}}

Sample projects under `engine/tests/sample_projects/`, all invented and rebuilt byte for byte by `tools/build_samples.py`: `A_minimal` (a neutral parcel-pricing method; XML, a Word file, four help pages), `F_capital` (XML inside a `.txt` file with four levels and a flat-numbered annex; equations as MathML, inline notation, a sentence and an image; stored tables as `.rda` and `.rds`; a help page that is out of step on purpose; a Word file and a PDF), `F_capital_known` (the same with six seeded differences, listed in its `expected_items.csv`) and `D_dosing` (another field, to keep the engine honest about rule R9; Word's web export with preserved equation markup; PDF-only documentation). Each sample has hand-made gold files: `gold_links.csv`, `gold_not_checkable.csv`, `gold_clean_units.csv`.

## 26. Extending AIVA safely

| You want to add | Where | What must be re-evaluated |
|---|---|---|
| a tag rule for a new XML schema | `Inputs/tag_rules.yaml` of the project, or `engine/references/tag_rules.yaml` | `test_aiva1_documents.py`; the outline of one real document |
| an R function the comparison should understand | `engine/references/r_function_map.yaml` (neutral name, arguments, domain), `aiva4_checks.to_sympy` and `aiva4_checks.evaluate` | `test_aiva4_checks.py` with new pairs in `engine/tests/equivalence_corpus.yaml`; Reviewer 2 and Reviewer 4 agree the entry |
| a question type | a prompt under `engine/references/prompts/`, a validator branch in `aiva3_mapping.validate_narrow`, a handler in the stand-in | the bad-answers corpus; the token budget for the largest unit |
| a category | the constants of `aiva0_shared.py`, `aiva4_checks.NEXT_STEPS`, Appendix B | the wording lint; the identity tests |
| a search signal | `aiva3_mapping.search_one`, `aiva3_mapping.REASON_TEMPLATES`, the `signals` setting | `tools/recall_at_k.py`: the signal must earn its place on the ablation ladder |

After any change: the whole test suite, `tools/check_docs.py`, `tools/build_manual.py`, the harness (`tools/run_harness.py`), and a new `docs/release_manifest.json` from `tools/make_release_manifest.py`.

## 27. How AIVA was evaluated

The evaluation dossier is `docs/AIVA_0.0.1_Evaluation_Dossier.md`. In short, with the stand-in `chat()` on invented samples: the equivalence corpus of 100 formula pairs (no differing pair is ever reported as agreeing); the seeded-difference harness (`evaluation/harness_F_capital.md`); the recall ladder of the search stage (`evaluation/relatedness_report.md`); the six seeded differences of `F_capital_known`; reproducibility by replay. What is still to be done with the real model on a real package, by the owner, is listed there as well.

{{line_counts}}

**Dependencies.**

{{dependencies}}
