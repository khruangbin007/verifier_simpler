---
name: read-methodology
description: "Reads the canonical methodology into citable chunks with their full heading chain. Use as the first reading step of a review run."
metadata:
  version: "0.0.2"
  carried-out-by: "aiva1_documents.read_methodology"
---
## Purpose
Turn the methodology, whatever its format, into chunks under one contract: paragraph, table, figure, equation.

## Inputs
Files in Inputs/1_Methodology; references/tag_rules.yaml, overridden by Inputs/tag_rules.yaml.

## Outputs
chunks_canon; read_repairs; the outline preview. Sheet: Chunks_Canon.

## Procedure
1. Detect the format from the content. 2. Repair what must be repaired and record each repair. 3. Read blocks in document order. 4. Infer levels where nesting is flat. 5. Keep each table whole. 6. Read equation markup into linear notation and an expression tree. 7. Hash every chunk.

## Quality rules
- Every smallest piece of text in the file ends in one named class: kept in a unit, kept in a unit's other fields, read into another form, left out under a named rule, or reported as not read. What is in none of them is counted and located on Model_Package_Info.
- Nothing a unit shows may come from anywhere but the file or a transform named in the code.
A table is never split and never merged with its neighbours. A figure or equation that cannot be read is still a chunk. Reading order is stable.

## Never
- Never leave a piece of the file out of the account in silence. An open account is written down, and the run goes on.
Never execute or evaluate anything from an input. Never skip a block silently. Never keep a document-type declaration.
