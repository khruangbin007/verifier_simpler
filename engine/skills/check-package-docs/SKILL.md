---
name: check-package-docs
description: "Checks roxygen blocks and help pages against the code, without the language model. Use after read-package."
metadata:
  version: "0.0.1"
  carried-out-by: "aiva4_checks.check_package_docs"
---
## Purpose
In-package documentation hygiene.

## Inputs
model_units, package_info.

## Outputs
package_doc_checks. Column: Documentation consistency.

## Procedure
Arguments, defaults, exports, usage, page in step with its source, block present, examples parse.

## Quality rules
A missing block on a function that is not exported is not flagged.

## Never
Never run example code.
