# Maintaining Verifier: the tests and tools

This folder lives only on the branch `maintainer-tools`, beside a copy of the engine it tests. The tool itself ships
without it: nothing the tool runs ever reads this folder.

## Before you start

- Python 3.12 with the engine's packages (`engine/requirements.txt`) and pandas.
- flowR, as the engine gets it: it fetches the pinned release from GitHub. Where GitHub cannot be reached, put the
  pinned archive (`flowr-2.15.8-linux-x64.tar.gz`) in a folder and name that folder in `VERIFIER_FLOWR_DIR`.
- Run everything from this folder: `cd engine/tests`. `paths.py` finds the engine, the notebook and the samples
  from here; nothing depends on where the checkout is.

No test needs the organisation's model: `harness.py` holds a stand-in gateway that answers every question the way
a model would, from what the question shows, and can be made to fail, refuse, expire a token or be interrupted.

## After any change: the three things to run

1. **The golden capture.** `python3 golden.py compare golden_base.json` reruns the eight sample projects and
   compares every sheet of `Output.xlsm`, every record and every file of `_Audit` with the capture taken before
   (run ids, times, durations and local folders are masked). A pure refactor must say `identical: 8 of 8
   samples`; a change that means to alter outputs must differ only where it meant to. When it is right, take a
   new capture: `python3 golden.py capture golden_base.json`.
2. **The signposts.** `python3 signposts.py write` regenerates the contents, the part banners and every
   docstring's *Used by*, *Uses* and *Holds* in `verifier.py`; `python3 signposts.py check` must then say
   `idempotent: True | the file's signposts are current: True` (it exits 1 while any is stale). Never edit a
   signpost by hand.
3. **The suite** below.

## The suite, and what a pass looks like

| Script | What it checks | A pass |
|---|---|---|
| `test_a.py` | every cell of the eight samples against what the stand-in gateway was asked | `wrong 0` for every sample |
| `test_faults.py` | B: 1 and 256 questions at once give the same workbook; C: faults everywhere; D: a token expires and a fresh one is pasted; E: the cell is interrupted twice; F: oversized questions refused. `TESTS=F` runs one | every line `wrong 0 \| answered twice 0`, each ending `finished`; B `same workbook ... True` |
| `test_words.py` | the model's words are kept as written; technical text is still kept out | `asked again for words: 0`, `cells withheld anywhere: 0` |
| `still_answering.py` | the short question a step asks before it stops | refused: `stopped: False`, 30 of 30; outage: `stopped: True`; `main thread still reads the widgets ... True` |
| `flagged_test.py` | Flagged_Items: its links, its dropdown | `faults: none` |
| `param_links.py` | fourteen ways code reads stored data | `wrong: 0` |
| `links_test.py` | every hyperlink of the workbook; an edited workbook is never replaced | `faults: none` |
| `lift_test.py` | projects laid out before, brought to the present layout | cases A to F as described in each line |
| `journal_test.py` | answers survive a restart of Python | `asked again: 0 of 18`, `cell 4: 9 of 9 confirmed` |
| `rerun_audit.py` | an expired token, a new PAT, every cell again: `_Audit` only grows | `cell 4: 9 confirmed`, `tokens in _Audit: none` |
| `archive_test.py` | a new run keeps the run before, byte for byte | `byte for byte ... True`, `9 of 9 confirmed` |
| `audit_test.py`, `audit_resume.py` | the `_Audit` folder: its files, its inventory, a retried step | `9 of 9`, `files holding the token: none` |
| `outage.py` | four outages through the notebook's cells | each `after the fix ... finished \| ... as without an outage: True` |
| `ship05.py` | the four cells of `Verifier.ipynb`, end to end | nine checks, each `Confirmed` |

`check_plan.py <path to Verifier_Build_Plan.md>` checks the Build Plan's contracts against the code: every line
must say `True`.

## When you add or move a function

Put it in the section of the step that uses it, or in part 1 when several parts do; then regenerate the
signposts. If you move whole sections, the contents at the top of `verifier.py` follow by themselves.
