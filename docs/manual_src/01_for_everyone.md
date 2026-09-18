# Part I. For everyone

## 1. What AIVA is and what it is not

AIVA, the AI Verification Assistant, helps a model validator with one question: **does the code of an R package do what the methodology says, and does the model documentation describe both truthfully?** It compares three things, called the three corners:

- **the methodology** (in the files: *canon*), the approved description of how the model must work;
- **the model package**, an R source tarball with code, stored parameter data, roxygen blocks, help pages, tests and vignettes;
- **the model documentation**, the developer's description of the package.

AIVA reads all three, cuts them into units, links what corresponds, checks formulas, values and stated rules by code, and raises everything it could not line up as a **flagged item** for a person to decide.

**An evidence pack, not a verdict.** A run produces `Output.xlsx`, `Validation_Report.docx` and an `_audit` folder from which every statement in the two files can be re-verified. A named person records a determination against every flagged item. AIVA never decides whether a model is acceptable.

**What AIVA does not do.** It does not run the model, does not execute any R code, does not judge whether the methodology itself is sound, and never treats the content of an image as evidence: a formula given only as a picture is raised for manual review, never skipped. Where the optional OCR package is installed, the words inside a picture are shown under it as a machine reading, to help a person find and judge it.

**The wording rule.** <!-- wording-policy-sentence -->AIVA rates nothing: words that grade seriousness (such as "severity", "critical", "major", "minor" or "high risk") and the policy terms "finding" and "error" never appear in anything AIVA produces, because grading and classifying are decisions of the validation policy and of people, not of a tool.<!-- end --> AIVA says what it observed, where, and what a sensible next step would be. A test scans the engine, the workbook and the report for these words on every build.

**The role of the language model.** A language model, reached through the `chat()` function of your organisation, answers narrow questions: which of these lettered passages does this unit correspond to, and how. Code proposes the passages, code validates every answer (letters, verbatim quotations, planted control passages), and code checks every linked formula and value again. The model's answer is never the last word where a deterministic check exists.

## 2. Design principles

| Rule | Statement |
|---|---|
| R1 | AIVA flags; people decide. No rating of seriousness. The policy terms never appear in anything AIVA produces or names. |
| R2 | Closed accounting. Every unit ends with one status; every unit that is not clean has a flagged item; this identity is checked on every run and a violation stops the run. |
| R3 | The model's opinion is never the last word. Answers are validated by code; linked formulas and values are checked deterministically; a failed or rejected call leaves the unit untraced and flagged and never stops a run. |
| R4 | Every link says how it was established, shows its evidence and carries provenance. Every citation can be re-verified by hash. |
| R5 | Everything except the model's answers is deterministic. Results never depend on thread timing. A run can be replayed from its recorded answers. |
| R6 | Inputs are never modified. A run writes only inside its own folder. |
| R7 | Nothing taken from an input or from the model is ever executed or evaluated: no R, no evaluation of text, no unpickling, no string parsing by SymPy, safe reading of archives, safe loading of YAML only. |
| R8 | The access token never persists: not in files, logs, manifests, workbooks or messages. |
| R9 | No domain concept in the engine, its vocabulary, its categories or its prompts. Domain flavour lives in sample data and in the optional glossary. |
| R10 | Plain language outward. No internal names, no technical traces, whole numbers shown as whole numbers, in anything an analyst reads. |
| R11 | Seven flat bundles, one-way imports, plain code, line budgets. The reading floor sits directly above the contracts: it imports the shared file and nothing else in the engine, and every step stands on it. |
| R12 | Workspace discipline: build on local disk, copy whole files, keep the file count small, sync after every step. |
| R13 | Reading conserves content. Every smallest piece of text in an input ends in exactly one named class: kept in a unit, kept elsewhere in a unit's fields, left out under a named rule, or reported as not read. Every character of a unit traces back to the input or to a named mark. Where the model helps decide how a file is sliced it chooses among options the code has already checked, and never supplies text. |

Which functions enforce which rule is listed in chapter 21; the list is generated from the docstrings.

## 3. Glossary

| Term | Meaning |
|---|---|
| Corner | One of the three things compared: methodology (canon), model package, model documentation. |
| Chunk | One unit of a document: a paragraph, a table, a figure or an equation. A table is always one chunk. References look like C-0012 (methodology) and D-0007 (documentation). |
| Model unit | One unit of the package: a function, a formula statement, a test block, a parameter table, a roxygen block, a help page and so on. References look like M-0024. |
| Formula statement | A statement inside a function that computes something, for example `b <- sqrt(rho) * qnorm(q)`. |
| Link | A recorded correspondence between two units, with its relation (for example *Implements*), how it was established and its evidence. |
| Candidate | A passage the deterministic search proposes for a unit, with a plain reason. Only the judge question can turn a candidate into a link. |
| Planted control passage | A passage that has nothing to do with the unit, shown among the candidates. An answer that accepts it is rejected. |
| Check | A deterministic comparison: of two formulas, of values, of a stated rule with the code, of a roxygen block with its function. |
| Status | The one final state of a unit; four statuses are clean and four need attention. |
| Flagged item | Something AIVA could not line up, raised for a person. It has a category and a suggested next step, and no rating. |
| Determination | A named person's recorded decision on a flagged item: *Requires action* or *No action needed*, with a rationale. |
| Ledger | The append-only, hash-chained record of all nodes and links. Its head is the *graph version id*. |
| Evidence pack | The run folder: the two output files and `_audit`. |
| Stand-in chat() | A deterministic test double shipped with AIVA for trying the process out and for tests. It is not a model. |
