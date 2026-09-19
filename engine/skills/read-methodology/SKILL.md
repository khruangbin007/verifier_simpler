---
name: read-methodology
description: "Reads the canonical methodology into citable chunks with their full heading chain. Use as the first reading step of a review run."
metadata:
  version: "0.0.3"
  carried-out-by: "aiva1_documents.read_methodology"
---
## Purpose
Turn the methodology, whatever its format, into chunks under one contract: paragraph, table, figure, equation.

## Inputs
Files in Inputs/1_Methodology; references/tag_rules.yaml, overridden by Inputs/tag_rules.yaml.

## Outputs
chunks_canon; read_repairs; content_accounts; shape_digests; the outline preview. Sheet: Chunks_Canon.

## Procedure
1. Detect the format from the content. 2. Repair what must be repaired and record each repair. 3. Work out what each tag of the file is for; where the built-in rules are unsure, ask what the shape of the file means and apply the answer under everything the rules already know. 4. Read blocks in document order. 5. Infer levels where nesting is flat. 6. Keep each table whole. 7. Read equation markup into linear notation and an expression tree. 8. Hash every chunk.

## Quality rules
- Every smallest piece of text in the file ends in one named class: kept in a unit, kept in a unit's other fields, read into another form, left out under a named rule, or reported as not read. What is in none of them is counted and located on Model_Package_Info.
- Nothing a unit shows may come from anywhere but the file or a transform named in the code.
- A heading names the block around it: it usually occurs about as often as that block, holds short text of its own, and opens it. A paragraph holds longer text and does not open the block around it. A tag that holds other tags is a container or a heading, never a paragraph: reading it as a paragraph would make the file say twice what it says once.
- Where the words of a file are already read correctly and only its shape is in doubt, change the shape and leave the words exactly where they are.
A table is never split and never merged with its neighbours. A figure or equation that cannot be read is still a chunk. Reading order is stable.

## Never
- Never leave a piece of the file out of the account in silence. An open account is written down, and the run goes on.
- Never write text of your own into an answer about a file's shape. Name only tags you were shown, and give only families from the list you were given. There is no way to tell the reader to skip a tag, and no answer may leave a word of the file out of a unit.
- Never overrule what a person wrote in Inputs/tag_rules.yaml, a schema AIVA already ships, or a table whose rows were counted. Speak where the reader guessed, and nowhere else.
Never execute or evaluate anything from an input. Never skip a block silently. Never keep a document-type declaration.
