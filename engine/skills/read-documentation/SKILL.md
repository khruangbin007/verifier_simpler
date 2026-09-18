---
name: read-documentation
description: "Reads the model documentation into citable chunks and marks which ones state something checkable. Use after read-methodology."
metadata:
  version: "0.0.2"
  carried-out-by: "aiva1_documents.read_documentation"
---
## Purpose
Same contract as the methodology, plus a first decision on which chunks state a formula, number, rule or definition.

## Inputs
Files in Inputs/3_Model_Documentation.

## Outputs
chunks_doc; read_repairs. Sheet: Chunks_Doc.

## Procedure
As read-methodology; then mark each chunk checkable or not by pattern.

## Quality rules
- Every smallest piece of text in the file ends in one named class: kept in a unit, kept in a unit's other fields, read into another form, left out under a named rule, or reported as not read. What is in none of them is counted and located on Model_Package_Info.
- Nothing a unit shows may come from anywhere but the file or a transform named in the code.
References run across several files in file-name order.

## Never
- Never leave a piece of the file out of the account in silence. An open account is written down, and the run goes on.
Never execute or evaluate anything from an input.
