# AIVA 0.0.1 - User Manual

This manual is assembled by `tools/build_manual.py`; its tables are generated from the source.

# Part I. For everyone

## 1. What AIVA is and what it is not

AIVA, the AI Verification Assistant, helps a model validator with one question: **does the code of an R package do what the methodology says, and does the model documentation describe both truthfully?** It compares three things, called the three corners:

- **the methodology** (in the files: *canon*), the approved description of how the model must work;
- **the model package**, an R source tarball with code, stored parameter data, roxygen blocks, help pages, tests and vignettes;
- **the model documentation**, the developer's description of the package.

AIVA reads all three, cuts them into units, links what corresponds, checks formulas, values and stated rules by code, and raises everything it could not line up as a **flagged item** for a person to decide.

**An evidence pack, not a verdict.** A run produces `Output.xlsx`, `Validation_Report.docx` and an `_audit` folder from which every statement in the two files can be re-verified. A named person records a determination against every flagged item. AIVA never decides whether a model is acceptable.

**What AIVA does not do.** It does not run the model, does not execute any R code, does not judge whether the methodology itself is sound, and does not read the content of images: a formula given only as a picture is raised for manual review, never skipped.

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
| R11 | Five flat bundles, one-way imports, plain code, line budgets. |
| R12 | Workspace discipline: build on local disk, copy whole files, keep the file count small, sync after every step. |

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

# Part II. For analysts who run reviews and read the outputs

## 4. Before you start

