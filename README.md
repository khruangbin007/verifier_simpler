# Verifier

Reads a model's methodology, its package of code and data, and its documentation into numbered units, and links each piece of the package to the pieces it takes from and gives to. It runs no model, rates nothing and decides nothing; the organisation's language model explains each piece of code in the credit concepts it implements, finds the chunks of the methodology behind it, and flags where the code may depart from them, for the analyst who checks it against the methodology.

```
Verifier.ipynb          the notebook: four cells, each one call into the engine
engine/
  verifier.py           the whole tool: its steps, reading, chunking, the links, the model's questions, the workbook
  requirements.txt      what the tool needs installed
  Manual.md             the one manual, for everyone
```

A run writes into the project's folder, beside its three input folders: `Output.xlsm`, with five sheets - what was read, what the organisation's model says of the code, and each item it flags, one to a row, for a reviewer's decision; a click on a reference shows only the rows it names - and the `_Audit` folder, the record of the run: `Audit_Log.xlsx` - every step, every record, every exchange with the model, and an inventory of every file - and, for each step, a folder of JSON files for everything it read, made or asked the model, in the order written.

Everything else is in the manual.
