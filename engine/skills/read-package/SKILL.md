---
name: read-package
description: "Reads the R package statically into model units: code, roxygen blocks, help pages, tests and stored parameter data. Use after the documents are read."
metadata:
  version: "0.0.2"
  carried-out-by: "aiva2_package.read_package"
---
## Purpose
Account for every file of the tarball and every non-blank line of every R file, without R.

## Inputs
The single .tar.gz in Inputs/2_Model_Package; references/r_function_map.yaml.

## Outputs
model_units; parameter_tables; package_info. Sheets: Chunks_Model, Model_Package_Info.

## Procedure
1. Unpack safely on local disk, member by member. 2. Fingerprint every file. 3. Parse each R file one top-level expression at a time. 4. Form units. 5. Attach roxygen blocks. 6. Read help pages. 7. Decode data objects, profile and hash them. 8. Record which code reads which data.

## Quality rules
- Every smallest piece of text in the file ends in one named class: kept in a unit, kept in a unit's other fields, read into another form, left out under a named rule, or reported as not read. What is in none of them is counted and located on Model_Package_Info.
- Nothing a unit shows may come from anywhere but the file or a transform named in the code.
An expression that cannot be parsed becomes a unit of kind File not read; the rest of the file is still read. Numbers keep the form in which they were written.

## Never
- Never leave a piece of the file out of the account in silence. An open account is written down, and the run goes on.
Never run R. Never evaluate anything stored in a data file. Never extract an unsafe archive member.
