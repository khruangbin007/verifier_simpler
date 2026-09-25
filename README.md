# Verifier

Reads a model's methodology, its package of code and data, and its documentation into numbered units, and links each piece of the package to the pieces it takes from and gives to. It runs no model, rates nothing and decides nothing; the organisation's language model explains each piece of code in the credit concepts it implements, finds the chunks of the methodology behind it, and flags where the code may depart from them, for the analyst who checks it against the methodology.

```
Verifier.ipynb          the notebook: four cells, each one call into the engine
engine/
  verifier.py           the whole tool: its steps, reading, chunking, the links, the model's questions, the workbook
  requirements.txt      what the tool needs installed
  Manual.md             the one manual, for everyone
```

A run writes two files into the project's folder, beside its `Inputs`: `Output.xlsm`, with four sheets - what was read, and what the organisation's model says of the code, where a click on a reference shows only the chunks it names - and `Audit_Log.xlsx`, the record of the run: every step, every record and every exchange with the model.

Everything else is in the manual.
