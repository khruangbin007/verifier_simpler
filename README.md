# Verifier

Reads a model's methodology, its package of code and data, and its documentation; maps how the model computes what it returns, from each final output down to its rawest inputs; and links what corresponds, in the model's own words and the documents' own words. It runs no model, rates nothing, decides nothing, and is tied to no sector.

```
Verifier.ipynb          the notebook: four cells, each one call into the engine
docs/Manual.md          the one manual, for everyone
Engine_Map.xlsx         every function of the engine and what calls what, as of this version
engine/
  verifier.py           the whole tool: reading, parsing, chunking, the map, the links, the workbook
  pipeline.yaml         five steps, in order, each versioned
  requirements.txt      what the tool needs installed
```

A run leaves one folder: `Output.xlsx` with six sheets - what was read, how the model computes what it returns, and what that covers - and `_audit/Audit_Log.xlsx`, the record of the run: every step, every record and every exchange with the model.

Everything else is in the manual.
