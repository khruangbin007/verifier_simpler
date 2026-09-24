# Verifier

Reads a model's methodology, its package of code and data, and its documentation; maps how the model computes what it returns, from each final output down to its rawest inputs. It runs no model, rates nothing and decides nothing; the organisation's language model explains each piece of code in the credit concepts it implements, for the analyst who checks it against the methodology.

```
Verifier.ipynb          the notebook: four cells, each one call into the engine
engine/
  verifier.py           the whole tool: its steps, reading, parsing, chunking, the map, the workbook
  requirements.txt      what the tool needs installed
  Manual.md             the one manual, for everyone
```

A run leaves one folder: `Output.xlsx` with five sheets - what was read, and how the model computes what it returns - and `_audit/Audit_Log.xlsx`, the record of the run: every step, every record and every exchange with the model.

Everything else is in the manual.
