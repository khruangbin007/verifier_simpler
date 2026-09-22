# Verifier — the manual

**Version 0.0.2, September 2026.** One document for everyone: the person who runs a review, the person who reads its output, the person who reviews the code, and the person who maintains it. Part I is for everyone. Part II is for whoever runs a review. Part III is for whoever reads the code. Part IV is reference.

---

# Part I — For everyone

## 1. What the tool is, and what it is not

A model comes with three things: a **methodology** that says what it should do, a **package** of code and data that does it, and **documentation** that describes it. The tool reads all three, works out what corresponds to what, checks by code whether the things that correspond agree — formulas, values, stated rules — and raises what it could not line up as a question for a person.

It does not run the model. It does not judge whether the methodology is sound. It rates nothing: no grade, no score, no verdict. Every flagged item is an observation with its evidence and a suggested next step, and a person decides what it means. The person's decision is recorded beside the item, with who made it and when.

It is not tied to any sector. The methodology can be about anything the package computes. Nothing in the code, its vocabulary or its prompts assumes a field; what it knows about a project's language comes from the project's own files and, optionally, a glossary the analyst supplies.

**What comes out.** One run produces a folder with two deliverables and a record:

```
Run_2026-09-22_1430/
  Output.xlsx               eight sheets: what was read, what was linked, what was checked, what is flagged
  Validation_Report.docx    the same, as a report a person can read end to end
  _audit/
    records.jsonl           every record of the run, one per line
    calls.jsonl.gz          every exchange with the model
    manifest.json           the run's identity, its coverage account, the package as described
```

The record is what makes the run an **evidence pack**: from those three files alone, anyone can check that the inputs are the ones fingerprinted, that the code that ran is the code released, that every citation still points at the words it cites, and that nothing was edited afterwards.

## 2. How a review goes

1. **Put the files in.** A project folder has three input folders: the methodology, the package, the documentation. Almost any format works (section 6).
2. **Read.** The tool reads every file into small citable units — a paragraph, a table, a formula, a function — each with its place in the document and a fingerprint of its content. No model is involved yet. You are shown the outline it found and asked to confirm it.
3. **Link and check.** The tool finds, for each unit, the passages elsewhere that correspond to it, asks the model to choose among them and quote them, refuses any answer that does not quote the passage word for word, and then checks by code whether linked formulas, values and rules agree.
4. **Decide.** Every unit that could not be traced or that differs becomes a flagged item. You fill in your determinations in the workbook; the tool reads them back and records them.
5. **Keep.** The run folder is the evidence pack.

## 3. Design rules

Twelve rules were set at the start and one was added when reading was rebuilt. Each is enforced by named code, and a test holds each.

| Rule | Statement |
|---|---|
| R1 | The tool flags; people decide. No rating of seriousness. The policy terms never appear in anything the tool produces or names. |
| R2 | Closed accounting. Every unit ends with one status; every unit that is not clean has a flagged item; this identity is checked on every run. A file, a step or a call that fails is written down, and the run goes on. |
| R3 | The model's opinion is never the last word. Answers are validated by code; linked formulas and values are checked deterministically; a failed or rejected call leaves the unit untraced and flagged and never stops a run. |
| R4 | Every link says how it was established, shows its evidence and carries provenance. Every citation can be re-verified by hash. |
| R5 | Everything except the model's answers is deterministic. Results never depend on thread timing. A run can be replayed from its recorded answers. |
| R6 | Inputs are never modified. A run writes only inside its own folder. |
| R7 | Nothing taken from an input or from the model is ever executed or evaluated: no R, no evaluation of text, no unpickling, no string parsing by a symbolic library, safe reading of archives, safe loading of YAML only. |
| R8 | The access token never persists: not in files, logs, manifests, workbooks or messages. |
| R9 | No domain concept in the engine, its vocabulary, its categories or its prompts. Domain flavour lives in sample data and in the optional glossary. |
| R10 | Plain language outward. No internal names, no technical traces, whole numbers shown as whole numbers, in anything an analyst reads. |
| R11 | Five flat modules, one-way imports, plain code, line budgets. The notebook is built from code and never edited by hand. |
| R12 | Workspace discipline: build on local disk, copy whole files, keep the file count small, sync after every step. |
| R13 | Reading conserves content. Every smallest piece of text in an input ends in exactly one named class: kept in a unit, kept elsewhere in a unit's fields, read into another form, left out under a named rule, or reported as not read. Every character of a unit traces back to the input or to a named mark. Where the model helps decide how a file is sliced it chooses among options the code has already checked, and never supplies text. |

**The wording rule.** The tool rates nothing. Words that grade how serious something is, and the two policy terms that classify an observation, never appear in anything the tool produces, because grading and classifying are decisions of the validation policy and of people, not of a tool. The tool says what it observed, where, and what a sensible next step would be. The list of words lives in one place in `core.py`, and a test scans the engine, the workbook, the report and this manual for them on every build.

## 4. Vocabulary

Every word the tool can show in a status, a relation or a "how established" cell comes from one list in `core.py`. The tables are generated from it.

**Statuses that are clean**

| Wording |
|---|
| Traced to methodology |
| Supporting code (justified) |
| Unit test |
| Narrative - nothing to check |

**Statuses that need attention**

| Wording |
|---|
| Traced - differences flagged |
| Traced - check undecided |
| Not traced - for review |
| Not assessed - for manual review |

**Relations, as shown**

| Shown in the workbook | Word allowed in a prompt |
|---|---|
| Implements | implements |
| Partly implements | partly implements |
| Differs from | deviates from |
| Same topic (not implemented here) | merely related |
| Describes | describes |
| Consistent with | consistent with |
| Differs from | inconsistent with |

**How a link was established**

| Wording |
|---|
| Parsed from the files |
| AI judgement ({confidence}%) |
| Symbolic check: agrees |
| Numerical check: agrees ({n} points) |
| Numerical check: differs |
| Value check: agrees at stated precision |
| Value check: differs |
| Table matched by headers and row keys |
| Recorded by a person |

**Kinds of model unit**

| Wording |
|---|
| Function |
| Formula statement |
| Top-level statement |
| Test block |
| Parameter table |
| Parameter object |
| Roxygen block |
| Help page |
| Vignette text |
| Compiled code |
| File not read |
| Other file |

**Kinds of chunk**

| Wording |
|---|
| Paragraph |
| Table |
| Figure |
| Equation |

**Reasons for a check that could not be decided**

