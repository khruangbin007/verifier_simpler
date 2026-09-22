# Verifier

Reads a model's methodology, its package of code and data, and its documentation; links what corresponds; checks by code whether linked formulas, values and stated rules agree; and raises what it could not line up as questions for a person. It runs no model, rates nothing, and is tied to no sector.

```
Verifier.ipynb          the notebook: five cells
docs/Manual.md          the one manual, for everyone
engine/
  core.py               contracts, the reading floor, the front door
  reading.py            documents and the package into units
  review.py             links, checks, statuses, flagged items
  runner.py             the run, its record, the workbook, the report
  develop.py            measurements, release, the notebook builder
  pipeline.yaml         eighteen steps, in order, each versioned
  release.json          the fingerprint of every engine file
  references/           tag rules, prompts, the workbook layout
  tests/                the tests and the sample projects
```

Run the tests with `python -m unittest discover engine/tests`. Everything else is in the manual.
