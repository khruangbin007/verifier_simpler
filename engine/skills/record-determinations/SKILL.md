---
name: record-determinations
description: "Reads the yellow cells of the uploaded workbook and appends hash-chained determination records. Use after an upload."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva5_run_report.record_determinations"
---
## Purpose
An attributable, tamper-evident record of who decided what, when and why.

## Inputs
The uploaded workbook, recognised by its embedded identity under any file name.

## Outputs
determinations; uploads/. Columns: Status, Last decision recorded.

## Procedure
1. Archive the upload with its SHA-256. 2. Read by item id, never by row position. 3. Validate. 4. Append one record per changed item. 5. Rebuild both output files.

## Quality rules
Earlier determinations are never changed; a changed mind is a new record; a cleared decision is recorded as Withdrawn.

## Never
Never record an incomplete row. Never overwrite an unread workbook.