| Wording |
|---|
| the equation is an image |
| the equation could not be read |
| symbols could not be aligned |
| the function could not be composed |
| it uses operations the tool cannot evaluate |
| too few valid sample points |

**Reasons why an answer of the model could not be used**

| Wording |
|---|
| it could not be read |
| it named a passage that was not shown |
| it quoted words that are not in the text |
| it accepted a planted control passage |
| it contradicted itself |

**Fixed cell texts**

| Wording |
|---|
| Could not be decided |
| Not applicable |
| Not run yet |
| The AI's wording is not displayed here; the full text is in the audit records. |

---

# Part II — Running a review

## 5. The notebook, five cells

The notebook is `Verifier.ipynb`. It has five cells, each run in order the first time; cells 4 and 5 are run again as the review goes on.

| Cell | What it does | When to run it again |
|---|---|---|
| **cell 1** | Makes the widgets, installs the packages if any is missing (pinned to what the cluster already has), loads the engine, and reads the endpoint, token and user id from the widgets. | After anything restarts Python, and after pasting a fresh token. |
| **cell 2** | Your organisation's `chat()`, already filled in; it reads the endpoint, token and user id through `live()` each time it is called. Set `USE_STANDIN = True` to try the notebook without a model. Ends with a one-word self-test. | After changing `chat()`. |
| **cell 3** | Makes the project folder if it is new and says what to put where. Reads every input file, with no model involved, and shows the outline of the methodology and what each file was read as. | After adding or changing an input, or adding `Inputs/tag_rules.yaml`. |
| **cell 4** | The first time: records that you confirmed the outline and starts the model steps and the checks in the background. Every time after: shows where the run stands. `PAUSE` and `STOP` at the top do what they say. | To see progress; to pause or stop. |
| **cell 5** | After the run waits for a person: reads your determinations back from `Output.xlsx` and verifies the evidence pack. `APPENDIX` at the top runs a maintainer's check instead. | After every round of determinations. |

**The widgets.** Endpoint and token for the model gateway (01, 02); your user id (03), which is both the id sent to the gateway and the id recorded beside every decision you make; the model id (04); an existing project date and run to resume, or empty for new (05, 06); the Projects folder (07); the package index (08); concurrency and token cap (09, 10); a scratch folder, normally empty (11); and the subject of the documents (12), such as `financial`, which tells the model what kind of concepts to look for and names the concepts column after it.

**The token.** It is read at the moment `chat()` is called, never stored. When it runs out mid-run, cell 4 says the run is waiting for a fresh one: paste it into widget 02, run cell 1, and the run goes on. No question is repeated.

**Three ways to run the model steps.** Mode A (the default) runs them in a background thread and cell 4 shows progress. Mode C runs them in the foreground and stops by itself after `FOREGROUND_MINUTES`, so that a token can be renewed; run cell 4 again to continue.

## 6. What goes in

Three folders under `Inputs/`:

| Folder | What | Formats |
|---|---|---|
| `1_Methodology` | the canonical methodology | XML (also inside a `.txt`), `.mhtml`, `.docx`, `.pdf`, Markdown, `.csv`/`.tsv`, `.xlsx`, `.rtf`, `.tex`, `.svg` |
| `2_Model_Package` | the model | an R package as a `.tar.gz`, a `.zip` of it, or its source folder |
| `3_Model_Documentation` | the model documentation | as for the methodology; `.docx` preferred |

Folders inside a corner are read too, in name order. A Word lock file, `Thumbs.db` and a saved web page's support folder are left out and listed. A format the tool does not read — a slide deck, an old `.doc`, a picture on its own — becomes one row on `Model_Package_Info` saying so and what to save it as instead. Nothing is decoded as text that is not text.

**SVG pictures.** An SVG holds its text as text, so the tool reads a chart or a table drawn as a picture without guessing: every word comes from the picture's own `<text>` elements. Text that stands in a grid of at least two rows of the same width becomes a table, with the first row as its header; anything else becomes a figure whose words are the picture's labels in reading order. Where the methodology's XML refers to a picture beside it — `<figure src="floors.svg">` — that figure takes the picture's table or labels as its own, under the caption the XML gives. Only a picture in the same folder as the document, or a folder inside it, is followed; a missing picture or a path that leaves the folder stays a plain figure.

**Optional.** `Inputs/glossary.xlsx` names the project's own terms, so that the search for corresponding passages knows that two words mean one thing. `Inputs/tag_rules.yaml` tells the reader what the tags of an unfamiliar XML schema are for, and always wins over what the tool would work out.

**Only R is read as code.** A package in another language is said to be one, and its files are kept as running text that nothing can be linked to.

## 7. Reading `Output.xlsx`

Eight sheets, always in this order; a sheet whose step has not run yet shows its header only, and *Run progress* on the first sheet says where the run stands.

**How to read one row of a mapping sheet.** From left to right: what the unit is (blue identity columns and its text), what it was linked to in the methodology (green) and in the other corner, with the relation and **how the link was established**, then the assessment columns, then *Overall status* and the ids of its flagged items. Several values in one cell stand on separate lines, each prefixed with its reference. Text taken from your inputs or from the model is always shown in quotation marks with its citation.

**"How established"** starts with one of a small set of phrases: *Parsed from the files*; *AI judgement (64%)*; *Symbolic check: agrees*; *Numerical check: agrees (200 points)*; *Numerical check: differs*; *Value check: ...*; *Table matched by headers and row keys*; *Recorded by a person*. After an AI judgement you also see why the passage was proposed, for example "shares the words floor, probability; shares the rare number 0.0003".

**What "AI judgement (64%)" means.** The model chose this passage among lettered passages, quoted words from both sides that code found verbatim, and did not accept a planted control passage. The percentage is the model's own statement and is not calibrated; treat it as an ordering hint at most. Where a deterministic check exists for the link, the check's result follows in the same cell and has the last word.

**What was searched / Why not mapped.** Every unit without a link shows what the tool looked for (words, symbols, numbers) and what happened: nothing was proposed, the model saw only passages on the same topic, or its answer could not be used.

**The statuses.** The table is generated from the code:

**Units of the package** (the first rule that fits decides)

