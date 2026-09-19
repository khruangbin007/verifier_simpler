---
name: read-package
description: "Reads the R package statically into model units: code, roxygen blocks, help pages, tests and stored parameter data. Use after the documents are read."
metadata:
  version: "0.0.3"
  carried-out-by: "aiva2_package.read_package"
---
## Purpose
Account for every file of the tarball and every non-blank line of every R file, without R.

## Inputs
The single .tar.gz in Inputs/2_Model_Package; references/r_function_map.yaml.

## Outputs
model_units; parameter_tables; content_accounts; shape_digests; package_info. Sheets: Chunks_Model, Model_Package_Info.

## Procedure
1. Unpack the tarball, refusing any member that breaks the limits. 2. Work out which reader each member gets from where it lies and what it is; where the built-in tests give a member none, ask which existing reader should take it and apply the answer. 3. Parse R source into functions, objects and formula statements. 4. Decode stored data into tables of values. 5. Read help pages and vignettes. 6. Tie each roxygen block to what it documents. 7. Number every unit in a fixed order.

## Quality rules
- Every non-blank line of every member that holds text lies inside a unit, is refused with a reason, or is carried by a unit that says it could not be read. A member AIVA cannot read as text is counted as one piece of its own.
- A reader chosen for a member changes only which existing reader takes it. It never changes how that reader works.
- Where a member's first lines show assignments and calls it is R code, wherever in the package it lies.

## Never
- Never leave a member of the package out of the account in silence. An open account is written down, and the run goes on.
- Never write text of your own into an answer about a package. Name only paths you were shown as not placed, and give only readers from the list you were given.
- Never ask for a member to be skipped: there is no such reader. A file that cannot be made sense of becomes a unit that says so.
- Never let an answer reach the parsing of R code, the building of expression trees or the decoding of stored data. Reading code is a parse, not an opinion.
Never execute or evaluate anything from a package. Never import a package to inspect it.
