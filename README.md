# Verifier

Reads a model's methodology, its package of code and data, and its documentation; maps how the model computes what it returns, from each final output down to its rawest inputs; and links what corresponds, in the model's own words and the documents' own words. It runs no model, rates nothing, decides nothing, and is tied to no sector.

```
Verifier.ipynb          the notebook: five cells
docs/Manual.md          the one manual, for everyone
engine/
  verifier.py           the whole tool: reading, parsing, chunking, the map, the links, the workbook
  pipeline.yaml         six steps, in order, each versioned
  requirements.txt      what the tool needs installed
  tests/                the tests, the sample projects and the maintainer's tooling
```

A run leaves one folder: `Output.xlsx` with seven sheets — what was read, how the model computes it, the concepts, the implementation map and what it covers — and `_audit/Audit_Log.xlsx`, the record of the run: every step, every record and every exchange with the model.

Run the tests with `python -m unittest discover engine/tests`. Everything else is in the manual.
