# Verifier

Reads a model's methodology, its package of code and data, and its documentation; maps how the model computes what it returns, from each final output down to its rawest inputs. It runs no model, rates nothing, decides nothing, and is tied to no sector.

```
Verifier.ipynb          the notebook: four cells, each one call into the engine
docs/Manual.md          the one manual, for everyone
Engine_Map.xlsx         every function of the engine and what calls what, as of this version
engine/
  verifier.py           the whole tool: reading, parsing, chunking, the map, the workbook
  pipeline.yaml         three steps, in order, each versioned
  requirements.txt      what the tool needs installed
```

A run leaves one folder: `Output.xlsx` with five sheets - what was read, and how the model computes what it returns - and `_audit/Audit_Log.xlsx`, the record of the run: every step, every record and every exchange with the model.

Everything else is in the manual.
