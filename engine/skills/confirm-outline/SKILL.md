---
name: confirm-outline
description: "A person confirms that Level and Section on Chunks_Canon match the methodology's own outline. Use before any chat() call is spent."
metadata:
  version: "0.0.1"
  carried-out-by: "a person, in notebook cell 10"
---
## Purpose
Catch an unseen schema before the expensive steps.

## Inputs
Chunks_Canon and the outline preview.

## Outputs
The confirmation in run_manifest.

## Procedure
The reviewer compares the outline preview with the document's table of contents and runs cell 10.

## Quality rules
chat() steps refuse to start without it unless require_outline_confirmation is switched off.

## Never
Never confirm on a person's behalf.