| Order | Rule | Status | When it applies |
|---|---|---|---|
| 1 | could not be read or assessed | Not assessed - for manual review | A file that could not be read, compiled code, or a stored object that is not compared. |
| 2 | test block | Unit test | A test_that block. Which function it tests is shown in the column Unit test. |
| 3 | package file without code | Supporting code (justified) | DESCRIPTION, NAMESPACE and other files that hold no code. |
| 4 | example code in a vignette | Supporting code (justified) | Code inside a vignette; it illustrates the package and is not part of the model. |
| 5 | its own checks | Traced - differences flagged / Traced - check undecided | A roxygen block or help page whose own deterministic checks differ or are undecided. |
| 6 | documents no single object | Supporting code (justified) | A roxygen block or help page that documents no single object of the package. |
| 7 | takes the tracing of what it documents | the status of the documented object | A roxygen block or help page whose own checks pass. |
| 8 | a check or the judge reports a difference | Traced - differences flagged | Linked, and a check, the judge or the second question reports a difference. |
| 9 | a required check is undecided | Traced - check undecided | Linked, and a required check could not be decided. |
| 10 | linked and all required checks agree | Traced to methodology | Linked to the methodology, and every required check agrees. |
| 11 | covered by the check of the whole function | Traced to methodology | A statement without a link of its own, inside a function whose agreeing check ran through it. |
| 12 | supporting code by syntax | Supporting code (justified) | No link, and no arithmetic and no number other than the trivial ones; the reason is shown. |
| 13 | vignette prose without checkable statements | Supporting code (justified) | Vignette text that states no number and no formula. |
| 14 | not linked | Not traced - for review | Anything else without a link to the methodology. |

**Units of the documentation** (the first rule that fits decides)

| Order | Rule | Status | When it applies |
|---|---|---|---|
| 1 | content cannot be read | Not assessed - for manual review | A figure, an equation that could not be read, or a part of a file that could not be read. |
| 2 | states nothing checkable | Narrative - nothing to check | No formula, number, rule or definition, by code or by the judge's answer. |
| 3 | a check or the judge reports a difference | Traced - differences flagged | Linked, and a check, the judge or the second question reports a difference. |
| 4 | a required check is undecided | Traced - check undecided | Linked, and a required check could not be decided. |
| 5 | linked and consistent | Traced to methodology | Linked to the methodology, directly or through a linked unit of the package, and consistent. |
| 6 | checkable and not linked | Not traced - for review | States something checkable, and nothing was linked to it. |

Clean statuses: *Traced to methodology*, *Supporting code (justified)*, *Unit test*, *Narrative - nothing to check*. The other four need attention, and every unit with one of them is named by at least one row of `Flagged_Items`. `Mapping_Coverage` counts the same statuses; its numbers equal what you get by filtering *Overall status* on the two mapping sheets, and the tool stops a run in which they would not.

**The value-comparison rule** is one rule, used for parameter tables, numbers in code, numbers in roxygen text and numbers in the documentation. Its full text is on `Model_Package_Info`. In short: percent, basis points and scientific notation are converted first; a value agrees at stated precision when rounding it to the decimals of the methodology's value gives that value; there is no hidden tolerance. A cell reads like "package 0.10, methodology 0.15 (C-0017 row Retail): differs".

**The mathematical check.** For a linked function or statement and a passage that states a formula, the tool aligns the symbols first (shown as "with rho = ρ"), then tries to show symbolically that both sides are equal, then evaluates both at 200 seeded points, including points at and around every threshold. *Differs* always comes with a counterexample: the inputs and both results. *Could not be decided* names one reason from a fixed list and is never clean.

**How to read a path.** *What was observed* on `Flagged_Items` ends with the supporting path, hop by hop: the unit, the function it sits in, the table it reads, the passage it corresponds to with how that was established, the roxygen block and documentation passage that describe it.

**The sheets and columns.** As laid out in the one place that defines them, `runner.WORKBOOK_LAYOUT_YAML`:

**Model_Package_Info**

| Column | Colour group | What it shows |
|---|---|---|
| Group | identity |  |
| Item | identity |  |
| Value | assessments |  |

**Chunks_Canon**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity |  |
| Level | identity |  |
| Section (heading chain) | identity |  |
| Para no. | identity |  |
| Type | identity |  |
| Text | methodology |  |
| Source file | identity |  |
| Cross-references | methodology |  |
| Reading note | assessments |  |

**Chunks_Doc**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity |  |
| Level | identity |  |
| Section (heading chain) | identity |  |
| Para no. | identity |  |
| Type | identity |  |
| Text | documentation |  |
| Source file | identity |  |
| Cross-references | documentation |  |
| States something checkable | assessments |  |
| Reading note | assessments |  |

**Chunks_Model**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity |  |
| Kind | identity |  |
| File | identity |  |
| Lines | identity |  |
| Name | identity |  |
| Inside | identity |  |
| Text | code text |  |
| LLM Interpretation | assessments |  |
| Expression / arguments | code text |  |
| Numbers used | code text |  |
| Exported | identity |  |
| Reading note | assessments |  |

**Mapping_Model_to_Canon_and_Doc**

| Column | Colour group | What it shows |
|---|---|---|
| Model ref | identity |  |
| Kind | identity |  |
| Name | identity |  |
| File and lines | identity |  |
| Code text | code text |  |
| Canon ref(s) | methodology |  |
| Relation (canon) | methodology |  |
| How established (canon) | methodology |  |
| What was searched (canon) | methodology |  |
| Why not mapped (canon) | methodology |  |
| Canon text | methodology |  |
| Doc ref(s) | documentation |  |
| Relation (doc) | documentation |  |
| How established (doc) | documentation |  |
| What was searched (doc) | documentation |  |
| Why not mapped (doc) | documentation |  |
| Doc text | documentation |  |
| Math check | assessments | Result of comparing the unit's formula with every linked formula: the aligned symbols, then agrees, differs with a counterexample, or could not be decided with its reason. |
| Parameter completeness | assessments | For a stored table: the cell-by-cell comparison with the linked table. For code: which symbol of the formula each code symbol stands for. |
| Logic consistency | assessments | Floors, caps and thresholds stated in linked passages, and whether the code applies them. On the documentation sheet: the judged relations. |
| Documentation consistency | assessments | Results of the checks of the roxygen block and help page, and where the model documentation describes the unit. |
| Hard-coded numbers | assessments | Every non-trivial number in the code, and where the linked passages state it. |
| Unit test | assessments | Which test block calls the function. For information only; it never raises an item. |
| Quality notes (AI) | assessments | Text written by the model, labelled as such and filtered. |
| Overall status | assessments | The one final status of the unit (the statuses are listed in this section). |
| Flagged item(s) | assessments | Ids of the rows on Flagged_Items that name this unit. |

**Mapping_Doc_to_Canon_and_Model**

