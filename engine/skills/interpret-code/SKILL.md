---
name: interpret-code
description: "Asks the language model to say in plain words what each piece of code does, shown together with where the piece sits in the whole package. Use after read-package and confirm-outline, before judge-links."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva3_mapping.interpret_code"
---
## Purpose
Help a validator who is not a programmer to read the package: one plain-language interpretation per function, formula statement, top-level statement and test block, shown in the column "LLM Interpretation" of Chunks_Model.

## Inputs
model_units, package_info, the prompt template references/prompts/interpret-code.txt.

## Outputs
interpretations: unit_ref, interpretation, quote_from_unit, question_id, note. Column: LLM Interpretation on Chunks_Model.

## Procedure
1. Build the outline of the package once: its name and title, and for every file the functions defined in it with their arguments and the first line of their documentation. 2. For each piece of code, put together what surrounds it: the whole function a statement sits inside, its documentation in the package, what calls it, what it calls, the stored data it reads. 3. Ask one question per piece, within the token budget. 4. Validate: strict JSON; an interpretation of sensible length; a quotation that is in the piece of code word for word. 5. Write the accepted interpretations in the order of the units.

## Quality rules
An interpretation is an aid to reading. It gives no status to a unit, raises no flagged item and takes no part in the coverage identity. A rejected or failed question leaves the cell with a plain note; the run continues.

## Never
Never use an interpretation as evidence in a check. Never show the model's words as AIVA's own: the cell shows them as a quotation. Never repair malformed JSON.
