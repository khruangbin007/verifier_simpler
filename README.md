# AIVA 0.0.1 - AI Verification Assistant

AIVA helps a model validator compare three things: a **methodology**, the **R package** that implements it, and the **model documentation**. It links what corresponds, checks formulas, values and stated rules by code, and raises what it could not line up as *flagged items* for a named person to decide. It rates nothing and never changes its inputs.

| Where | What |
|---|---|
| `AIVA_Interface.ipynb` | the only file an analyst opens (Databricks notebook, 12 widgets, 18 cells) |
| `engine/` | five flat bundles `aiva1_documents.py` ... `aiva5_run_report.py` and the shared `aiva0_shared.py`; `pipeline.yaml`; `skills/` (the written contract of every step); `references/` (layout, tag rules, function map, prompts, word lists) |
| `engine/tests/` | the test suite, the stand-in `chat()`, four invented sample projects with hand-made gold files, the equivalence and bad-answer corpora |
| `tools/` | `build_samples.py`, `build_notebook.py`, `build_manual.py`, `check_docs.py`, `count_lines.py`, `seed_differences.py`, `run_harness.py`, `recall_at_k.py`, `live_trial.py`, `environment_probe.py`, `make_release_manifest.py` |
| `docs/` | `AIVA_User_Manual.md` and `.docx`, the evaluation dossier, the release manifest, `review_records/` for the five reviewers |
| `evaluation/` | harness results, recall ladder, hand labels of mutants that were not flagged |
| `Projects/` | review projects; confidential, never in Git |

## Start here

- **Analysts:** manual Part II (chapters 4 to 12), then open the notebook.
- **Reviewers of the code:** manual Part III; read `engine/aiva0_shared.py` first, then your bundle, then run your test file and `cell 17`.
- **Everything offline:** `python -m unittest discover -s engine/tests` (about one minute).

## After any change

```
python -m unittest discover -s engine/tests     # the whole suite
python tools/run_harness.py F_capital            # seeded differences, stand-in chat()
python tools/build_notebook.py                   # if the notebook's cells changed
python tools/build_manual.py                     # the manual's generated parts
python tools/check_docs.py                       # manual and code must agree
python tools/make_release_manifest.py            # always last
```

## What has and has not been shown

Everything measured so far used invented samples and the deterministic stand-in for `chat()`; see `docs/AIVA_0.0.1_Evaluation_Dossier.md`. The Databricks probes, the live trial with the real model, the evaluation campaign and the reviewers' sign-offs are the owner's part and are listed there.