| Column | Colour group | What it shows |
|---|---|---|
| Doc ref | identity |  |
| Type | identity |  |
| Section (heading chain) | identity |  |
| Doc text | documentation |  |
| Canon ref(s) | methodology |  |
| Relation (canon) | methodology |  |
| How established (canon) | methodology |  |
| What was searched (canon) | methodology |  |
| Why not mapped (canon) | methodology |  |
| Canon text | methodology |  |
| Model ref(s) | code text |  |
| Relation (model) | code text |  |
| How established (model) | code text |  |
| Model text | code text |  |
| Value check | assessments | Numbers and tables of the documentation compared with the methodology under the value rule. |
| Math check | assessments | Result of comparing the unit's formula with every linked formula: the aligned symbols, then agrees, differs with a counterexample, or could not be decided with its reason. |
| Logic consistency | assessments | Floors, caps and thresholds stated in linked passages, and whether the code applies them. On the documentation sheet: the judged relations. |
| Parameter note (AI) | assessments | A column mapping or symbol alignment proposed by the model, where one was asked for. |
| Documentation quality notes | assessments | Deterministic notes: references that resolve to nothing, reconstructed numbering, unreadable parts, repeated paragraphs. |
| Overall status | assessments | The one final status of the unit (the statuses are listed in this section). |
| Flagged item(s) | assessments | Ids of the rows on Flagged_Items that name this unit. |

**Mapping_Coverage**

| Column | Colour group | What it shows |
|---|---|---|
| Corner | identity |  |
| Units in total | identity |  |
| Traced to methodology | assessments |  |
| Supporting code (justified) | assessments |  |
| Unit test | assessments | Which test block calls the function. For information only; it never raises an item. |
| Narrative - nothing to check | assessments |  |
| Traced - differences flagged | assessments |  |
| Traced - check undecided | assessments |  |
| Not traced - for review | assessments |  |
| Not assessed - for manual review | assessments |  |
| Needs attention | assessments |  |
| How to read this row | identity |  |

**Flagged_Items**

| Column | Colour group | What it shows |
|---|---|---|
| Item id | identity |  |
| Concerns | identity |  |
| Category | identity |  |
| Unit ref(s) | identity |  |
| Item | assessments |  |
| What was observed | assessments |  |
| Methodology says | methodology |  |
| Code does | code text |  |
| Documentation says | documentation |  |
| Suggested next step | assessments |  |
| Status | assessments |  |
| Last decision recorded | assessments |  |
| Decision | reviewer input |  |
| Reviewer | reviewer input |  |
| Role | reviewer input |  |
| Rationale | reviewer input |  |

## 8. Confirming the outline, and choosing what is in scope

The reading steps run before any model call is spent, and cell 3 shows the outline of the methodology as it was read: every heading at its depth. Check it against the document's own table of contents. Where the tool read a file whose shape it did not know, `Model_Package_Info` says which tag was read as what and why, and what the built-in rules would have done instead. Read those rows before confirming.

