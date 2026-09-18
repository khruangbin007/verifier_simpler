---
name: read-methodology
description: "Reads the canonical methodology into citable chunks with their full heading chain. Use as the first reading step of a review run."
metadata:
  version: "0.0.1"
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
A table is never split and never merged with its neighbours. A figure or equation that cannot be read is still a chunk. Reading order is stable.

## Never
Never execute or evaluate anything from an input. Never skip a block silently. Never keep a document-type declaration.