**The three inputs.** For every review you need: the methodology (XML, also inside a `.txt` file; HTML or Word's web export `.mhtml`; `.docx`; or PDF), the R package as a source tarball (`.tar.gz`), and the model documentation (`.docx`, PDF or the markup formats above). The format is found from the content of a file, not from its extension. PDF is the weakest input: layout is guessed from positions on the page, so prefer `.docx` or XML when you have the choice.

**The model ID** names the project folder. Use letters, digits, `-` and `_`, at most 24 characters; longer names would push downloaded files beyond the path length Excel can open, and the setup cell refuses them in plain words.

**What the setup cell creates** (`cell 8`):

```
Projects/<model ID>/<date initiated>/Inputs/1_Methodology/
                                     Inputs/2_Model_Package/
                                     Inputs/3_Model_Documentation/
                                    Run_<date>_<time>/Outputs/   Output.xlsx, Validation_Report.docx
                                    Run_<date>_<time>/_audit/    everything needed to re-verify the run
```

Each Inputs folder holds a README that says what goes in. Optional files directly under `Inputs/`: `glossary.xlsx` (two columns: term, meaning) and `tag_rules.yaml` (chapter 7). AIVA opens input files for reading only.

## 5. The notebook, cell by cell

`AIVA_Interface.ipynb` is the only file you open. It has twelve widgets: LLM endpoint, LLM token, LLM user id, model ID, project, run, Projects folder, JFrog index URL, concurrency limit, token cap, reviewer id and reviewer role.

| Cell | What it does |
|---|---|
| `cell 1` | How to use the notebook. |
| `cell 2` | Installs the packages from the JFrog index and restarts Python. Once per cluster start. |
| `cell 3` | Creates the widgets and finds the notebook's own folder. Run it again after entering the model ID to refresh the project and run lists. |
| `cell 4` | Preflight: versions, a write-and-read-back test in the Projects folder, scratch space. |
| `cell 5` | **Use the latest widget values.** The only cell that reads the three LLM widgets. It prints the token's age and length, never the token. |
| `cell 6` | **Your cell**: paste your `chat()` definition. Keep the signature; read the three live values with `aiva_live(...)` when `chat()` is called. |
| `cell 7` | Self-test of `chat()`: one tiny question. It reports success or which kind of failure was seen, and measures the time per call. A switch selects the stand-in instead. |
| `cell 8` | Project setup: creates the folders and says which Inputs folder is still empty. |
| `cell 9` | Starts or resumes the run: the reading steps, without any AI. Ends with the outline of the methodology as AIVA read it. |
| `cell 10` | Confirms that you checked the outline (chapter 7). The AI steps do not start without it. |
| `cell 11` | The call plan: questions by type, the largest prompt against the token cap, the expected duration. |
| `cell 12` | Runs the AI steps and the checks, in mode A, B or C. |
| `cell 13` | Status: finished steps, call statistics, token age, whether the run waits for a fresh token; pause and stop switches. |
| `cell 14` | Determinations: run after uploading the completed workbook (chapter 8). |
| `cell 15` | Verify this evidence pack (chapter 10). |
| `cell 16` to `cell 18` | Appendix: environment probe, reviewer sanity checks, evaluation harness. |

**Keeping the token fresh.** Tokens live about fifteen minutes; a run takes longer. Three modes, all served by the same engine code:

- **Mode A**: `cell 12` starts a background thread and returns. When you paste a fresh token into the widget, `cell 5` runs again by itself and the waiting workers go on.
- **Mode B**: the same, but you run `cell 5` by hand after pasting.
- **Mode C**: `cell 12` works in the foreground for a set number of minutes, then stops by itself and asks for a fresh token. Run it again to resume. This mode needs no assumption about widgets or threads and always works.

In every mode a question that already has a final answer is never asked again, so nothing is lost and nothing is paid for twice. When many calls in a row fail, the run pauses itself and says so; check the gateway and run `cell 12` again.

## 6. Reading Output.xlsx

Eight sheets, always in this order; a sheet whose step has not run yet shows its header only, and *Run progress* on the first sheet says where the run stands.

**How to read one row of a mapping sheet.** From left to right: what the unit is (blue identity columns and its text), what it was linked to in the methodology (green) and in the other corner, with the relation and **how the link was established**, then the assessment columns, then *Overall status* and the ids of its flagged items. Several values in one cell stand on separate lines, each prefixed with its reference. Text taken from your inputs or from the model is always shown in quotation marks with its citation.

**"How established"** starts with one of a small set of phrases: *Parsed from the files*; *AI judgement (64%)*; *Symbolic check: agrees*; *Numerical check: agrees (200 points)*; *Numerical check: differs*; *Value check: ...*; *Table matched by headers and row keys*; *Recorded by a person*. After an AI judgement you also see why the passage was proposed, for example "shares the words floor, probability; shares the rare number 0.0003".

**What "AI judgement (64%)" means.** The model chose this passage among lettered passages, quoted words from both sides that code found verbatim, and did not accept a planted control passage. The percentage is the model's own statement and is not calibrated; treat it as an ordering hint at most. Where a deterministic check exists for the link, the check's result follows in the same cell and has the last word.

**What was searched / Why not mapped.** Every unit without a link shows what AIVA looked for (words, symbols, numbers) and what happened: nothing was proposed, the model saw only passages on the same topic, or its answer could not be used.

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

Clean statuses: *Traced to methodology*, *Supporting code (justified)*, *Unit test*, *Narrative - nothing to check*. The other four need attention, and every unit with one of them is named by at least one row of `Flagged_Items`. `Mapping_Coverage` counts the same statuses; its numbers equal what you get by filtering *Overall status* on the two mapping sheets, and AIVA stops a run in which they would not.

**The value-comparison rule** is one rule, used for parameter tables, numbers in code, numbers in roxygen text and numbers in the documentation. Its full text is on `Model_Package_Info`. In short: percent, basis points and scientific notation are converted first; a value agrees at stated precision when rounding it to the decimals of the methodology's value gives that value; there is no hidden tolerance. A cell reads like "package 0.10, methodology 0.15 (C-0017 row Retail): differs".

**The mathematical check.** For a linked function or statement and a passage that states a formula, AIVA aligns the symbols first (shown as "with rho = ρ"), then tries to show symbolically that both sides are equal, then evaluates both at 200 seeded points, including points at and around every threshold. *Differs* always comes with a counterexample: the inputs and both results. *Could not be decided* names one reason from a fixed list and is never clean.

**How to read a path.** *What was observed* on `Flagged_Items` ends with the supporting path, hop by hop: the unit, the function it sits in, the table it reads, the passage it corresponds to with how that was established, the roxygen block and documentation passage that describe it.

**The sheets and columns.** Generated from `engine/references/workbook_layout.yaml`:

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
| Overall status | assessments | The one final status of the unit (chapter 6). |
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
| Overall status | assessments | The one final status of the unit (chapter 6). |
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

## 7. Confirming the methodology outline; tag rules; the glossary

Everything downstream depends on the methodology having been cut correctly. After `cell 9`, open `Chunks_Canon` and compare *Level* and *Section (heading chain)* with the methodology's own table of contents; the same outline is printed by `cell 9`. Then run `cell 10`. Your reviewer id is recorded in the run manifest and shown on `Model_Package_Info`.

If the methodology uses XML tags AIVA has not seen, it still reads them by their shape and lists them on `Model_Package_Info` as "unrecognised tag". To teach AIVA a schema, put a `tag_rules.yaml` next to the three Inputs folders, with the same keys as `engine/references/tag_rules.yaml` (which tags are headings, paragraphs, tables, rows, cells, captions, figures, equations, or to be ignored). Project rules are added to the shipped ones.

`glossary.xlsx` is optional: two columns, a term or abbreviation and its meaning. Its entries join the bridge vocabulary that AIVA harvests from the inputs themselves, which helps the search connect a code name such as `rho_a` with "asset correlation".

## 8. Working through Flagged_Items

1. Download `Output.xlsx` from `Outputs/`.
2. On `Flagged_Items`, fill the four **yellow** columns for the items you decide: *Decision* (`Requires action` or `No action needed`; capital letters do not matter), *Reviewer*, *Role* and *Rationale*. A decision without all three other cells is reported back and not recorded. You may sort and filter; AIVA finds rows by *Item id*, never by position. Anything typed outside the yellow columns is ignored.
3. Upload the workbook into the same `Outputs/` folder, under any name. AIVA recognises it by the identity stored inside the file, keeps a copy of exactly what you uploaded in `_audit/uploads/`, and refuses in plain words a workbook of another run or a file in the old `.xls` format.
4. Run `cell 14`. It says what was recorded and what was incomplete, and rebuilds both output files. `Outputs/` again holds exactly two files.

What is recorded for every determination: item id, decision, reviewer, role, rationale, the time, the reviewer id of whoever ran the cell, and the SHA-256 of the uploaded workbook. Records are only ever added. Changing a decision adds a record; clearing one adds a record with the decision *Withdrawn* and the item is *Open* again. The records form a hash chain whose head appears as the *Determinations record fingerprint* on `Model_Package_Info` and on the first page of the report.

A workbook you have edited and uploaded is never overwritten before it has been read in.

## 9. Reading Validation_Report.docx

The first page names the model ID, the date initiated, the run, the package and its version, the engine version, the graph version id and the determinations record fingerprint, and says either "N of M flagged items are still open." or "Every flagged item has a recorded determination.". Then: what was reviewed (every input with its fingerprint, and what changed since the previous run); what AIVA did and did not assess, with this run's limits; coverage; flagged items counted by concern and category, never ranked; every flagged item with its evidence, its path and the determination recorded against it; methodology passages that nothing points to, for information; how to re-verify the pack; and the AI call statistics.

## 10. The run folder as an evidence pack

`_audit` holds, as JSON Lines files: the run manifest, the chunks of both documents, the model units and parameter tables, the search records and candidates, the graph ledger, every exchange with `chat()` (compressed, token removed), all check records, the statuses, the flagged items, the determinations, the uploaded workbooks, the run summary and the exports of the graph. Chapter 23 lists every file.

`cell 15` verifies a pack from the run folder and the Inputs folder alone: it re-hashes the inputs against the manifest, re-reads them and compares every content hash, verifies both hash chains, re-checks that statuses and flagged items match, resolves every citation on `Flagged_Items`, and compares the ids inside the workbook with the records. Every line must read *Confirmed*. To archive a review, keep the project folder as it is.

## 11. When something goes wrong

| What you see | What it means and what to do |
|---|---|
| The status cell says the run waits for a fresh token | The token ran out. Paste a new one (mode B: then run `cell 5`). No question is repeated. |
| "The time box of this foreground run is over" | Mode C stopped by itself. Paste a fresh token and run `cell 12` again. |
| "Many calls in a row failed, so the run paused itself" | The gateway is not answering. Check it with `cell 7`, then run `cell 12` again. |
| The cluster stopped | Start it, run `cell 2` to `cell 8`, choose the same run in the run widget, and run `cell 12`. The run resumes after its last finished step. |
| An input changed | Start a **new run** in the same project. `Model_Package_Info` lists what changed since the previous run. Never edit inputs of a run that has started. |
| A unit of kind *File not read* | That file or expression could not be parsed. It has a flagged item with the reason; the rest of the package was still read. |
| "... belongs to another run or another list of items" | The uploaded workbook is not this run's `Output.xlsx`. Download the current one and fill it again. |
| A cell reads "This text could not be shown in plain words" | AIVA withheld a text that contained technical traces; the text is in `_audit/run_log.txt`. Please report it; it is a defect in AIVA. |
| "This is a defect in AIVA, not in the model under review" | The coverage identity did not hold and the run stopped on purpose. Keep the run folder and report it. |

## 12. Known limitations

- The content of images is never read. Formulas given only as pictures end *Not assessed* or make the linked code *Traced - check undecided*.
- PDF input is read by position on the page; multi-column layouts and tables without ruling lines may be cut wrongly. Check the outline.
- R code is parsed by AIVA's own reader, not by R. Unusual syntax becomes a *File not read* unit for that expression only. Functions with loops or branches are compared statement by statement; R semantics that AIVA's evaluator does not cover (recycling of vectors, matrix products) end as "uses operations AIVA cannot evaluate".
- Stored data is decoded without R. Objects that are not tables, vectors or short lists are described and not compared; missing values of different kinds are not told apart.
- The percentage after "AI judgement" is not calibrated.
- The evaluation so far used invented sample projects and the stand-in `chat()`; results with a real model on a real package are the owner's Phase 12 campaign (chapter 27).

# Part III. For the five code reviewers

## 13. How to review a bundle

The engine is five flat files, `aiva1_documents.py` to `aiva5_run_report.py`, plus the small shared file `aiva0_shared.py`. A file imports only the shared file and lower-numbered files, which `test_layout_rules.ImportDirection.test_a_file_imports_only_the_shared_file_and_lower_numbered_files` proves. Each reviewer owns one bundle.

1. **Read `aiva0_shared.py` first** (chapter 14). It holds the vocabulary and every data contract.
2. Read the opening overview of your bundle: what it does, what it takes in and produces, which sheets show its results, which design rules it enforces and in which functions, and how to sanity-check it.
3. Read the file top to bottom; it is written in reading order. Appendix C lists every function with its line number.
4. Run your test file: `python -m unittest discover -s engine/tests -p "test_aiva3_mapping.py"` (with your file's name).
5. Run your sanity check: `cell 17` of the notebook, with `REVIEWER` set to your number. It runs the steps of your bundle on a sample project with the stand-in `chat()` and tells you where the workbook is.
6. Work through the checklist at the end of your chapter. Every line names a test, a function or a place in the workbook that exists; `tools/check_docs.py` fails when one does not.
7. Record your review under `docs/review_records/`: your name, the date, the commit you read, each checklist line with what you saw, your questions and how each was resolved.

Two things hold for every bundle. Nothing taken from an input or from the model is executed (`test_layout_rules.LineBudgetsAndStyle.test_only_the_dataclass_decorator_and_no_execution_of_text`). And no sentence the engine can write uses a rating word (`test_layout_rules.StaticWordingLint.test_no_banned_wording`).

## 14. aiva0_shared.py, for everyone

**Purpose.** One vocabulary and one set of data contracts for all bundles, so that no bundle invents its own words or record shapes.

**Walk through.** Vocabulary of Appendix A as constants (relations, the phrases of "how established", statuses, categories, decision words, unit kinds, the fixed reasons for an undecided check and for a rejected answer); the wording rule as a function, `aiva0_shared.has_banned_wording`; the dataclasses (chunks, model units, edges, candidates, flagged items, determinations, step context and result); canonical JSON and hashes (`aiva0_shared.canonical_json`, `aiva0_shared.content_hash`, `aiva0_shared.swhid_content`); hash chains (`aiva0_shared.chain_records`, `aiva0_shared.verify_chain`); numbers as written (`aiva0_shared.parse_number`, `aiva0_shared.find_numbers`, `aiva0_shared.plain_number`); symbols (`aiva0_shared.normalise_symbol`); and the neutral expression tree with its linear notation (`aiva0_shared.expr_to_text`).

**Checklist for everyone.**

- The content hash ignores white space and line endings and nothing else: `test_aiva0_shared.CanonicalJsonAndHashes.test_content_hash_ignores_white_space_and_line_endings_and_nothing_else`.
- A chain detects an edited, a removed and a re-ordered record: `test_aiva0_shared.CanonicalJsonAndHashes.test_chain_detects_edited_removed_and_reordered_records`.
- Percent, basis points and scientific notation give the same value, and the form as written is kept: `test_aiva0_shared.Numbers.test_percent_basis_points_and_scientific_notation_become_the_same_value`, `test_aiva0_shared.Numbers.test_form_as_written_and_decimals_are_kept`.
- No category and no status rates seriousness: `test_aiva0_shared.Wording.test_no_category_or_status_rates_seriousness`.

## 15. Reviewer 1: aiva1_documents.py

**Purpose.** Turn methodology and documentation files of any supported form into chunks in reading order: paragraphs, tables, figures and equations, each with its level, heading chain, numbering as written, locator and content hash.

**Walk through.** The formula reader (`aiva1_documents.parse_formula`) and the converters from Office Math, MathML and LaTeX to AIVA's linear notation (`aiva1_documents.math_to_linear`, `aiva1_documents.latex_to_linear`); format detection from content (`aiva1_documents.detect_format`); recorded repairs of malformed markup (`aiva1_documents.repair_markup`) and the tolerant reader; the walker driven by `engine/references/tag_rules.yaml` (`aiva1_documents.walk_element`); Word's web export (`aiva1_documents.blocks_from_mhtml`), Word files (`aiva1_documents.blocks_from_docx`) and PDF (`aiva1_documents.blocks_from_pdf`); level inference (`aiva1_documents.infer_levels`); chunks (`aiva1_documents.blocks_to_chunks`); the two steps (`aiva1_documents.read_methodology`, `aiva1_documents.read_documentation`).

**Contracts.** In: the input files. Out: chunks_canon, chunks_doc, read_repairs, info_rows, outline. Shown on `Chunks_Canon`, `Chunks_Doc` and `Model_Package_Info`.

**Known limitations.** PDF layout is guessed from positions. Juxtaposition is read as a product only inside structured markup, never in running text. Images are never read.

**Checklist.**

- Every table of a sample methodology is exactly one row on `Chunks_Canon`: `test_aiva1_documents.ReadingFiles.test_one_table_is_one_chunk_and_inline_formulas_are_found`.
- Levels and heading chains match the document's own outline, also for a flat-numbered annex: `test_aiva1_documents.ReadingFiles.test_xml_in_a_txt_file_nested_levels_tables_equations`; compare with the outline printed by `cell 9`.
- Repairs are recorded: `test_aiva1_documents.ReadingFiles.test_malformed_markup_is_repaired_and_the_repairs_are_recorded`.
- An equation or figure that cannot be read is still a chunk and ends with a flagged item: `test_aiva4_checks.SeededSample.test_an_equation_given_as_an_image_is_never_skipped`.
- The format is detected from the content: `test_aiva1_documents.ReadingFiles.test_format_is_found_from_content_not_from_the_extension`.
- Nothing from an input is executed, ambiguous notation is not guessed, and document-type declarations are removed before parsing: `aiva1_documents.parse_formula`, `aiva1_documents.safe_xml`, `aiva1_documents.repair_markup`; `test_aiva1_documents.FormulaNotation.test_ambiguous_notation_is_not_guessed`, `test_aiva1_documents.ReadingFiles.test_entities_defined_inside_an_office_file_are_never_expanded`.
- The same bytes give the same chunks: `test_aiva1_documents.ReadingFiles.test_same_bytes_give_the_same_chunks`.
- A file that cannot be read never stops the run: `test_aiva1_documents.ReadingFiles.test_a_file_that_cannot_be_read_gives_a_not_read_unit_and_never_stops_the_run`.

## 16. Reviewer 2: aiva2_package.py

**Purpose.** Read an R source tarball without R: unpack it safely in memory, parse the code with AIVA's own reader, turn functions and formula statements into neutral expression trees, read roxygen blocks, help pages, tests and vignettes as units, and decode stored data into parameter tables.

**Walk through.** Safe unpacking (`aiva2_package.unpack_package`); DESCRIPTION and NAMESPACE; the tokenizer and the operator-precedence parser (`aiva2_package.tokenize_r`, `aiva2_package.parse_r_source`), which recovers expression by expression; facts about code (`aiva2_package.code_facts`, `aiva2_package.has_arithmetic`); conversion to the neutral tree through `engine/references/r_function_map.yaml` (`aiva2_package.to_expr`) and composition of straight-line functions (`aiva2_package.compose_function`); units from R files, roxygen, help pages and vignettes; stored data (`aiva2_package.decode_data_file`, `aiva2_package.table_of`); reads of stored data (`aiva2_package.data_reads`); the step (`aiva2_package.read_package`).

**Contracts.** In: the tarball. Out: model_units, parameter_tables, package_info. Shown on `Chunks_Model` and `Model_Package_Info`.

**Known limitations.** No second, independent reader of stored data and no extraction of R classes and attributes beyond what the decoder gives. S4 and R5 classes are read as code, not as structures. Missing values of different kinds are not told apart.

**Checklist.**

- Every non-blank line of every parsed R file lies inside a unit: `test_aiva2_package.ReadingR.test_every_non_blank_line_lies_inside_a_unit`.
- A broken expression gives a *File not read* unit and the rest is still read: `test_aiva2_package.ReadingR.test_a_broken_expression_is_kept_as_not_read_and_the_rest_is_still_parsed`.
- Roxygen blocks attach to the object that follows them; help pages out of step are seen: `test_aiva2_package.ReadingR.test_roxygen_blocks_help_pages_tests_and_vignettes_become_units`.
- Unsafe archive members are refused one by one: `test_aiva2_package.UnpackingSafely.test_paths_that_leave_the_package_links_and_devices_are_refused_and_nothing_touches_disk`.
- Stored data decodes without R and nothing in it is evaluated: `test_aiva2_package.StoredData.test_rda_and_rds_are_decoded_without_r_and_profiled`, `test_aiva2_package.StoredData.test_a_data_file_that_is_not_r_data_is_recorded_as_not_assessed`.
- Reads of stored data are recognised: `test_aiva2_package.StoredData.test_reads_of_stored_data_are_recognised`.
- Every entry of `engine/references/r_function_map.yaml` has been read and agreed: the function, its arguments, its valid domain.
- A sign changed above the return reaches the comparison: `test_aiva2_package.ReadingR.test_straight_line_functions_are_composed_so_that_a_sign_above_the_return_is_seen`.
- Supporting code by syntax never holds arithmetic or a non-trivial number, also not as a default: `test_aiva2_package.ReadingR.test_supporting_code_by_syntax_never_holds_arithmetic_or_a_non_trivial_number`.

## 17. Reviewer 3: aiva3_mapping.py

**Purpose.** Record what the readers found as a graph; propose, deterministically and with plain reasons, which passages a unit may correspond to; ask the judge; validate every answer; write accepted links.

**Walk through.** The ledger (`aiva3_mapping.ledger_records`, `aiva3_mapping.verify_ledger`, `aiva3_mapping.find_path`); words (`aiva3_mapping.split_words`); what is indexed for a unit (`aiva3_mapping.unit_fields`, `aiva3_mapping.chunk_fields`); the signals: field-aware text ranking (`aiva3_mapping.bm25_scores`), the bridge vocabulary (`aiva3_mapping.harvest_bridge`), explicit references (`aiva3_mapping.resolve_reference`), rare shared anchors and the restart walk (`aiva3_mapping.anchor_weights`, `aiva3_mapping.restart_walk`), formula signatures and table shape; fusion by rank (`aiva3_mapping.fuse`) and reasons; the steps `aiva3_mapping.build_graph` and `aiva3_mapping.find_candidates`; questions (`aiva3_mapping.assemble_question`, `aiva3_mapping.choose_decoys`); validators (`aiva3_mapping.validate_answer`); `aiva3_mapping.judge_links` and the second, oppositely framed question.

**Contracts.** In: chunks, units, tables, word lists and prompts under `engine/references/`. Out: graph_ledger, bridge_vocabulary, candidates, search_records, judgement_problems, second_opinions. Shown in the reference, relation, "How established", "What was searched" and "Why not mapped" columns of both mapping sheets.

**Known limitations.** Recall is complete on the small samples, so they cannot show which signal earns its place on a large methodology; that is measured in Phase 12 with `tools/recall_at_k.py`. The stemmer is deliberately weak.

**Checklist.**

- The ledger offers no way to change or remove a record, and verification detects tampering: `test_aiva3_mapping.Ledger.test_a_later_record_is_appended_and_never_replaces_an_earlier_one`, `test_aiva3_mapping.Ledger.test_an_edited_a_removed_and_a_reordered_record_are_each_detected`.
- The search is deterministic: `test_end_to_end.TwoRunsAreTheSame.test_same_inputs_give_the_same_audit_records_and_the_same_graph_version`.
- A reason shown in the workbook can be reproduced by hand: `test_aiva3_mapping.Words.test_bm25_by_hand`, `test_aiva3_mapping.Search.test_the_gold_passage_is_proposed_and_every_proposal_gives_its_reason`.
- Common anchors count for nothing: `test_aiva3_mapping.Search.test_an_anchor_that_too_many_units_mention_is_dropped`.
- Signatures re-order and never propose alone; propagated candidates never become links without the judge: `test_aiva3_mapping.Search.test_signatures_reorder_and_never_propose_alone`, `aiva3_mapping.propagated_candidates`.
- The bad-answers corpus passes: `test_aiva3_mapping.QuestionsAndValidators.test_the_bad_answer_corpus`, `test_aiva3_mapping.QuestionsAndValidators.test_letters_come_from_a_hash_not_from_the_score_and_the_question_id_is_the_prompt_hash`.
- A rejected answer never becomes a link: `test_aiva3_mapping.QuestionsAndValidators.test_a_rejected_answer_never_becomes_a_link`.
- No prompt contains a domain concept: `test_layout_rules.StaticWordingLint.test_no_domain_concept_in_engine_prompts_or_stop_words`.

## 18. Reviewer 4: aiva4_checks.py

**Purpose.** Confirm or contradict by code every link that involves a formula, a value, a table or a stated rule; check roxygen blocks and help pages against the code; decide the one status of every unit; raise the flagged items; prove the coverage identity.

**Walk through.** The value rule (`aiva4_checks.compare_values`); tree to SymPy, node by node (`aiva4_checks.to_sympy`) and the bounded symbolic step; AIVA's own evaluator and the sample points (`aiva4_checks.evaluate`, `aiva4_checks.sample_points`, `aiva4_checks.numeric_step`); alignment, settled before comparing (`aiva4_checks.align`, `aiva4_checks.prepare_alignment`, `aiva4_checks.compare_formulas`); the step `aiva4_checks.check_mathematics`; tables (`aiva4_checks.reconcile`) and `aiva4_checks.check_values`; rules (`aiva4_checks.stated_rules`, `aiva4_checks.rule_in_trees`, `aiva4_checks.check_rules`); `aiva4_checks.check_package_docs`; the ordered status rules (`aiva4_checks.model_unit_outcome`, `aiva4_checks.doc_unit_outcome`), items (`aiva4_checks.build_items`), the identity (`aiva4_checks.check_identity`) and `aiva4_checks.account_coverage`.

**Contracts.** In: everything before it. Out: math_checks, value_checks, rule_checks, package_doc_checks, new ledger edges, unit_status, flagged_items, coverage. Shown in the assessment columns, *Overall status*, `Mapping_Coverage` and `Flagged_Items`.

**Known limitations.** A statement that does not agree on its own takes the result of the check of its whole function when both are linked to the same passage; a statement without a link counts as traced when the agreeing check of its function ran through it. Both extend the plan's rules and are listed in chapter 27. Prose numbers are compared only when they sit among the same words.

**Checklist.**

- *Differs* only ever comes with a counterexample, and the same seed gives the same one: `test_aiva4_checks.FormulaComparison.test_differs_always_comes_with_a_counterexample_and_the_same_seed_gives_the_same_one`.
- No differing pair of the corpus is ever reported as agreeing: `test_aiva4_checks.FormulaComparison.test_the_corpus_no_differing_pair_ever_agrees`.
- An undecided check is never clean: `test_aiva4_checks.SeededSample.test_the_flipped_sign_in_cond_pd_is_caught_with_a_counterexample`, `test_aiva4_checks.SeededSample.test_an_equation_given_as_an_image_is_never_skipped`.
- No string is ever parsed by SymPy: read `aiva4_checks.to_sympy`.
- One value-comparison function is used everywhere, and its rule text is shown on `Model_Package_Info`: `aiva4_checks.compare_values`, `test_aiva4_checks.ValueRule.test_the_table_of_the_rule`.
- Alignment is fixed before the comparison: `test_aiva4_checks.FormulaComparison.test_alignment_is_fixed_before_comparing_so_swapped_symbols_end_as_differs`.
- The status rules in the code are the rules in chapter 6: `test_aiva4_checks.SeededSample.test_every_status_was_decided_by_a_rule_of_the_ordered_list`.
- Each part of the identity stops the run when it is violated: `test_aiva4_checks.SeededSample.test_a_broken_identity_stops_the_run_and_names_the_part`, `test_aiva4_checks.SeededSample.test_the_identity_not_clean_if_and_only_if_an_item_names_the_unit`.
- All six seeded differences of the known sample are flagged in an expected category: `test_aiva4_checks.SeededSample.test_all_six_seeded_differences_are_flagged_in_an_expected_category`.
- The clean baselines flag none of the units listed as clean: `test_aiva4_checks.CleanSamples.test_the_clean_baseline_flags_none_of_the_units_listed_as_clean`.

## 19. Reviewer 5: aiva5_run_report.py

**Purpose.** Everything around the review itself: settings, paths, the live values with the token, the only place where `chat()` is called, the audit store, the runner, the workbook, the report, determinations and verification.

**Walk through.** Settings as an allow-list (`aiva5_run_report.make_settings`); paths (`aiva5_run_report.setup_project`, `aiva5_run_report.open_run`); live values (`aiva5_run_report.LiveValues`); the store (`aiva5_run_report.AuditStore`); the wrapper (`aiva5_run_report.call_chat`, `aiva5_run_report.ask_one`, `aiva5_run_report.make_asker`) and replay (`aiva5_run_report.replay_chat`); the runner (`aiva5_run_report.load_pipeline`, `aiva5_run_report.run_pipeline`, `aiva5_run_report.run_step`); the plain-language gate for every cell (`aiva5_run_report.plain_cell`); the workbook (`aiva5_run_report.build_workbook`, `aiva5_run_report.check_written_totals`) and the overwrite guard (`aiva5_run_report.rebuild_outputs`); the call plan (`aiva5_run_report.call_plan`); determinations (`aiva5_run_report.find_uploads`, `aiva5_run_report.read_yellow_cells`, `aiva5_run_report.record_determinations`); the report (`aiva5_run_report.build_report_file`); verification (`aiva5_run_report.verify_evidence_pack`).

**Contracts.** In: every audit record. Out: the two output files, `_audit`, determinations. Shown everywhere.

**Known limitations.** Files are synced after every batch of calls and every step, not on a timer. A report with several thousand items is long; its build time has not been measured at that size.

**Checklist.**

- The token never persists, and no question is lost or asked twice: `test_aiva5_run_report.TokenRefresh.test_pause_resume_nothing_lost_nothing_twice_no_token_on_disk`.
- All three failure shapes of `chat()` are handled: `test_aiva5_run_report.TokenRefresh.test_all_three_failure_shapes_are_classified_as_authentication`, `test_aiva5_run_report.ResumeAndBreaker.test_breaker_opens_and_a_second_call_finishes_without_repeating`.
- The runner calls only functions of its explicit dictionary and refuses version drift: `test_aiva5_run_report.RunnerAndWorkbook.test_pipeline_refuses_unknown_functions_and_version_drift`.
- A run writes only inside its run folder: `test_aiva5_run_report.RunnerAndWorkbook.test_a_run_writes_only_inside_its_own_folder`.
- The workbook format is right: `test_aiva5_run_report.RunnerAndWorkbook.test_workbook_format`.
- No cell contains technical text or a rating word, and whole numbers are whole: `test_end_to_end.WhatAnAnalystReads.test_every_cell_of_the_workbook_is_in_plain_words`, `test_end_to_end.WhatAnAnalystReads.test_the_word_files_are_in_plain_words_and_the_report_holds_every_item_once`.
- Coverage on the sheet equals what filtering gives: `test_end_to_end.WhatAnAnalystReads.test_coverage_on_the_sheet_equals_what_filtering_overall_status_gives`.
- Determinations: `test_end_to_end.HumanRoundTrip.test_a_renamed_sorted_workbook_with_an_added_sheet_is_read_by_item_id`, `test_end_to_end.HumanRoundTrip.test_a_changed_decision_appends_and_a_cleared_one_is_recorded_as_withdrawn`, `test_end_to_end.HumanRoundTrip.test_an_edited_workbook_is_never_overwritten_before_it_has_been_read_in`, `test_end_to_end.HumanRoundTrip.test_a_workbook_of_another_run_and_an_xls_file_are_refused_in_plain_words`.
- The verification cell detects tampering: `test_end_to_end.VerifyingARunFolder.test_a_changed_chunk_a_broken_chain_and_a_deleted_status_are_each_detected`, `test_end_to_end.VerifyingARunFolder.test_a_changed_input_byte_is_detected`.
- Replaying the recorded answers reproduces the run: `test_end_to_end.TwoRunsAreTheSame.test_replaying_the_recorded_answers_reproduces_graph_statuses_and_items`.
- The notebook's cells run: `test_notebook.NotebookCells.test_the_cells_run_from_setup_to_verification_with_the_stand_in`.

# Part IV. Reference

## 20. Data contracts

Records are plain dictionaries in JSON Lines files; the dataclasses that produce them are in `aiva0_shared.py` (Appendix C lists them). The most important ones:

| Record | File in `_audit` | Main fields |
|---|---|---|
| Chunk | chunks_canon.jsonl, chunks_doc.jsonl | ref, corner, kind, text, level, heading_chain, numbering, caption, locator, table, equation, refs_out, checkable, content_hash |
| Model unit | model_units.jsonl | ref, kind, name, inside, parent_ref, file, lines, text, code (formals, symbols, numbers, calls, expression, composed, reads_data, exported, plumbing), roxygen, helppage, data, content_hash |
| Parameter table | parameter_tables.jsonl | unit_ref, object_name, header, rows, row_key, column_types |
| Ledger record | graph_ledger.jsonl | node: ref, node_kind, corner. edge: source, target, kind, relation, how, confidence, evidence, provenance. Both: prev_hash, record_hash |
| Candidate | candidates.jsonl | unit_ref, target_ref, target_corner, rank, fused_score, signals, reason, search_pass |
| Search record | search_records.jsonl | unit_ref, target_corner, searched_text, shortlist, ranked_anywhere, note |
| Call record | llm_calls_001.jsonl.gz and following | question_id, question_type, unit_ref, attempt, letters, planted, prompts (token removed), response_text, outcome, answer, final, seconds |
| Math check | math_checks.jsonl | check_id, unit_ref, target_ref, both formulas in linear notation, formula_source, alignment, symbolic, numeric, counterexample, outcome, undecided_reason, seed, points_valid |
| Value check | value_checks.jsonl | check_id, unit_ref, target_ref, what, column_map, key_map, cells, rows on one side only, outcome, sentences, rule_text |
| Rule check | rule_checks.jsonl | check_id, unit_ref, target_ref, rule_as_stated, rule_kind, rule_number, located_by, outcome, where_in_code |
| Package documentation check | package_doc_checks.jsonl | check_id, unit_ref, about_ref, check, outcome, detail |
| Unit status | unit_status.jsonl | unit_ref, corner, status, clean, decided_by_rule, reason_shown, item_ids, cells |
| Flagged item | flagged_items.jsonl | item_id, category, concerns, unit_refs, item, observed, the three side-by-side texts, suggested_next_step, evidence_path, from_checks |
| Determination | determinations.jsonl | item_id, decision, reviewer, role, rationale, recorded_at, recorded_by, workbook_sha256, prev_hash, record_hash |

## 21. Skills and the pipeline

A skill is the written contract of one step (`engine/skills/<name>/SKILL.md`: purpose, inputs, outputs, procedure, quality rules, what it never does). `engine/pipeline.yaml` lists the steps in order; each names its skill and one plain function from the explicit dictionary in `aiva5_run_report.py`. There is no loading of scripts by path, and the runner refuses to start when a SKILL.md version differs from the version its bundle declares.

| Step | Skill | Version | Carried out by | What it does |
|---|---|---|---|---|
| 01 | prepare-run | 0.0.1 | aiva5_run_report.prepare_run | Fingerprints the inputs and opens the run record. Use as the first step of every review run. |
| 02 | read-methodology | 0.0.1 | aiva1_documents.read_methodology | Reads the canonical methodology into citable chunks with their full heading chain. Use as the first reading step of a review run. |
| 03 | read-documentation | 0.0.1 | aiva1_documents.read_documentation | Reads the model documentation into citable chunks and marks which ones state something checkable. Use after read-methodology. |
| 04 | read-package | 0.0.1 | aiva2_package.read_package | Reads the R package statically into model units: code, roxygen blocks, help pages, tests and stored parameter data. Use after the documents are read. |
| 05 | build-graph | 0.0.1 | aiva3_mapping.build_graph | Builds the append-only graph of chunks, model units and anchors, and harvests the bridge vocabulary. Use after all three corners are read. |
| 06 | find-candidates | 0.0.1 | aiva3_mapping.find_candidates | Proposes, for every unit and target corner, a short list of passages with a plain reason. Use before each judge-links pass. |
| 07 | confirm-outline | 0.0.1 | a person | A person confirms that Level and Section on Chunks_Canon match the methodology's own outline. Use before any chat() call is spent. |
| 08 | judge-links | 0.0.1 | aiva3_mapping.judge_links | Asks the language model narrow, lettered questions about one unit and its shortlist, and validates every answer by code. Use after find-candidates. |
| 09 | find-candidates | 0.0.1 | aiva3_mapping.find_candidates | Proposes, for every unit and target corner, a short list of passages with a plain reason. Use before each judge-links pass. |
| 10 | judge-links | 0.0.1 | aiva3_mapping.judge_links | Asks the language model narrow, lettered questions about one unit and its shortlist, and validates every answer by code. Use after find-candidates. |
| 11 | check-mathematics | 0.0.1 | aiva4_checks.check_mathematics | Compares linked formulas symbolically and numerically. Use after judge-links. |
| 12 | check-values | 0.0.1 | aiva4_checks.check_values | Compares stored and stated values with the methodology under one displayed precision rule. Use after judge-links. |
| 13 | check-rules | 0.0.1 | aiva4_checks.check_rules | Checks that conditions, floors, caps and thresholds stated in linked passages are present in the code. Use after judge-links. |
| 14 | check-package-docs | 0.0.1 | aiva4_checks.check_package_docs | Checks roxygen blocks and help pages against the code, without the language model. Use after read-package. |
| 15 | account-coverage | 0.0.1 | aiva4_checks.account_coverage | Gives every unit exactly one status, raises the flagged items and checks the coverage identity. Use after all checks. |
| 16 | await-determinations | 0.0.1 | a person | Reviewers fill the four yellow columns on Flagged_Items and upload the workbook. Use when the run pauses after account-coverage. |
| 17 | record-determinations | 0.0.1 | aiva5_run_report.record_determinations | Reads the yellow cells of the uploaded workbook and appends hash-chained determination records. Use after an upload. |
| 18 | build-report | 0.0.1 | aiva5_run_report.build_report | Builds Validation_Report.docx, the final Output.xlsx and the graph exports from the audit records. Use whenever flagged items exist. |

**Design rules and the functions that enforce them** (from the "Enforces:" lines of the docstrings):

| Rule | Enforced in |
|---|---|
| R1 | `aiva0_shared.has_banned_wording`, `aiva4_checks.build_items`, `aiva4_checks.account_coverage`, `aiva5_run_report.quoted`, `aiva5_run_report.plain_cell`, `aiva5_run_report.build_report_file` |
| R2 | `aiva1_documents.not_read_block`, `aiva1_documents.blocks_to_chunks`, `aiva2_package.parse_r_source`, `aiva2_package.units_from_r_source`, `aiva2_package.read_package`, `aiva3_mapping.find_candidates`, `aiva4_checks.check_identity`, `aiva4_checks.account_coverage`, `aiva5_run_report.rows_coverage` |
| R3 | `aiva3_mapping.validate_answer`, `aiva3_mapping.judge_links`, `aiva4_checks.compare_formulas`, `aiva4_checks.check_mathematics`, `aiva4_checks.check_values`, `aiva5_run_report.ask_one`, `aiva5_run_report.make_asker` |
| R4 | `aiva0_shared.content_hash`, `aiva0_shared.chain_records`, `aiva1_documents.blocks_to_chunks`, `aiva3_mapping.ledger_records`, `aiva3_mapping.judge_links`, `aiva4_checks.numeric_step`, `aiva4_checks.compare_formulas`, `aiva4_checks.check_mathematics`, `aiva5_run_report.record_determinations` |
| R5 | `aiva0_shared.canonical_json`, `aiva0_shared.chain_records`, `aiva2_package.read_package`, `aiva3_mapping.ledger_records`, `aiva3_mapping.ranked`, `aiva3_mapping.fuse`, `aiva3_mapping.assemble_question`, `aiva4_checks.sample_points`, `aiva5_run_report.run_batch`, `aiva5_run_report.make_asker`, `aiva5_run_report.replay_chat` |
| R6 | `aiva1_documents.read_file_blocks`, `aiva2_package.unpack_package`, `aiva5_run_report.open_run`, `aiva5_run_report.rebuild_outputs` |
| R7 | `aiva1_documents.parse_formula`, `aiva2_package.parse_r_source`, `aiva2_package.to_expr`, `aiva2_package.decode_data_file`, `aiva4_checks.to_sympy`, `aiva4_checks.evaluate` |
| R8 | `aiva5_run_report.make_settings`, `aiva5_run_report.LiveValues` |
| R9 | `aiva3_mapping.load_word_lists` |
| R10 | `aiva0_shared.plain_number`, `aiva5_run_report.plain_cell`, `aiva5_run_report.build_report_file` |
| R11 | `aiva5_run_report.load_pipeline` |
| R12 | `aiva5_run_report.copy_whole`, `aiva5_run_report.rebuild_outputs`, `aiva5_run_report.record_determinations` |

## 22. Settings

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
| `signals` | ['fields', 'bridge', 'references', 'anchors', 'signatures', 'propagation'] | The search signals in use; the ablation ladder of tools/recall_at_k.py switches them off one by one. |

## 23. The files in _audit

| File | Content |
|---|---|
| run_manifest.json | model ID, dates, engine version, every input with its SHA-256, what changed since the previous run, who confirmed the outline, hashes of the last workbook written and the last workbook read in |
| run_log.txt | one line per event; texts that were withheld from cells |
| step_records.jsonl | one record per finished step: skill, version, counts, notes, seconds |
| chunks_canon.jsonl, chunks_doc.jsonl, outline.jsonl, read_repairs.jsonl, info_rows.jsonl | what the document reader produced |
| model_units.jsonl, parameter_tables.jsonl, package_info.json | what the package reader produced |
| graph_ledger.jsonl, bridge_vocabulary.jsonl, unresolved_references.jsonl | the graph and what was harvested for the search |
| candidates.jsonl, search_records.jsonl | the search stage |
| llm_calls_001.jsonl.gz and following | every exchange with `chat()`, every attempt, with the token removed |
| judgement_problems.jsonl, doc_judgements.jsonl, second_opinions.jsonl | what the judge step recorded besides links |
| math_checks.jsonl, value_checks.jsonl, rule_checks.jsonl, package_doc_checks.jsonl | the deterministic checks |
| unit_status.jsonl, flagged_items.jsonl, coverage.json | the accounting |
| determinations.jsonl, uploads/ | the human half |
| exports/nodes.csv, exports/edges.csv, exports/graph.graphml | the graph for loading elsewhere |
| Run_Summary.docx | where the run stands, refreshed after every step |

## 24. Prompts

One template per question type under `engine/references/prompts/`; each has a version line, a SYSTEM part and a MAIN part with slots. Every prompt has one purpose, names no domain concept, shows passages under letters in an order derived from a hash, and asks for one JSON object with a closed set of fields.

| Question type | Version | The one task of the prompt |
|---|---|---|
| align-symbols | VERSION 1 | Which symbol of the code stands for which symbol of the equation? |
| check-rule | VERSION 1 | Does the code apply the rule as stated? |
| judge-doc-to-canon | VERSION 1 | Which passages of the methodology, if any, does this passage of the documentation correspond to, and how? |
| judge-doc-to-model | VERSION 1 | Which units of the package, if any, does this passage of the documentation describe, and how? |
| judge-unit-to-canon | VERSION 1 | Which passages of the methodology, if any, does this unit of the package correspond to, and how? |
| judge-unit-to-doc | VERSION 1 | Which passages of the documentation, if any, describe this unit of the package, and how? |
| map-table-columns | VERSION 1 | Which lettered table, if any, states the same values as the package table, which column is which, and which column identifies a row? |
| read-formula-from-prose | VERSION 1 | Write the formula that this paragraph states, as one line of the form name = expression. |
| second-opinion | VERSION 1 | Identify any difference between what the unit does or states and what the passages state. |

## 25. Tests and sample projects

Run everything with `python -m unittest discover -s engine/tests`.

| Test file | Tests | What it covers |
|---|---|---|
| `test_aiva0_shared.py` | 19 | Tests of aiva0_shared.py: contracts, canonical JSON, hashes, numbers, symbols, the expression tree. |
| `test_aiva1_documents.py` | 17 | Tests of aiva1_documents: reading methodology and documentation files of every supported form. |
| `test_aiva2_package.py` | 12 | Tests of aiva2_package: safe unpacking, the R reader, documentation units and stored data. |
| `test_aiva3_mapping.py` | 20 | Tests of aiva3_mapping: the ledger, the deterministic search signals, questions and validators. |
| `test_aiva4_checks.py` | 27 | Tests of aiva4_checks: the value rule, formula comparison, tables, rules, statuses and the identity. |
| `test_aiva5_run_report.py` | 16 | Tests of aiva5_run_report.py: the wrapper around chat(), the store, paths, the runner, Output.xlsx. |
| `test_docs.py` | 4 | The manual, the skills and the release manifest must agree with the code (plan, Phases 11 and 12). |
| `test_end_to_end.py` | 14 | End-to-end tests on the sample projects: sameness of two runs, the human round trip, the report, the wording of everything an analyst reads, replay, and verification of a run folder. |
| `test_layout_rules.py` | 7 | Rules that hold for the whole engine: one-way imports, line budgets, plain code, no execution of input text (R7), and the wording lint, static and dynamic (R1, R10). |
| `test_notebook.py` | 1 | The notebook's cells are run here, outside Databricks, against a stand-in for dbutils, so that a change in the engine that would break a cell is seen before an analyst sees it. |

Sample projects under `engine/tests/sample_projects/`, all invented and rebuilt byte for byte by `tools/build_samples.py`: `A_minimal` (a neutral parcel-pricing method; XML, a Word file, four help pages), `F_capital` (XML inside a `.txt` file with four levels and a flat-numbered annex; equations as MathML, inline notation, a sentence and an image; stored tables as `.rda` and `.rds`; a help page that is out of step on purpose; a Word file and a PDF), `F_capital_known` (the same with six seeded differences, listed in its `expected_items.csv`) and `D_dosing` (another field, to keep the engine honest about rule R9; Word's web export with preserved equation markup; PDF-only documentation). Each sample has hand-made gold files: `gold_links.csv`, `gold_not_checkable.csv`, `gold_clean_units.csv`.

## 26. Extending AIVA safely

| You want to add | Where | What must be re-evaluated |
|---|---|---|
| a tag rule for a new XML schema | `Inputs/tag_rules.yaml` of the project, or `engine/references/tag_rules.yaml` | `test_aiva1_documents.py`; the outline of one real document |
| an R function the comparison should understand | `engine/references/r_function_map.yaml` (neutral name, arguments, domain), `aiva4_checks.to_sympy` and `aiva4_checks.evaluate` | `test_aiva4_checks.py` with new pairs in `engine/tests/equivalence_corpus.yaml`; Reviewer 2 and Reviewer 4 agree the entry |
| a question type | a prompt under `engine/references/prompts/`, a validator branch in `aiva3_mapping.validate_narrow`, a handler in the stand-in | the bad-answers corpus; the token budget for the largest unit |
| a category | the constants of `aiva0_shared.py`, `aiva4_checks.NEXT_STEPS`, Appendix B | the wording lint; the identity tests |
| a search signal | `aiva3_mapping.search_one`, `aiva3_mapping.REASON_TEMPLATES`, the `signals` setting | `tools/recall_at_k.py`: the signal must earn its place on the ablation ladder |

After any change: the whole test suite, `tools/check_docs.py`, `tools/build_manual.py`, the harness (`tools/run_harness.py`), and a new `docs/release_manifest.json` from `tools/make_release_manifest.py`.

## 27. How AIVA was evaluated

The evaluation dossier is `docs/AIVA_0.0.1_Evaluation_Dossier.md`. In short, with the stand-in `chat()` on invented samples: the equivalence corpus of 100 formula pairs (no differing pair is ever reported as agreeing); the seeded-difference harness (`evaluation/harness_F_capital.md`); the recall ladder of the search stage (`evaluation/relatedness_report.md`); the six seeded differences of `F_capital_known`; reproducibility by replay. What is still to be done with the real model on a real package, by the owner, is listed there as well.

**Line counts.** The plan asks for at least 30 percent of each file to be docstrings, comments and overview. The files are below that share; the numbers are reported here as they are.

| File | Lines | Budget | Docstrings and comments |
|---|---|---|---|
| aiva0_shared.py | 450 | 450 | 23% |
| aiva1_documents.py | 1181 | 1500 | 15% |
| aiva2_package.py | 1285 | 1500 | 13% |
| aiva3_mapping.py | 1123 | 1500 | 18% |
| aiva4_checks.py | 1380 | 1500 | 14% |
| aiva5_run_report.py | 1347 | 1500 | 14% |

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

# Appendices

## Appendix A. Vocabulary

Every word AIVA can show in a status, a relation or a "how established" cell comes from one list in `aiva0_shared.py`. The tables are generated from it.

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
| it uses operations AIVA cannot evaluate |
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

## Appendix B. Categories and decision words

**Concerns:** Model code, Parameter data, Package documentation, Model documentation.

| Category | Suggested next step, as shown |
|---|---|
| Code differs from methodology | Compare the code with the cited passage, starting from the inputs shown under What was observed. |
| Code not traced to methodology | Decide whether this code implements a part of the methodology; if so, name the passage. |
| Mathematical check undecided | Compare the formula in the code with the cited passage by hand; AIVA could not decide it. |
| Value differs from methodology | Compare the listed rows of the package table with the cited table of the methodology. |
| Hard-coded number not traced | Find where the methodology states this number, or confirm that it needs no statement. |
| Parameter data not traced | Decide which table of the methodology this stored object corresponds to, if any. |
| Parameter data not described | Check whether the stored object and each of its columns should be described in the package. |
| Package documentation differs from code | Compare the roxygen block or help page with the function it documents. |
| Package documentation differs from methodology | Compare the value stated in the package documentation with the cited passage. |
| Documentation statement not traced | Decide which passage of the methodology this statement of the documentation rests on, if any. |
| Documentation differs from methodology | Compare the statement in the documentation with the cited passage of the methodology. |
| Documentation differs from code | Compare the statement in the documentation with the cited unit of the package. |
| Item could not be read or assessed | Review this item by hand; AIVA could not read or assess it. |
| AI answer could not be used | Review this unit by hand, or run AIVA again; the AI's answer could not be used. |
| AI answers disagree | Read both quotations and decide whether the unit and the passage state the same thing. |

**Decision words:** *Requires action*, *No action needed*. A cleared decision is recorded as *Withdrawn*; an item without an active decision is *Open*.

## Appendix C. Code index

Generated from the source: every function and class of the engine with its line number and the first sentence of its docstring.

**aiva0_shared.py**

| Name | Line | Kind | What it does |
|---|---|---|---|
| `has_banned_wording` | 113 | function | Return the first word in `text` that AIVA's own wording may not use, or "". |
| `TableData` | 120 | class | A table kept whole: header cells, body rows, and which column identifies a row. |
| `EquationData` | 125 | class | An equation as found: its source form, whether AIVA could read it, and its tree. |
| `Chunk` | 131 | class | One citable unit of a document: a paragraph, a table, a figure or an equation. |
| `CodeDetail` | 140 | class | What the R reader learned about a function or a statement, without running it. |
| `ParameterDataDetail` | 148 | class | The profile of one stored data object. |
| `RoxygenDetail` | 156 | class | A roxygen block: what it documents, its tags with their lines, and its formulas. |
| `HelpPageDetail` | 162 | class | A help page as read from its macro format. |
| `ModelUnit` | 168 | class | One citable unit of the package (see UNIT_KINDS). |
| `Provenance` | 177 | class | Which run, step and skill produced a record, and from which AI exchange if any. |
| `Edge` | 183 | class | A recorded connection between two nodes of the graph. |
| `Candidate` | 190 | class | A passage the search stage proposes for a unit, with the reason in plain words. |
| `FlaggedItem` | 197 | class | Something AIVA could not line up, raised for a person. |
| `Determination` | 204 | class | A named person's recorded decision on one flagged item. |
| `StepContext` | 210 | class | What every step function receives. |
| `StepResult` | 216 | class | What every step function returns: records by kind, counts, and plain notes. |
| `to_plain` | 222 | function | Turn dataclasses, tuples and Decimals into plain JSON-ready values. |
| `canonical_json` | 234 | function | One JSON text per content: sorted keys, no spare white space. |
| `sha256_bytes` | 238 | function | SHA-256 of bytes, in hexadecimal. |
| `sha256_text` | 241 | function | SHA-256 of a text in UTF-8, in hexadecimal. |
| `swhid_content` | 244 | function | The ISO/IEC 18670 content identifier of a file; the same value Git computes. |
| `normalise_text` | 248 | function | Unicode NFC, one kind of line ending, runs of white space collapsed to one space. |
| `content_hash` | 253 | function | The hash that makes a citation re-verifiable. |
| `make_ref` | 258 | function | make_ref("C", 9) gives "C-0009". |
| `strip_volatile` | 262 | function | A copy of a record without the named keys, at any depth (time stamps, run id). |
| `chain_records` | 270 | function | Give each record the hash of the one before it and its own hash. |
| `verify_chain` | 282 | function | Re-compute a chain. |
| `chain_head` | 293 | function | The hash of the last record of a chain, or the fixed starting value for an empty one. |
| `parse_number` | 305 | function | Bring one written number to a decimal value and keep how it was written. |
| `plain_decimal` | 327 | function | A Decimal as the shortest plain decimal text: no exponent, no trailing zeros. |
| `find_numbers` | 332 | function | All numbers written in a piece of prose, with their position. |
| `plain_number` | 351 | function | How a computed value is shown to an analyst: whole numbers stay whole, other values show at most six significant digits, never an exponent. |
| `normalise_symbol` | 373 | function | One form for a symbol however it was written: the Greek letter by name, by character or in LaTeX form; a subscript written PD_i, PD[i], PD_{i} or with a subscript character. |
| `Expr` | 397 | class | AIVA's neutral tree for a formula. |
| `expr_from_dict` | 404 | function | Rebuild a tree that was read back from _audit as plain JSON. |
| `expr_walk` | 412 | function | Every node of a tree, parents before children. |
| `expr_symbols` | 418 | function | The distinct symbols of a tree, in order of first appearance. |
| `expr_to_text` | 428 | function | The tree in AIVA's linear notation, the form shown to analysts and to the AI. |

**aiva1_documents.py**

| Name | Line | Kind | What it does |
|---|---|---|---|
| `NotReadable` | 56 | class | A formula or a file that AIVA cannot read. |
| `load_notation` | 68 | function | The names AIVA reads as functions in a written formula, from r_function_map.yaml. |
| `tokenize_formula` | 73 | function | Cut a written formula into numbers, names and signs. |
| `FormulaReader` | 94 | class | A small recursive-descent reader over the tokens of one formula. |
| `FormulaReader.__init__` | 99 | function |  |
| `FormulaReader.peek` | 103 | function | The token at the reading position (or further on), without taking it. |
| `FormulaReader.take` | 108 | function | Take the next token; with `sign`, insist that it is that sign. |
| `FormulaReader.statement` | 116 | function | A whole formula: an expression, or `left = right`. |
| `FormulaReader.comparison` | 126 | function | An expression, optionally compared with another one. |
| `FormulaReader.sum` | 134 | function | Terms joined by + and -, from left to right. |
| `FormulaReader.product` | 142 | function | Factors joined by * and /, from left to right; juxtaposition only where the source allows it. |
| `FormulaReader.term_follows` | 154 | function | Does another factor start here without a sign in between? |
| `FormulaReader.unary` | 159 | function | A leading minus or plus. |
| `FormulaReader.power` | 169 | function | A base with an optional power (right-associative), an inverse-function mark or a percent sign. |
| `FormulaReader.minus_one_follows` | 180 | function | Is the next thing ^-1 or ^(-1) followed by an opening bracket? |
| `FormulaReader.atom` | 189 | function | A number, a symbol, a function call or a bracketed expression. |
| `parse_formula` | 222 | function | Read a formula written in linear notation into AIVA's expression tree. |
| `read_equation` | 234 | function | Build the EquationData of a chunk: readable with its tree, or not readable with the reason. |
| `inline_formula` | 248 | function | A formula written inside running text, such as "K = LGD * N(x)". |
| `local_name` | 265 | function | '{namespace}oMath' and 'm:oMath' both become 'omath'. |
| `attribute` | 271 | function | The value of an attribute, whatever namespace prefix it carries. |
| `child_named` | 278 | function | The first child with this local tag name, or None. |
| `bracketed` | 285 | function | Put brackets around a part unless it is one number, one symbol or one call. |
| `math_to_linear` | 297 | function | Office Math (OMML) and MathML to linear notation, by the local names of the elements: fractions, powers, subscripts, roots, brackets and function application. |
| `math_children` | 352 | function | The linear text of all children, in order. |
| `strip_outer_brackets` | 364 | function | Remove one pair of brackets that encloses the whole text. |
| `latex_group` | 374 | function | The content of the {...} group that starts at `position`, and the position after it. |
| `latex_to_linear` | 388 | function | The LaTeX subset found in roxygen \eqn{} and \deqn{} and in some XML, to linear notation: \frac, \sqrt, ^{}, _{}, Greek letters, \cdot, \times, \left, \right, text wrappers. |
| `detect_format` | 434 | function | The format of a file from its first bytes, whatever its extension says. |
| `decode_text` | 448 | function | Bytes to text: a byte-order mark or a declared encoding decides, then UTF-8, then Latin-1. |
| `repair_markup` | 460 | function | The repairs AIVA makes before strict parsing. |
| `TolerantReader` | 507 | class | Builds the same kind of element tree as the strict XML parser, from start, end and text events of the standard library's HTML parser. |
| `TolerantReader.__init__` | 513 | function |  |
| `TolerantReader.handle_starttag` | 518 | function | Open an element, first closing what HTML closes implicitly. |
| `TolerantReader.handle_startendtag` | 528 | function | An element written as empty: opened and closed at once. |
| `TolerantReader.handle_endtag` | 533 | function | Close the nearest open element of this name; a stray end tag is recorded as a repair. |
| `TolerantReader.handle_data` | 543 | function | Text between tags. |
| `TolerantReader.handle_comment` | 547 | function | Keep equation markup that Word's web export hides in conditional comments; drop other comments. |
| `TolerantReader.feed_inner` | 555 | function | Read preserved equation markup found inside a comment into the tree being built. |
| `TolerantReader.copy_children` | 564 | function | Copy an element read elsewhere into the tree being built. |
| `TolerantReader.finish` | 575 | function | Close whatever is still open and return the root element. |
| `parse_markup` | 583 | function | Strict XML parsing first; when that still fails after the repairs, the tolerant reader. |
| `load_tag_rules` | 598 | function | The default tag rules, with any part replaced by the project's own Inputs/tag_rules.yaml. |
| `element_text` | 616 | function | The running text of an element without the text of figures, equations and captions in it. |
| `new_block` | 625 | function | One block of a document before numbering: kind, text, where it was found, and what its kind needs. |
| `not_read_block` | 633 | function | A whole file, or a part, that could not be read still becomes one block. |
| `WalkState` | 638 | class | What the walker carries along: the rules, the notation, images by name, and the report of tags it met that are in no family. |
| `walk_element` | 644 | function | Turn one element and everything below it into blocks, in reading order. |
| `walk_mixed` | 683 | function | An element that may hold both running text and blocks. |
| `table_block` | 708 | function | A table is always one block: header cells, body rows and its caption stay together. |
| `table_from_rows` | 722 | function | The one-cell display form of a table: cells joined by "; ", one row per line, header first. |
| `figure_block` | 738 | function | A figure: never read, kept with its caption or alternative text and the fingerprint of the image. |
| `equation_block` | 751 | function | An equation element: MathML or Office Math is converted; LaTeX or linear text is read as written; an equation that is only a picture stays an Equation chunk that could not be read. |
| `blocks_from_markup` | 773 | function | XML or HTML text to blocks: parse (repairing where needed), then walk the tree by the tag rules. |
| `blocks_from_mhtml` | 780 | function | Parts are read with the standard `email` package. |
| `word_value` | 809 | function | The value of a Word property such as a style id or an outline level, or None. |
| `docx_paragraph_facts` | 814 | function | Heading level (from the style name or the outline level, following based-on styles) and whether Word numbers this paragraph automatically. |
| `docx_paragraph_parts` | 834 | function | The text of a paragraph with its formulas in place, its formulas, and its pictures. |
| `docx_figure` | 850 | function | A picture in a Word file as a figure block with the fingerprint of the embedded image. |
| `safe_xml` | 862 | function | Parse one XML part of an Office file. |
| `blocks_from_docx` | 868 | function | Body elements in document order, so that tables stay where they are. |
| `blocks_from_pdf` | 927 | function | PDF keeps no structure, so this reader is the weakest (the manual says so and recommends .docx where both exist). |
| `blocks_from_pdf_text_only` | 986 | function | The fallback PDF reader: page texts as paragraphs, when the layout-aware reader cannot open the file. |
| `first_numbering` | 1002 | function | The numbering at the start of a heading as written, and the name of its scheme. |
| `infer_levels` | 1010 | function | Give every heading its level. |
| `cross_references` | 1042 | function | Cross-references as written: "Table 3", "section 4.2", "Annex A". |
| `states_something_checkable` | 1048 | function | Does a documentation passage state something that can be checked against the methodology or the code: a number, a formula, a table, or a phrase from the rules file? |
| `blocks_to_chunks` | 1062 | function | Blocks to chunks. |
| `block_is_under_reconstructed` | 1097 | function | Was the numbering of the heading directly above this block reconstructed by counting? |
| `outline_lines` | 1107 | function | The indented outline an analyst compares with the document's own table of contents: one line per section, with its range of references and the number of units in it. |
| `read_file_blocks` | 1124 | function | One input file to blocks, by the format found in its content. |
| `read_corner` | 1143 | function | Read every file of one corner, in file-name order, into chunks numbered in reading order. |
| `read_methodology` | 1175 | function | Step 02, skill read-methodology: the canonical methodology into chunks C-0001, C-0002, ... |
| `read_documentation` | 1179 | function | Step 03, skill read-documentation: the model documentation into chunks D-0001, D-0002, ... |

**aiva2_package.py**

| Name | Line | Kind | What it does |
|---|---|---|---|
| `NotParsed` | 54 | class | One R expression that AIVA's reader could not read. |
| `unpack_package` | 58 | function | Read the tarball member by member, into memory, never onto disk by path. |
| `strip_top_folder` | 78 | function | R tarballs hold one top folder named after the package; paths are shown without it. |
| `read_description` | 85 | function | The fields of DESCRIPTION (name: value, continuation lines start with white space). |
| `read_namespace` | 96 | function | Exported names and export patterns from NAMESPACE. |
| `is_exported` | 108 | function | Is `name` exported by this NAMESPACE (by name, by pattern or as an S3 method)? |
| `Token` | 116 | class | One token of R source: kind is num, str, name, op, newline or end. |
| `tokenize_r` | 134 | function | R source to tokens. |
| `Node` | 170 | class | One node of the syntax tree. |
| `RParser` | 186 | class | Precedence climbing over R's documented operator table (?Syntax). |
| `RParser.__init__` | 190 | function |  |
| `RParser.peek` | 193 | function | The token at the reading position, without taking it. |
| `RParser.take` | 199 | function | Take the next token; with `text`, insist that it is that token. |
| `RParser.skip_newlines` | 208 | function | Skip line ends where R allows an expression to go on. |
| `RParser.is_op` | 213 | function | Is the next token one of these operators? |
| `RParser.expression` | 218 | function | Operator-precedence parsing of one expression; `minimum` is the weakest binding still accepted. |
| `RParser.finish_paren` | 243 | function | A bracketed expression, after its opening bracket. |
| `RParser.prefix` | 251 | function | What an expression can start with: a literal, a name, a unary sign, a bracket, a block or a keyword. |
| `RParser.block` | 276 | function | The expressions between curly brackets. |
| `RParser.condition` | 292 | function | The bracketed condition of if and while. |
| `RParser.keyword` | 302 | function | if, for, while, repeat, function and the other reserved words. |
| `RParser.function` | 339 | function | A function definition: its formal arguments with their defaults as written, and its body. |
| `RParser.call_or_index` | 362 | function | Calls and the three kinds of indexing that may follow an expression. |
| `parse_r_source` | 396 | function | Parse a file ONE top-level expression at a time. |
| `CannotConvert` | 440 | class | A piece of code that cannot become a formula tree. |
| `walk` | 443 | function | Every node of a tree, parents first. |
| `callee_name` | 449 | function | The name of the function a call node calls: f(...) and pkg::f(...) both give "f". |
| `assignment_parts` | 456 | function | (target, value) when the node is an assignment, whichever arrow it uses; else None. |
| `number_token` | 463 | function | A number as written in the code, brought to one form, with its line. |
| `unparse` | 471 | function | The tree back as short R-like text: used to show defaults and conditions as written. |
| `has_arithmetic` | 497 | function | Does this code compute something: arithmetic, a mathematical function, a comparison with a number, or a number that is not on the list of trivial ones? |
| `code_facts` | 520 | function | Calls, symbols read and written, numbers and strings of a piece of code, in order of appearance. |
| `to_expr` | 558 | function | One R expression to AIVA's neutral formula tree, through r_function_map.yaml. |
| `call_to_expr` | 591 | function | A call in R to the neutral expression tree, through r_function_map.yaml; anything else cannot be converted. |
| `is_guard` | 619 | function | An argument check that does not change the value: stop(...), stopifnot(...), or an `if` without `else` whose body only holds such calls. |
| `compose_function` | 629 | function | The value a straight-line function returns, as one formula in its arguments: local assignments are substituted in order. |
| `draft` | 653 | function | A unit before it has its reference. |
| `code_detail` | 661 | function | The facts about a piece of code that later steps use: symbols, numbers, calls, strings, expression. |
| `formula_statements` | 667 | function | The formula statements inside one function: assignments, return(...) calls and the last expression, when they compute something. |
| `function_units` | 712 | function | A function, the formula statements inside it, and any functions defined inside it. |
| `statement_units` | 737 | function | The unit(s) of one top-level expression. |
| `units_from_r_source` | 760 | function | All units of one R file: roxygen blocks, functions, formula statements, test blocks, top-level statements, and a "File not read" unit for each expression that could not be parsed. |
| `braces_content` | 796 | function | The content of the {...} that starts at `position` (nested braces allowed), and the position after it. |
| `roxygen_units` | 810 | function | Consecutive #' lines form one block. |
| `help_page_unit` | 858 | function | A help page (.Rd): name, aliases, title, usage and arguments, read from the macro format with nested braces; % starts a comment. |
| `vignette_units` | 883 | function | A vignette: prose becomes "Vignette text" units, one per stretch between code chunks; code chunks are read as R code (and never run). |
| `expand` | 907 | function | Undo gzip, bzip2 or xz compression, recognised from the first bytes and never from the extension, and stop when the content grows beyond the cap. |
| `cell_text` | 919 | function | One stored value as its canonical text: numbers as the shortest decimal that gives the same stored value back, missing values as NA, logical values as TRUE/FALSE, dates in ISO form. |
| `table_of` | 943 | function | A decoded object as a table: (header, rows of canonical cell texts, column types, R-side description), or None when the object has no tabular meaning. |
| `column_kind` | 998 | function | Is a column made of numbers, of text, or of both? |
| `row_key_columns` | 1007 | function | How a row is identified: real row names if present; otherwise the left-most single column, or the smallest left-most combination of up to three non-numeric columns, whose values are unique; otherwise the row number. |
| `table_display` | 1022 | function | The one-cell display form: at most 50 rows, always below Excel's limit for one cell. |
| `data_object_unit` | 1030 | function | One stored object to a unit and, when it is assessable, its full values. |
| `decode_data_file` | 1056 | function | Decode one stored-data file without R. |
| `data_object_unit_from_rows` | 1093 | function | A unit for a table given as header and rows (delimited text files under data/ or inst/extdata/). |
| `data_reads` | 1101 | function | Where a function reads stored data, and how the code shows it: a bare symbol that is neither an argument nor assigned in the function; data("x"); readRDS(...) or load(...) with a literal file name; pkg::x; get("x"). |
| `is_data_file` | 1136 | function | Does this path name a stored-data file that AIVA decodes? |
| `is_parsed_r_file` | 1143 | function | Is this an R source file in a folder whose code AIVA parses? |
| `file_units` | 1147 | function | The units of one file of the package, by where it lies and what it is. |
| `link_documentation_units` | 1170 | function | Tie each roxygen block to the object it documents and each help page to the block that generated it (by name and aliases), and say whether the page is still in step with it. |
| `finalise_units` | 1193 | function | Give every draft its reference, in reading order, and turn keys into references. |
| `package_rows` | 1214 | function | The package lines of Model_Package_Info. |
| `read_package` | 1233 | function | Step 04, skill read-package. |

**aiva3_mapping.py**

| Name | Line | Kind | What it does |
|---|---|---|---|
| `node_record` | 59 | function | The ledger record of one node. |
| `ledger_records` | 63 | function | Chain new records onto the ledger. |
| `verify_ledger` | 74 | function | True when no record of the ledger was edited, removed or re-ordered. |
| `graph_version_id` | 78 | function | G- and the first twelve characters of the ledger's head hash. |
| `load_graph` | 82 | function | The ledger as two adjacency dictionaries: outgoing and incoming edges per node. |
| `find_path` | 93 | function | Breadth-first walk over typed edges in either direction, at most `max_hops` long. |
| `links_of` | 111 | function | The `corresponds` edges of a unit into one corner ("C", "D" or "M"), in ledger order. |
| `load_word_lists` | 118 | function | Stop words, bridge patterns and the neutral words of mathematical functions. |
| `stem` | 129 | function | A light, rule-based stemmer: plural endings, -ing, -ed, and a doubled last letter. |
| `split_words` | 142 | function | Text or identifiers to index words: split at anything that is not a letter or digit, at underscores, dots and capital letters inside a name; lower-case; drop stop words, single characters and pure numbers; stem. |
| `shown` | 155 | function | Index words as an analyst should see them: as first written, not as stems. |
| `symbols_in` | 159 | function | Short symbols a passage uses: single letters and Greek names standing alone, short capital abbreviations, and names with a subscript. |
| `numbers_in` | 171 | function | The non-trivial numbers of a text, as normalised values ("12.5%" gives 0.125). |
| `chunk_fields` | 178 | function | The named fields of a methodology or documentation chunk (plan 2.6). |
| `unit_fields` | 189 | function | The named fields of a model unit: name words, what the package says about it (roxygen of the object or of the function it sits in), comments, symbols, numbers, the neutral words of the mathematical functions it calls, and string literals. |
| `build_index` | 218 | function | documents: {ref: {"fields": {field: [words]}}}. |
| `bm25_scores` | 233 | function | BM25 with the usual constants k1 and b. |
| `ranked` | 250 | function | References by falling score; ties break by reference. |
| `initials_match` | 255 | function | Do the letters of an abbreviation appear, in order, as initials of the long form? |
| `harvest_text` | 269 | function | Bridge entries from one text: "long form (ABBR)", "ABBR (long form)", "where X denotes ...", "let X be ...". |
| `harvest_bridge` | 290 | function | The bridge vocabulary of this project, harvested from its own inputs: documents, symbol tables, roxygen @param and @return lines, column descriptions of data blocks, comments of the form "# x: phrase", and the optional Inputs/glossary.xlsx. |
| `expansions_for` | 334 | function | The bridge entries that apply to a unit: by its symbols and by its name words. |
| `resolve_reference` | 344 | function | "Table 3", "section 4.2", "Annex B" as written, resolved among `chunks` (one corner): tables, figures and equations by the label at the start of their caption, sections by their numbering as written. |
| `anchors_of` | 363 | function | The anchors one unit or chunk mentions, as (kind, key) pairs. |
| `anchor_weights` | 374 | function | Weight of an anchor = 1 / log(1 + number of units that mention it). |
| `restart_walk` | 388 | function | A random walk over the two-sided graph of units and anchors that keeps restarting at the unit (personalised PageRank): fixed restart probability and a fixed number of rounds, so it is deterministic. |
| `formula_signature` | 424 | function | What a formula is made of, whatever its symbols are called: operators, neutral function names with their number of arguments, and non-trivial constants. |
| `overlap` | 436 | function | Weighted overlap of two multisets, between 0 and 1. |
| `table_shape_score` | 441 | function | How alike two tables are: shared header words, shared row keys and shared values at printed precision. |
| `fuse` | 464 | function | Reciprocal rank fusion: score = sum over signals of 1 / (60 + rank). |
| `reason_text` | 486 | function | The plain reason of one candidate, assembled from the signals that proposed it. |
| `structural_edges` | 493 | function | Edges the readers established: contains, calls, tested_by, documents, generated_from, reads_data. |
| `build_graph` | 524 | function | Step 05, skill build-graph: nodes for every chunk and unit, structural edges, cross-references resolved within their own corner, and the bridge vocabulary. |
| `is_searched` | 553 | function | Which model units look for passages. |
| `searched_text` | 565 | function | The "What was searched" sentence of one unit and corner. |
| `search_one` | 581 | function | All signals for one unit and one target corner, fused into a shortlist of candidates. |
| `build_world` | 642 | function | Everything the search needs, built once per step: representations of all units and chunks, one BM25 index per corner, the bridge vocabulary, anchors and the walk. |
| `propagated_candidates` | 695 | function | S5, pass 2 only. |
| `find_candidates` | 715 | function | Step 06 (pass 1) and step 08 (pass 2), skill find-candidates. |
| `load_prompt` | 744 | function | A prompt template: its version line, its SYSTEM part and its MAIN part with slots. |
| `estimate_tokens` | 752 | function | No tokenizer can be installed, so tokens are estimated from characters, on the safe side: one token per 3.2 characters of prose and per 2.5 characters of code and numbers. |
| `prompt_budget` | 757 | function | Tokens available for the main prompt: the smaller of the target size (long prompts are answered badly) and what the cap leaves after all reserves. |
| `cut_text` | 763 | function | Cut a long text to `limit` characters around the first of `keep_words` it contains (the matched region), marking the cuts; lines stay whole where possible. |
| `cut_code` | 775 | function | Cut a long function around its formula lines: the header, then every line that computes something with two lines of context, until the limit is reached. |
| `passage_text` | 795 | function | How a chunk or a unit is shown as a lettered passage. |
| `passage_label` | 808 | function | The heading line of a lettered passage: where it stands, never its reference. |
| `letters_for` | 816 | function | A, B, ... |
| `choose_decoys` | 821 | function | Planted control passages: chosen by a hash of the unit reference (never at random) from passages that share no anchor with the unit and appear nowhere in its rankings. |
| `assemble_question` | 830 | function | Put one question together. |
| `narrow_question` | 852 | function | The narrow questions of the checks (map-table-columns, align-symbols, read-formula- from-prose, check-rule): same assembly, same budget, same validators. |
| `judge_question` | 857 | function | The judge question of one unit (or documentation passage) and one target corner. |
| `Rejected` | 878 | class | An answer that cannot be used. |
| `last_json_object` | 881 | function | The last balanced {...} object in a text, or None. |
| `strict_json` | 898 | function | Strict parsing: no repair of malformed JSON, and a repeated key is refused. |
| `check_quote` | 907 | function | A quotation must be verbatim after white-space normalisation, contiguous, without an ellipsis, and of a sensible length. |
| `validate_judge` | 922 | function | The answer to a judge question: its shape, the letters it names, its quotations, planted passages, self-contradiction. |
| `validate_narrow` | 943 | function | The narrow question types. |
| `validate_answer` | 995 | function | The validators, in a fixed order: remove any thought block and code fence; take the last balanced JSON object; parse it strictly; check its shape, its letters, its quotations, the planted passages and self-contradiction. |
| `shown_ai_text` | 1024 | function | Text written by the model passes the same plain-language filter as AIVA's own wording: if it rates seriousness or uses a policy term, a fixed sentence is shown instead and the full text stays in the audit records. |
| `needs_second_opinion` | 1032 | function | `unchecked_only`: a second, oppositely framed question is asked for accepted links that no deterministic check will back, that is, passages without a formula or a table. |
| `judge_links` | 1039 | function | Steps 07 and 09, skill judge-links. |
| `second_opinions` | 1102 | function | The oppositely framed question ("identify any difference ...") for links no check can back. |

**aiva4_checks.py**

| Name | Line | Kind | What it does |
|---|---|---|---|
| `AivaDefect` | 60 | class | The run contradicts itself (the coverage identity does not hold). |
| `compare_values` | 73 | function | The value rule of plan 2.8. |
| `number_of` | 93 | function | The single number a table cell or a default holds, or None. |
| `NotEvaluable` | 99 | class | The formula uses an operation AIVA cannot evaluate. |
| `to_sympy` | 102 | function | One explicit table from AIVA's tree to SymPy objects. |
| `symbolic_step` | 128 | function | Bounded symbolic work: expand the difference always; simplify fully only for small trees; nothing for very large ones. |
| `evaluate` | 145 | function | The value of a tree at one point. |
| `unit_interval_symbols` | 189 | function | Symbols that sit under a square root, a logarithm or the inverse normal function are drawn from (0, 1), which keeps most sample points inside the domain. |
| `sample_points` | 198 | function | The sample points: a fixed, recorded seed; ranges (0, 1), (1, 10) and (-10, 10) in turn; symbols with a narrow domain always from (0, 1); symbols supplied by a stored table take its values row by row; and, on purpose, points at, just below and just above every constant that appears in a comparison, a maximum or a minimum. |
| `crossing_points` | 229 | function | Where a threshold sits on a scaled quantity, as in min(0.2, 0.01 * n), the two sides meet far outside the generic ranges (here at n = 20). |
| `numeric_step` | 267 | function | Evaluate both trees at every sample point. |
| `align` | 286 | function | Align code symbols with the symbols of the stated formula, by code only: identical normalised names; the same name apart from capital letters when that is unambiguous; then the bridge vocabulary (both described by the same words). |
| `rename` | 318 | function | The code tree written in the stated formula's symbols; defaults put in as numbers. |
| `right_side` | 326 | function | The right-hand side of an equation; an expression that is no equation is returned whole. |
| `prepare_alignment` | 330 | function | Everything about one comparison that is settled before any number is computed: the aligned pairs, the defaults put in (only where the stated formula shows that very number), and what is still left for the align-symbols question. |
| `compare_formulas` | 346 | function | Symbolic step, then numeric step, on an alignment that is already fixed. |
| `load_world` | 375 | function | Units, chunks, the graph and the latest link of every linked pair, read once per step. |
| `linked` | 392 | function | References in one corner ("C-", "D-", "M-") that `ref` is linked to, either way round. |
| `check_edge` | 398 | function | A check never rewrites a link: it appends a new edge on the same pair, which then has the last word in the workbook and in the status rules. |
| `number_text` | 406 | function | A computed number for a cell: at most six significant digits, never in Python's own notation. |
| `stated_formula` | 411 | function | The formula a passage states, as (tree, source, reason it cannot be used). |
| `code_forms` | 426 | function | The formulas a unit offers for comparison, as (tree, defaults, reference it came from). |
| `stored_values` | 441 | function | Numeric columns of stored tables, as {"object$column": [values]}, for the numeric step. |
| `math_sentence` | 451 | function | The words of one comparison, as shown in the Math check cell. |
| `combine` | 466 | function | Several forms of one unit against one formula: any form that agrees settles it; else any form that differs (with its counterexample); else it could not be decided. |
| `check_mathematics` | 475 | function | Step 11, skill check-mathematics. |
| `quote` | 578 | function | Input text is always shown visibly quoted, with its citation (same form as in aiva5). |
| `plain_key` | 583 | function | A row key or header as compared: lower case, single spaces, underscores as spaces. |
| `header_words` | 587 | function | The index words of a column header, without its unit in brackets. |
| `map_columns` | 591 | function | Columns matched by header: equal words after normalisation. |
| `as_grid` | 602 | function | The one layout rule that is supported: a table in long form (two key columns and one value column) is turned into a grid, so that it can be laid over a printed grid. |
| `reconcile` | 615 | function | Compare two tables cell by cell under the value rule. |
| `columns_by_values` | 661 | function | Match columns whose values agree with exactly one column on the other side for most keys. |
| `table_sentences` | 677 | function | The words of one table comparison, as shown in the workbook. |
| `numbers_with_context` | 691 | function | Every number of a text with the words around it (four before, three after). |
| `prose_value_lines` | 701 | function | Numbers in a documentation passage or a roxygen block against the numbers of the passages it is linked to. |
| `check_values` | 727 | function | Step 12, skill check-values: parameter tables against the tables they are linked to (a table that the judge did not link is still matched by its shape); documentation tables against methodology tables; numbers written in linked code; numbers in documentation passages and roxygen text. |
| `stated_rules` | 826 | function | Floors and caps a passage states: (kind, number, sentence), recognised by generic phrases. |
| `rule_in_trees` | 840 | function | Code looks first: a maximum (for a floor), a minimum (for a cap), a piecewise expression or a comparison that holds the stated number, written as a number or held as the default of an argument. |
| `check_rules` | 860 | function | Step 13, skill check-rules. |
| `check_package_docs` | 900 | function | Step 14, skill check-package-docs. |
| `concerns_of` | 1032 | function | Which of the four Concerns a unit falls under, from its kind. |
| `citation` | 1040 | function | How a unit or a passage is cited next to a quotation. |
| `render_path` | 1048 | function | The supporting path of an item, hop by hop, each hop with its citation (plan 2.5). |
| `gather` | 1072 | function | All check records and AI notes, grouped by the unit they belong to. |
| `ai_judged_difference` | 1093 | function | Passages the AI judge itself called deviating or inconsistent (not a check's edge). |
| `model_unit_outcome` | 1098 | function | The status rules for one model unit, top to bottom (plan 2.9). |
| `doc_unit_outcome` | 1183 | function | The status rules for one documentation unit, top to bottom (plan 2.9). |
| `lines_or` | 1238 | function | Several lines for one cell without repeats, or the fallback sentence when there is none. |
| `model_cells` | 1242 | function | The assessment cells of one row of Mapping_Model_to_Canon_and_Doc. |
| `doc_cells` | 1267 | function | The assessment cells of one row of Mapping_Doc_to_Canon_and_Model. |
| `build_items` | 1284 | function | One flagged item per unit and category; several observations of one category are listed inside one item. |
| `check_identity` | 1309 | function | The four-part identity of plan 2.9 (part 4 is completed by the workbook builder). |
| `account_coverage` | 1327 | function | Step 15, skill account-coverage: one status per unit by the ordered rules, the cells of the assessment columns, one flagged item per unit and category, the identity, and the totals that the workbook builder must reproduce by counting its rows. |

**aiva5_run_report.py**

| Name | Line | Kind | What it does |
|---|---|---|---|
| `RunPaused` | 60 | class | The run stopped on purpose and can be resumed. |
| `make_settings` | 81 | function | The settings of a run. |
| `RunPaths` | 104 | class | Where one run lives. |
| `check_model_id` | 110 | function | Return "" when the model ID is usable, otherwise a plain sentence saying why not. |
| `setup_project` | 117 | function | Create the project skeleton and say what is still missing. |
| `new_run_id` | 136 | function | Run_<date>_<HHMM>, with a letter added when that folder already exists. |
| `open_run` | 145 | function | Create or re-open a run folder and its local scratch folder. |
| `list_input_files` | 167 | function | The input files of a project, by corner, in file-name order. |
| `LiveValues` | 181 | class | The three values chat() reads when it is CALLED: endpoint, token, user id. |
| `LiveValues.update` | 189 | function | Take the latest widget values; a different token starts a new generation. |
| `LiveValues.get` | 198 | function | One live value, read at the moment chat() is called. |
| `LiveValues.token_age_minutes` | 203 | function | Minutes since the current token was pasted. |
| `LiveValues.redact` | 207 | function | Remove the current and recent token strings from any text before it is kept. |
| `copy_whole` | 217 | function | Copy one whole file: to a temporary name, then replace; a plain copy if the file system does not support replace (probe P-5). |
| `AuditStore` | 230 | class | All audit files are read and written on local disk; sync() copies changed files whole into _audit/ in the Workspace. |
| `AuditStore.path` | 236 | function | The local path of one kind of audit file. |
| `AuditStore.read` | 241 | function | Every record of one kind, in the order written. |
| `AuditStore.append` | 252 | function | Append records of one kind; the three single-object kinds are rewritten whole. |
| `AuditStore.call_files` | 262 | function | The gzip files of call records, in order. |
| `AuditStore.append_calls` | 267 | function | Call records go to gzip files that roll over at the size limit. |
| `AuditStore.read_calls` | 279 | function | Every call record of the run, in the order written. |
| `AuditStore.sync` | 287 | function | Copy every file that changed since the last sync, whole. |
| `AuditStore.restore` | 302 | function | On resume: copy the run folder's audit files back to local disk first. |
| `open_store` | 307 | function | The audit store of a run, restored from the run folder when local scratch is empty. |
| `classify_failure` | 317 | function | Sort a failure into one of three classes by the words it contains (probe P-13 matches these lists to what the real gateway returns). |
| `call_chat` | 327 | function | Call chat() once and bring the three ways a failure can surface (an exception; a dictionary that carries a status or code; a dictionary with no "answer") into one shape: (answer text or None, failure class or "", what was seen with tokens removed). |
| `AskState` | 342 | class | What the workers of one run share: the pause and stop switches, the consecutive- failure count of the circuit breaker, and the generation of the token that failed. |
| `wait_until_allowed` | 350 | function | Called before every call. |
| `ask_one` | 368 | function | Ask one question until it has a final outcome. |
| `run_batch` | 408 | function | Ask one batch of questions with a thread pool. |
| `make_asker` | 425 | function | Build ask(), the only place chat() is ever called. |
| `replay_chat` | 450 | function | A chat() that answers from the recorded answers of an earlier run. |
| `load_pipeline` | 480 | function | Read pipeline.yaml and refuse anything that is not a known skill and function. |
| `update_manifest` | 500 | function | Change fields of the run manifest and write it back. |
| `confirm_outline` | 507 | function | Record that a person has checked the outline of the methodology (notebook cell 10). |
| `human_step_open` | 515 | function | Is this human step still waiting for its person? |
| `run_pipeline` | 522 | function | Run, or resume, the pipeline. |
| `run_step` | 563 | function | Build the context, call the step function, write what it returns, record the step, rebuild the outputs and sync. |
| `record_step` | 588 | function | Leave the step record that makes a finished step visible and resume possible. |
| `log_line` | 597 | function | Technical text (exception messages, Python names) belongs in run_log.txt only. |
| `fingerprint_file` | 606 | function | Name, corner, size, SHA-256 and content identifier of one input file. |
| `prepare_run` | 613 | function | Step 01. |
| `previous_run_inputs` | 644 | function | The manifest of the latest earlier run of this project, or None. |
| `quoted` | 664 | function | Text taken from an input or from the AI is always shown visibly quoted, with its citation. |
| `plain_cell` | 670 | function | The last gate before a cell is written. |
| `lines_by_ref` | 690 | function | Several values in one cell: each on its own line, prefixed with its reference. |
| `texts_by_ref` | 694 | function | Several quoted texts in one cell, separated by a line of dashes. |
| `run_identity` | 698 | function | What ties a workbook to its run: also written into the workbook's properties. |
| `rows_package_info` | 708 | function | The rows of Model_Package_Info: identity, inputs, what was read, repairs, how values and formulas are compared, AI calls. |
| `chunk_note` | 748 | function | What a reader should know about one chunk: unreadable, how an equation was read, reconstructed numbering. |
| `rows_chunks` | 762 | function | The rows of Chunks_Canon and Chunks_Doc. |
| `unit_expression` | 772 | function | A unit's formula or arguments as shown on Chunks_Model. |
| `rows_model_units` | 785 | function | The rows of Chunks_Model. |
| `link_columns` | 799 | function | The block of columns that shows what one unit was linked to in one corner. |
| `rows_mapping` | 814 | function | One row per model unit (corner "model") or per documentation unit (corner "doc"). |
| `rows_coverage` | 844 | function | Counted from the rows actually written: the second, independent route of the coverage identity (part 4). |
| `latest_determinations` | 864 | function | The last recorded determination of every item. |
| `rows_flagged` | 871 | function | The rows of Flagged_Items with the latest determination of each item. |
| `sheet_rows` | 885 | function | The rows of all eight sheets, by sheet name. |
| `check_written_totals` | 898 | function | Identity part 4: what account-coverage counted must equal what the workbook holds. |
| `load_layout` | 912 | function | The workbook layout from references/workbook_layout.yaml. |
| `write_sheet` | 917 | function | One generic writer for all eight sheets: header row and first column frozen, filter on the header, wrapped text, no merged cells, reviewer columns yellow and unlocked. |
| `build_workbook` | 953 | function | Build Output.xlsx on local disk from the audit records. |
| `file_sha256` | 971 | function | SHA-256 of a file's bytes. |
| `progress_text` | 976 | function | Where the run stands, in one or two plain sentences. |
| `rebuild_outputs` | 985 | function | Rebuild Output.xlsx (and the report once flagged items exist) on local disk and copy them whole into Outputs/. |
| `docx_table` | 1014 | function | A plain table in a Word document, header row in bold. |
| `build_run_summary` | 1027 | function | Where the run stands, in plain words; refreshed after every step. |
| `call_statistics` | 1049 | function | The AI call statistics shown on Model_Package_Info and in the report's annex. |
| `call_plan` | 1070 | function | The call plan of one AI step, obtained by really building every question of the step (building is deterministic and cheap) without asking any. |
| `find_uploads` | 1093 | function | Every .xlsx in Outputs/ whose embedded identity matches this run, whatever it is called (the behaviour of an upload onto an existing name is not documented). |
| `read_yellow_cells` | 1116 | function | The four yellow cells of every row of Flagged_Items, found by item id and never by row position, because reviewers sort and filter. |
| `record_determinations` | 1139 | function | Step 17, skill record-determinations: find the uploaded workbook by its identity, keep a copy of its bytes in _audit/uploads/, read and validate the yellow cells, and append one record for every item whose four values changed. |
| `build_report_file` | 1192 | function | The report, in the eight parts of plan 2.11, built from the same records as the workbook. |
| `build_report` | 1260 | function | Step 18, skill build-report: the exports of the graph for anyone who wants to load it elsewhere (nodes.csv, edges.csv, graph.graphml). |
| `verify_evidence_pack` | 1285 | function | Works from a run folder and the Inputs folder alone. |

## Appendix D. Change history

| Version | Date | Change |
|---|---|---|
| 0.0.1 | 2026-09-18 | First build of all thirteen phases of the build plan: five bundles, sixteen skills, the notebook, tools, four sample projects, the test suite and this manual. Evaluated with the stand-in `chat()` only. |