**Choosing what is in scope.** Each of the three sheets `Chunks_Canon`, `Chunks_Doc` and `Chunks_Model` has a yellow column, **Use in review**, with a drop-down of two words: *to use* and *to not use*. An empty cell means *to use*. Mark *to not use* on anything that should not be reviewed — a cover page, a table of contents, a disclaimer, a helper file of the package — then save the workbook back into the run folder under its own name. When cell 4 is run it reads that column back, by unit reference and never by row position, and records each decision with your id in a hash chain. A unit marked *to not use* is not searched, not linked, not a link target, not interpreted and not checked; it ends with the status **Not in scope (a person's decision)**, which counts as clean and raises no flagged item, and it is still listed, so that what was left out stays visible. Anything else written in the column is ignored and cell 4 says so.

Then set `OUTLINE_CONFIRMED = True` at the top of cell 4 and run it; the confirmation is recorded with your id.

## 8a. Concepts

**The model is the basis.** A concept is one of the model's: a name its code gives something — a function, an argument, a variable a statement sets, a stored table or one of its columns — together with how the model's own roxygen and help pages describe it, word for word (`pd`, described by its `@param` as *probability of default*). Names the code only calls, such as base functions, and generic names such as `x`, `data` or `result`, are not concepts.

**The documents are searched for those, and nothing else.** A term of the methodology or the documentation is extracted only when it has a likely equivalent in the model; a term with none is never extracted, however important it looks. Three kinds of evidence, kept apart:

1. **The same words, found by code** (step 06, `extract-concepts`, in cell 3, before any model call): the words of the model's name (`asset_correlation` in *asset correlation*), or the words the model uses to describe it (*probability of default*), compared in lower case and singular, with only spaces, hyphens or underscores between them. Where the documents define an acronym — *stand-alone credit profile (SACP)*, or a glossary entry written as its own heading — and one side of it is already one of the model's forms, the other side becomes one too, with the unit that defines it.
2. **The rest of the model**: other model files that write a concept's name — a test, a vignette, a help page — found the same way.
3. **Candidate synonyms and acronyms, guessed by the model** (step 07b, `judge-concepts`, after you confirm the outline): only for methodology and documentation units where code sees a likely model concept it could not prove — a name whose parts begin the unit's words (`adj_rating`, *adjusted rating*), an acronym-like name spelled by the initials of words in a row, a description sharing its words. The model is shown those concepts and asked which the unit names, copying the unit's words; a name not in the unit word for word refuses the whole answer.

**Verbatim, always.** The Chunks sheets' column **Extracted concepts with candidate equivalent in model** (*Extracted financial concepts with candidate equivalent in model* when widget 12 is `financial`) shows, for each unit, the words that unit writes, character for character — *PD*, not the model's `pd`; *PDc* as the text capitalises it — joined by `;`. It never shows the model's name for them. That mapping, and every guess in it, is on the sheet **Concepts** only: one row per model concept, with the names the code gives it, how the model describes it, the same words found in the methodology, the documentation and the rest of the model, and — in a column of their own, headed as the AI's guess — the synonyms and acronyms the model found, each as written and with its units.

**How concepts steer the mapping.** The search for corresponding passages (step 07c) runs after the concepts, and a passage that names the same model concept as the unit comes first: that signal counts `concept_weight` times as much as any other and is the first to fill the places reserved on each shortlist. The reason shown for such a candidate begins *shares the concept*.

## 9. Working through `Flagged_Items`

1. Download `Output.xlsx` from `the run folder`.
2. On `Flagged_Items`, fill the four **yellow** columns for the items you decide: *Decision* (`Requires action` or `No action needed`; capital letters do not matter), *Reviewer*, *Role* and *Rationale*. A decision without all three other cells is reported back and not recorded. You may sort and filter; the tool finds rows by *Item id*, never by position. Anything typed outside the yellow columns is ignored.
3. Upload the workbook into the same `the run folder` folder, under any name. The tool recognises it by the identity stored inside the file, keeps a copy of exactly what you uploaded in `_audit/uploads/`, and refuses in plain words a workbook of another run or a file in the old `.xls` format.
4. Run `cell 5`. It says what was recorded and what was incomplete, and rebuilds both output files. `the run folder` again holds exactly two files.

What is recorded for every determination: item id, decision, reviewer, role, rationale, the time, the reviewer id of whoever ran the cell, and the SHA-256 of the uploaded workbook. Records are only ever added. Changing a decision adds a record; clearing one adds a record with the decision *Withdrawn* and the item is *Open* again. The records form a hash chain whose head appears as the *Determinations record fingerprint* on `Model_Package_Info` and on the first page of the report.

A workbook you have edited and uploaded is never overwritten before it has been read in.

## 10. Reading `Validation_Report.docx`

The report says what was reviewed, how, and what is open, in the order a reader needs: the scope, the inputs and their fingerprints, what was read and how much of it, the coverage identity, then every flagged item with its evidence and its determination if one has been recorded. A person who has never opened the workbook can read the report alone. It is rebuilt after every step, so it always matches the workbook.

## 11. The run folder as an evidence pack

The three files in `_audit/` are the record. `records.jsonl` holds every record of every kind, one per line, each tagged with its kind, in the order written and never rewritten; `calls.jsonl.gz` holds every exchange with the model, prompt and reply; `manifest.json` holds the run's identity, the fingerprint of every input, the fingerprint of every engine file that ran, the coverage account and the package as described. Cell 5 verifies a pack from these three files alone: that the inputs are the ones fingerprinted, that the engine files match the release, that re-reading the inputs gives the recorded content hashes, that both hash chains (the graph and the determinations) verify, that every unit has one status and every citation resolves, and that no token was written anywhere. A changed byte in an input, a removed record or an edited status is caught.

## 12. When something goes wrong

| What you see | What it means and what to do |
|---|---|
| "Your notebook session has crashed" right after `cell 3`, with *compiled using NumPy 1.x cannot be run in NumPy 2* or *PyArrow must be installed* in the output | An install moved a package the runtime needs to start, so every restart crashes. Detach the notebook from the cluster and attach it again: that discards what `cell 3` installed, and only this notebook was affected. Do not restart the cluster for this. Then run `cell 2` onwards again. Since 21 September 2026 `cell 3` keeps the runtime's own numpy, pandas, pyarrow and scipy exactly as they are, and checks before restarting that they still import together, so this should not happen again; if it does, tell whoever maintains the tool. |
| `cell 3` says "STOPPED BEFORE RESTARTING PYTHON" | The install changed something the runtime needs to start, and `cell 3` noticed before restarting, so the session is still alive. Detach the notebook and attach it again to undo the install, and tell whoever maintains the tool which package pip named. |
| `cell 3` says pip could not find versions that fit | The index has no version of a package the tool needs that works with this runtime's own packages. Nothing was changed. Ask for an older version of the package pip names to be added to the index. |
| The status cell says the run waits for a fresh token | The token ran out. Paste a new one (mode B: then run `cell 1`). No question is repeated. |
| "The time box of this foreground run is over" | Mode C stopped by itself. Paste a fresh token and run `cell 4` again. |
| "Many calls in a row failed, so the run paused itself" | The gateway is not answering. Check it with `cell 2`, then run `cell 4` again. |
| The cluster stopped | Start it, run `cell 1` to `cell 3` in order, choose the same run in the run widget, and run `cell 4`. The run resumes after its last finished step. |
| An input changed | Start a **new run** in the same project. `Model_Package_Info` lists what changed since the previous run. Never edit inputs of a run that has started. |
| A unit of kind *File not read* | That file or expression could not be parsed. It has a flagged item with the reason; the rest of the package was still read. |
| "... belongs to another run or another list of items" | The uploaded workbook is not this run's `Output.xlsx`. Download the current one and fill it again. |
| A cell reads "This text could not be shown in plain words" | The tool withheld a text that contained technical traces; the text is in `_audit/run_log.txt`. Please report it; it is a defect in the tool. |
| "This is a defect in the tool, not in the model under review" | The coverage identity did not hold and the run stopped on purpose. Keep the run folder and report it. |

## 13. Known limitations

- The content of images is never evidence. Formulas given only as pictures end *Not assessed* or make the linked code *Traced - check undecided*. Where the optional OCR package is installed, the words inside a picture are shown under it, headed *Words read from the picture by OCR*; a machine misreads digits, so check them against the picture itself. The Figure still ends *Not assessed - for manual review*.
- **LLM Interpretation** on `Chunks_Model` says in plain words what a function, a formula statement, a top-level statement or a test block does. The AI is shown the piece itself together with where it sits in the whole package: the function a statement is inside, the package's own documentation of it, what calls it, what it calls, the stored data it reads, and an outline of every file. The words are the model's, so the cell shows them in quotation marks. They are an aid to reading and nothing more: an interpretation gives a unit no status, raises no flagged item, and is never used in a check. The tool only accepts an answer whose quotation is in the code word for word; where an answer could not be used the cell says why. Other kinds of unit (documentation blocks, help pages, stored data) are not asked about.
- **Para no.** shows the paragraph number the document itself gives (`36.`), gaps included, where it gives one. A PDF gives none, so its paragraphs are labelled with their page and their place on it (`p.4 ¶2`); so are the paragraphs of a Word file in which Word noted where its pages ended. Otherwise it is the tool's own count under the heading.
- The items of a list are shown inside the paragraph that introduces them, each on its own line behind `- ` or its number, and are not rows of their own. A list under a heading, with no paragraph before it, keeps its items as rows.
- A table of sentences is shown with each cell on its own line under the heading of its column (`Very Strong: ...`); a table of short values is shown as a grid, cells joined by `; `.
- Page headers, page footers and logos that repeat in the margins of a PDF are left out, and `Model_Package_Info` lists every one that was.
- A reading guided by the model (`agentic_reading: rules`) can put a statement under the wrong heading. It cannot lose a word or add one: every answer is a choice among tags the tool showed it and families from a fixed list, and the content account on `Model_Package_Info` balances whatever the answer says. Check the changed rows at cell 4 before confirming the outline.
- A run with `agentic_reading` on is reproducible from its recorded answers, and two fresh runs on the same inputs may cut a file it is unsure of differently. The reading notes say which files were read that way.
- the tool reads XML (also inside a `.txt`), `.mhtml`, `.docx`, `.pdf`, Markdown, `.csv` and `.tsv`, `.xlsx`, `.rtf` and `.tex`. It does not read slide decks, OpenDocument files, e-books, old Office files (`.doc`, `.xls`, `.ppt`) or pictures on their own; each of those becomes one row on the sheet saying so, with what to save it as instead. Folders inside an Inputs corner are read, in name order; a Word lock file, Thumbs.db and a saved web page's support folder are left out and listed on `Model_Package_Info`.
- A spreadsheet is read sheet by sheet, each sheet a heading over one table. A formula is never worked out: the value the spreadsheet saved with it is what is read, so save the workbook after it has calculated.
- The model package may be a tarball, a `.zip` of it, or its source folder. Only R is read as code: a package in another language is said to be one, and its files are kept as running text that nothing can be linked to.
- PDF input is read by position on the page; multi-column layouts and tables without ruling lines may be cut wrongly. Check the outline.
- R code is parsed by the tool's own reader, not by R. Unusual syntax becomes a *File not read* unit for that expression only. Functions with loops or branches are compared statement by statement; R semantics that the tool's evaluator does not cover (recycling of vectors, matrix products) end as "uses operations the tool cannot evaluate".
- Stored data is decoded without R. Objects that are not tables, vectors or short lists are described and not compared; missing values of different kinds are not told apart.
- The percentage after "AI judgement" is not calibrated.
- The evaluation so far used invented sample projects and the stand-in `chat()`; results with a real model on a real package are still to be measured (section 22).

---

# Part III — For whoever reads the code

## 14. The five modules

The engine is five flat files, imported in one direction: `core` imports nothing of the engine; `reading` imports `core`; `review` imports `core` and `reading`; `runner` imports all three; `develop` imports whatever it measures. Each opens with the same five-part overview (what it does, what it takes in and produces, which sheets show its results, which design rules it enforces, and how to sanity-check it). Read the overview first; it was written to be read before the code.

| Module | What it holds | Reviewer |
|---|---|---|
| `core.py` | the record contracts and vocabulary; the machinery for asking the model and validating an answer; the baseline decisions about a document's shape; the content account; the shape digest; what a file is; which files of a folder are documents; the converters for spreadsheets, Markdown, delimited rows, RTF and LaTeX | everyone |
| `reading.py` | the methodology and the documentation into units; the package into functions, formula statements, objects, data tables, help pages and vignettes; the guided reading of an unfamiliar file | 1 and 2 |
| `review.py` | the graph; the search for corresponding passages; the judged links; the interpretation of code; the checks of formulas, values, rules and package documentation; statuses, flagged items and the coverage identity | 3 and 4 |
| `runner.py` | the run folder and its record; the wrapper around `chat()`; the pipeline; the workbook and the report; the determinations; the verification of a pack | 5 |
| `develop.py` | the measurements, the release manifest, the check of this manual against the code, the notebook | the maintainer |

**How to review a module.** Read its overview. Run the tests it names. Run the sanity check it names and look at the sheet. Then read the functions in the order the overview lists them, checking each docstring's `Enforces:` line against the rule table in section 3.

## 15. The pipeline

`engine/pipeline.yaml` names eighteen steps, in order, each with a version and the function that carries it out (`carried_out_by`). Only functions in `runner.STEP_FUNCTIONS` may be named; `runner.load_pipeline` refuses anything else, and refuses a step with no version. A step's version is part of the provenance of every record it writes.

| Step | Name | Carried out by |
|---|---|---|
| 01 | prepare-run | `runner.prepare_run`: fingerprints every input |
| 02 | read-methodology | `reading.read_methodology` |
| 03 | read-documentation | `reading.read_documentation` |
| 04 | read-package | `reading.read_package` |
| 05 | build-graph | `review.build_graph`: every unit a node |
| 06 | extract-concepts | `review.extract_concepts`: the model's concepts, and where the documents write them in the same words |
| 07c, 09 | find-candidates | `review.find_candidates`, two passes; shared concepts first |
| 07 | confirm-outline | a person, in cell 4 |
| 07a | interpret-code | `review.interpret_code` |
| 07b | judge-concepts | `review.judge_concepts`: the model's guesses of synonyms and acronyms, kept apart |
| 08, 10 | judge-links | `review.judge_links`, two passes |
| 11 | check-mathematics | `review.check_mathematics` |
| 12 | check-values | `review.check_values` |
| 13 | check-rules | `review.check_rules` |
| 14 | check-package-docs | `review.check_package_docs` |
| 15 | account-coverage | `review.account_coverage`: the identity |
| 16 | await-determinations | a person, in the workbook |
| 17 | record-determinations | `runner.record_determinations` |
| 18 | build-report | `runner.build_report` |

The steps that ask the model are `read-methodology`, `read-documentation` and `read-package` (only where a file's shape is in doubt and `agentic_reading` is on), `interpret-code`, `judge-concepts`, `judge-links`, `check-mathematics`, `check-values` and `check-rules`. Every other step is code alone.

## 16. How the model is used, and held

The model is asked questions whose answers are **choices among things code has already decided to show**: which of these lettered passages corresponds, quoting words from each; what this function does, in plain words; which reader should take this file; what this tag is for. Every answer is validated by `review.validate_answer` before anything is done with it: a quotation that is not word for word in the passage, a reference to a passage that was not shown, a planted control passage accepted, a self-contradiction — each is a refusal, and a refusal leaves the unit untraced and flagged. Nothing is repaired. A refused, failed or absent answer never stops a run and never changes an input.

Every exchange is recorded, and `runner.replay_chat` answers from the record, so that a run can be reproduced without a model and its graph version compared.

**Guided reading.** Where the built-in rules cannot tell what a file's tags are for, and `agentic_reading` is not `off`, the reader asks one question about the file's *shape* — a digest of its tags, never the file — and the answer names a family for each tag from a fixed list of five. The model cannot name a tag it was not shown, cannot ask for a tag to be skipped, and cannot overrule the analyst, the shipped rules or a table whose rows were counted. It speaks only where the reader guessed. The same holds for a package member the built-in tests give no reader: one question chooses which existing reader takes it, and there is no reader that means skip. `core.validate_slice_rules` and `core.validate_package_plan` hold these lines; `core.account` proves afterwards that no word was lost or added.

## 17. Reading, and the content account

Every file read keeps a **content account** (`core.account`). The file's smallest pieces of text are counted straight from its bytes — not from what the reader made of it — and each must end in one of five classes: in a unit's text; relocated into another field of a unit (a heading carried onto the units below it, a caption, the cells of a table); rewritten into another form (an equation into linear notation); left out under a named rule (page furniture, an attribute the rules do not read, a comment); or reported as not read. What is in none of them is counted and located on `Model_Package_Info`. In the other direction, every piece of text a unit shows must come from the file or from a transform named in the code (`core.DECLARED_MARKS`); anything else is reported as added. An account that will not close is written down and the run goes on.

## 18. Tests and sample projects

`engine/tests/` holds the tests, all offline, run with `python -m unittest discover engine/tests`. Seven sample projects under `engine/tests/sample_projects/` are built from source by `engine/tests/build_samples.py`, byte for byte the same on every build: four settled ones with gold links and gold clean units, and three built to be read badly — an XML schema unlike any the rules know, a two-column PDF with running headers and a footnote, a Word file with bold-only headings, a text box and tracked changes. `engine/tests/frozen/` holds a snapshot of every unit the four settled samples produce, so that a change to reading shows as a diff; `REFRESHED.md` beside it records every deliberate refresh and why.

---

# Part IV — Reference

## 19. Settings

Settings are an allow-list: a name that is not in this table is refused. The notebook sets the concurrency limit, the token cap, the reviewer id and the reviewer role from its widgets.

| Setting | Default | Meaning |
|---|---|---|
| `k_candidates` | 12 | How many passages are shown to the judge for one unit and corner. |
| `concurrency_limit` | 4 | How many questions are asked at the same time. |
| `token_cap` | 40000 | The gateway's limit for one call, in tokens. |
| `answer_reserve` | 1500 | Tokens kept free for the answer. |
| `thinking_reserve` | 0 | Tokens kept free for a model that writes out its reasoning first. |
| `safety_margin` | 0.15 | Share of the remaining room left unused, because tokens are estimated. |
| `prompt_target_tokens` | 6000 | The size a prompt should stay below even when the cap allows more. |
| `max_attempts` | 3 | Attempts per question before it ends as failed. |
| `breaker_after_failures` | 8 | Failed calls in a row after which the run pauses itself. |
| `retry_wait_seconds` | 2.0 | Waiting time before a retry; it grows with every attempt. |
| `token_lifetime_minutes` | 14.0 | Age at which a token is treated as run out and a fresh one is awaited. |
| `token_wait` | wait | wait: workers wait for a fresh token (modes A and B). stop: the run stops and is resumed (mode C). |
| `foreground_minutes` | 0.0 | Time box of a foreground run; 0 means none. |
| `sync_every_calls` | 100 | Call records are written and copied to the Workspace after this many questions. |
| `llm_file_roll_mb` | 25.0 | Size at which a new file of call records is started. |
| `require_outline_confirmation` | True | The AI steps wait until a person has confirmed the outline of the methodology. |
| `second_opinion` | unchecked_only | When the second, oppositely framed question is asked: unchecked_only, all or none. |
| `judge_supporting_code` | False | Also send supporting code by syntax to the search and the judge. |
| `max_parameter_cells` | 5000 | A stored object with more cells is profiled and not compared. |
| `max_parameter_columns` | 50 | A stored object with more columns is profiled and not compared. |
| `protect_sheets` | True | Lock every cell except the yellow ones (filtering stays allowed; no password). |
| `system_prompt_prefix` |  | Text put in front of every system prompt, for example a switch that turns written-out reasoning off. |
| `strip_patterns` | ['(?s)<think>.*?</think>', '(?s)<thought>.*?</thought>', '(?s)<\\/channel\\/>thought.*?<\\/channel\\/>'] | Patterns of thought blocks that are removed from an answer before it is read. |
| `numeric_points` | 200 | Sample points of the numerical check. |
| `numeric_seed` | 20260917 | The seed of the sample points; recorded in every check. |
| `min_valid_points` | 50 | Fewer valid points than this leave a check undecided. |
| `relative_tolerance` | 1e-09 | Two results agree when they differ by less than this, relative to their size. |
| `trivial_numbers` | ['0', '1', '2', '-1', '10', '100'] | Numbers that are not looked up in the methodology. |
| `bm25_k1` | 1.2 | Text ranking: how fast repeated words stop counting. |
| `bm25_b` | 0.75 | Text ranking: how much long passages are scaled down. |
| `anchor_max_share` | 0.1 | An anchor that more than this share of all units mention is dropped. |
| `walk_restart` | 0.25 | Restart probability of the walk over units and anchors. |
| `walk_rounds` | 30 | Rounds of the walk; fixed, so that it is deterministic. |
| `heading_anchor_cap` | 0.5 | The most a shared section title can weigh. |
| `rrf_constant` | 60 | The constant of reciprocal rank fusion. |
| `reserved_places` | 2 | Places of the shortlist kept for candidates that only the anchors or propagation found. |
| `max_unit_chars` | 3000 | A longer unit is cut around its formula lines before it is shown to the model. |
| `max_passage_chars` | 1100 | A longer passage is cut around the matched words. |
| `max_file_mb` | 200.0 | A larger input file is not read and becomes a not-read unit. |
| `reviewer_id` |  | Who runs the notebook; recorded with confirmations and determinations. |
| `reviewer_role` |  | The role of that person. |
| `read_pictures` | True | Read the words inside pictures by OCR when the optional package rapidocr-onnxruntime is installed. The words are shown under the Figure as a machine reading; a Figure still ends for manual review. |
| `interpret_code` | True | Ask the AI to say in plain words what each function, formula statement, top-level statement and test block does, shown with where it sits in the whole package. Fills the column LLM Interpretation on Chunks_Model. One question per piece of code; switch it off to save the calls. |
| `agentic_reading` | off | Whether a reading step may ask the model what the tags of a file whose shape the tool does not know are for. "off" asks nothing and reads as the built-in rules read; "rules" asks one question per file the rules are unsure about and applies the answer under everything the rules already know. |
| `signals` | ['fields', 'bridge', 'references', 'anchors', 'signatures', 'propagation'] | The search signals in use; the recall ladder (`develop.recall`) switches them off one by one. |

`concept_subject` (default empty): the subject of the documents, from widget 12; it tells the model what kind of concepts to look for and names the concepts column. `concept_weight` (default 2.0): how much more a shared concept counts in the search than any other signal. `concept_batch` (default 8): how many units one extraction question shows the model. `concept_candidates_max` (default 40): the most model concepts shown to the model in one question, and the most suggested for one unit. `concepts_with_ai` (default true): whether the model is asked for synonyms and acronyms code could not prove; switched off, only what code proved stands.

`agentic_reading` (default `off`): whether a reading step may ask the model what the tags of a file whose shape the tool does not know are for. `off` asks nothing; `rules` asks one question per file the rules are unsure about. The sign-off bar for turning it on is `develop.run`, run from cell 5 with `APPENDIX = "sign-off"`; it changes no setting.

## 20. Categories and decision words

**Concerns:** Model code, Parameter data, Package documentation, Model documentation.

| Category | Suggested next step, as shown |
|---|---|
| Code differs from methodology | Compare the code with the cited passage, starting from the inputs shown under What was observed. |
| Code not traced to methodology | Decide whether this code implements a part of the methodology; if so, name the passage. |
| Mathematical check undecided | Compare the formula in the code with the cited passage by hand; the tool could not decide it. |
| Value differs from methodology | Compare the listed rows of the package table with the cited table of the methodology. |
| Hard-coded number not traced | Find where the methodology states this number, or confirm that it needs no statement. |
| Parameter data not traced | Decide which table of the methodology this stored object corresponds to, if any. |
| Parameter data not described | Check whether the stored object and each of its columns should be described in the package. |
| Package documentation differs from code | Compare the roxygen block or help page with the function it documents. |
| Package documentation differs from methodology | Compare the value stated in the package documentation with the cited passage. |
| Documentation statement not traced | Decide which passage of the methodology this statement of the documentation rests on, if any. |
| Documentation differs from methodology | Compare the statement in the documentation with the cited passage of the methodology. |
| Documentation differs from code | Compare the statement in the documentation with the cited unit of the package. |
| Item could not be read or assessed | Review this item by hand; the tool could not read or assess it. |
| AI answer could not be used | Review this unit by hand, or run the tool again; the AI's answer could not be used. |
| AI answers disagree | Read both quotations and decide whether the unit and the passage state the same thing. |

**Decision words:** *Requires action*, *No action needed*. A cleared decision is recorded as *Withdrawn*; an item without an active decision is *Open*.

## 21. Extending the tool safely

| You want to add | Where | What must be re-evaluated |
|---|---|---|
| a tag rule for a new XML schema | `Inputs/tag_rules.yaml` of the project; or, for every project, `reading.TAG_RULES_YAML` | `test_documents.py`; the outline of one real document |
| an R function the comparison should understand | `reading.R_FUNCTION_MAP_YAML` (neutral name, arguments, domain), `review.to_sympy` and `review.evaluate` | `test_checks.py`, with new pairs in `engine/tests/equivalence_corpus.yaml` |
| a question type | a prompt in `core.PROMPTS`, a validator branch in `review.validate_narrow`, a handler in the stand-in | the bad-answer corpus; the token budget for the largest unit |
| a category | the constants of `core.py`, `review.NEXT_STEPS`, section 20 | the wording lint; the identity tests |
| a search signal | `review.search_one`, `review.REASON_TEMPLATES`, the `signals` setting | `develop.recall`: the signal must earn its place on the recall ladder |
| a word the search should ignore, or a code-to-prose bridge | `review.STOPWORDS_TEXT`, `review.BRIDGE_PATTERNS_YAML` | the layout lint, which checks both for domain words |
| a column or a sheet of `Output.xlsx` | `runner.WORKBOOK_LAYOUT_YAML` and the row builder of that sheet in `runner.py` | `test_runner.py`; the end-to-end tests |

A prompt's text is part of every question id made from it, and recorded answers are found by that id: change a prompt's words and raise its `VERSION` line together, so that no answer to the old question is taken for an answer to the new one.

After any change, see section 23.

## 22. How the tool was measured

With the stand-in `chat()` on invented samples: an equivalence corpus of 100 formula pairs, in which no differing pair is ever reported as agreeing; the seeded-difference harness (`develop.harness`), in which every seeded difference in a sample ends flagged in an expected category and the clean baseline flags none of its gold clean units; the recall ladder of the search (`develop.recall`); the six seeded differences of `F_capital_known`; and reproducibility by replay from recorded answers. Every measurement appends a row to `engine/tests/history.csv`. What is still to be done is to measure the same with the real model on a real package.

**Line counts.** `python engine/develop.py budgets` prints them. The plan asked for at least 30 percent of each file to be docstrings, comments and overview; the files are below that share, and the numbers are reported as they are rather than padded.

**Dependencies.**

| Package | Needed | Note |
|---|---|---|
| PyYAML>=6.0 | required |  |
| openpyxl>=3.1 | required |  |
| python-docx>=1.1 | required |  |
| numpy>=1.24 | required |  |
| scipy>=1.10 | required |  |
| sympy>=1.12 | required |  |
| rdata>=1.0 | required |  |
| pdfplumber>=0.10 | optional |  |
| pypdf>=4.0 | optional |  |
| pyreadr | optional, not used in 0.0.1 | a second, independent reader of stored data |

**Reading.** The content account closes on every file of every sample. The hard samples measure guided reading: on the XML schema the rules do not know, guidance takes heading depths from 0 of 4 right to 4 of 4 for one question; the two-column PDF and the Word file raise no doubt and cost nothing. Every measurement appends a row to `engine/tests/history.csv`.

**What is not measured here.** Whether a unit is *useful* — a package file with no reader is fully accounted for and still unusable. And guided reading against a real model: everything above was measured with the stand-in, which shows the machinery is safe and the vocabularies sound, and does not show how a model reads an unfamiliar schema. `agentic_reading` stays `off` until `develop.run` holds against the real model.

## 23. Maintaining the tool

`python engine/develop.py budgets` prints the line count of each module against its budget. `python engine/develop.py release` rewrites `engine/release.json`, the fingerprint of every engine file, and must be the last step of every change: a run records the engine files it used and cell 5 compares them with the release. `python engine/develop.py check-docs` checks this manual against the code: every function, sheet, setting, rule, step and cell it names must exist, and every setting and rule must be explained. `python engine/develop.py notebook` rebuilds `Verifier.ipynb`, the only way it is ever changed. `python engine/develop.py harness A_minimal --limit 10` runs the seeded-difference harness.
