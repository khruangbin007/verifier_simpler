---
name: read-documentation
description: "Reads the model documentation into citable chunks and marks which ones state something checkable. Use after read-methodology."
metadata:
  version: "0.0.1"
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
References run across several files in file-name order.

## Never
Never execute or evaluate anything from an input.
