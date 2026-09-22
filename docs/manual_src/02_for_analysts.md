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

`AIVA_Interface.ipynb` is the only file you open. It has thirteen widgets: LLM endpoint, LLM token, LLM user id, model ID, project, run, Projects folder, JFrog index URL, concurrency limit, token cap, reviewer id, reviewer role and scratch folder. Leave the scratch folder empty unless AIVA says it cannot write on the driver. `cell 2` makes them all and needs nothing installed, so they can be filled in before `cell 3` installs anything.

| Cell | What it does |
|---|---|
| `cell 1` | How to use the notebook. |
| `cell 2` | **Run this first.** Makes every widget at the top of the notebook. It needs nothing installed, so the widgets are there to fill in before anything else happens. Run it again after entering the model ID to refresh the project and run lists; it installs nothing. |
| `cell 3` | Installs the packages from the index in widget `08 JFrog index URL` and restarts Python. Once per cluster start. With no URL it installs nothing and says so, rather than taking packages from an index you did not name. |
| `cell 4` | Sets the import path, loads the engine, and runs preflight: versions, a write-and-read-back test in the Projects folder, scratch space. |
| `cell 5` | **Use the latest widget values.** The only cell that reads the three LLM widgets. It prints the token's age and length, never the token. |
| `cell 6` | **Your cell**: paste your `chat()` definition. Keep the signature; read the three live values with `aiva_live(...)` when `chat()` is called. |
| `cell 7` | Self-test of `chat()`: one tiny question. It reports success or which kind of failure was seen, and measures the time per call. A switch selects the stand-in instead. |
| `cell 8` | Project setup: creates the folders and says which Inputs folder is still empty. |
| `cell 9` | Starts or resumes the run: the reading steps, without any AI. Ends with the outline of the methodology as AIVA read it. |
| `cell 10` | Confirms that you checked the outline (chapter 7). The AI steps do not start without it. |
| `cell 11` | The call plan of the two steps that ask the most: questions by type, the largest prompt against the token cap, the expected duration. Step `07a` asks one question per piece of code to fill *LLM Interpretation*; on a large package that is the larger share, and the setting `interpret_code` switches it off. |
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

{{status_rules}}

Clean statuses: *Traced to methodology*, *Supporting code (justified)*, *Unit test*, *Narrative - nothing to check*. The other four need attention, and every unit with one of them is named by at least one row of `Flagged_Items`. `Mapping_Coverage` counts the same statuses; its numbers equal what you get by filtering *Overall status* on the two mapping sheets, and AIVA stops a run in which they would not.

**The value-comparison rule** is one rule, used for parameter tables, numbers in code, numbers in roxygen text and numbers in the documentation. Its full text is on `Model_Package_Info`. In short: percent, basis points and scientific notation are converted first; a value agrees at stated precision when rounding it to the decimals of the methodology's value gives that value; there is no hidden tolerance. A cell reads like "package 0.10, methodology 0.15 (C-0017 row Retail): differs".

**The mathematical check.** For a linked function or statement and a passage that states a formula, AIVA aligns the symbols first (shown as "with rho = ρ"), then tries to show symbolically that both sides are equal, then evaluates both at 200 seeded points, including points at and around every threshold. *Differs* always comes with a counterexample: the inputs and both results. *Could not be decided* names one reason from a fixed list and is never clean.

**How to read a path.** *What was observed* on `Flagged_Items` ends with the supporting path, hop by hop: the unit, the function it sits in, the table it reads, the passage it corresponds to with how that was established, the roxygen block and documentation passage that describe it.

**The sheets and columns.** Generated from `engine/references/workbook_layout.yaml`:

{{columns}}

## 7. Confirming the methodology outline; tag rules; the glossary

Everything downstream depends on the methodology having been cut correctly. After `cell 9`, open `Chunks_Canon` and compare *Level* and *Section (heading chain)* with the methodology's own table of contents; the same outline is printed by `cell 9`. Then run `cell 10`. Your reviewer id is recorded in the run manifest and shown on `Model_Package_Info`.

If the methodology uses XML tags AIVA has not seen, it still reads them by their shape and lists them on `Model_Package_Info` as "unrecognised tag". To teach AIVA a schema, put a `tag_rules.yaml` next to the three Inputs folders, with the same keys as `engine/references/tag_rules.yaml` (which tags are headings, paragraphs, tables, rows, cells, captions, figures, equations, or to be ignored). Project rules are added to the shipped ones.

`glossary.xlsx` is optional: two columns, a term or abbreviation and its meaning. Its entries join the bridge vocabulary that AIVA harvests from the inputs themselves, which helps the search connect a code name such as `rho_a` with "asset correlation".

## 7a. How AIVA reads a file it has not seen before

Most methodology files use tags AIVA already knows, or a shape it can work out by counting: a tag that holds rows of equal width is a table, a tag that holds text is a paragraph. Where that counting runs out, AIVA can ask.

**The setting.** `agentic_reading` has two values. `off`, the default, asks nothing: the file is read by the built-in rules exactly as earlier versions read it. `rules` lets a reading step ask ONE question about a file whose shape the rules are unsure of. A file the rules read confidently costs no question at all, so on a familiar project nothing changes and nothing is spent.

**What the model is shown.** Not the file. A *shape digest*: one line per tag, with how often it occurs, how deep it sits, what it sits inside and what sits inside it, how often it carries text of its own and how long that runs, what attributes it has, how often it opens the block around it, and up to three samples of 120 characters. Every digest is recorded in the run folder, so you can see exactly what was put in front of the model.

**What it may say back.** A choice, never text. For each tag: one of five families - heading, container, paragraph, list_container, list_item. It cannot name a tag it was not shown, cannot invent a family, and has no way to ask for a tag to be skipped. Tables, rows, cells, captions, figures and equations are worked out by counting and are not its to give. **There is no field in the answer through which a word can enter or leave your document.**

**What wins over what.** In this order: a `tag_rules.yaml` you wrote beats the rules AIVA ships, which beat what AIVA proved by counting rows, which beats what the model proposes, which beats AIVA's own fallback guess. The model speaks only where AIVA was guessing, and never overrules you.

**For a package.** The same, for a tarball laid out in a way AIVA does not expect. `Model_Package_Info` will say, for example, that a file of R code in a folder AIVA does not expect was read as R source on the model's proposal. Without that it would have been one unit of running text and nothing in it could have been linked or checked.

**Turning it on, and who decides.** `agentic_reading` stays `off` until its owner has run **cell 19** once against the real model: run cells 5 and 6 as for any run, then cell 19. It reads every sample project twice, off and on, asks about ten questions in all, and writes `evaluation/reading_report_<date>.md` with four tests - nothing lost or added, never worse than without guidance, the settled samples unchanged, and every question answered and accepted first time. If all four hold, the owner may change the setting. Cell 19 changes nothing itself. A run against the stand-in is not evidence about a model: rehearsed against a stand-in that misbehaves, the first three tests still held and the fourth did not, which is the difference between guidance that is safe and guidance that is ready.

**What you must check, at cell 10.** Where a proposal changed the reading, `Model_Package_Info` names the tag, what it was read as, and what the built-in rules would have read it as. Read those rows before you confirm the outline. A wrong proposal cannot lose a word of your document, but it can put a rule under the wrong heading, and the outline is where that shows.

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
| "Your notebook session has crashed" right after `cell 3`, with *compiled using NumPy 1.x cannot be run in NumPy 2* or *PyArrow must be installed* in the output | An install moved a package the runtime needs to start, so every restart crashes. Detach the notebook from the cluster and attach it again: that discards what `cell 3` installed, and only this notebook was affected. Do not restart the cluster for this. Then run `cell 2` onwards again. Since 21 September 2026 `cell 3` keeps the runtime's own numpy, pandas, pyarrow and scipy exactly as they are, and checks before restarting that they still import together, so this should not happen again; if it does, tell whoever maintains AIVA. |
| `cell 3` says "STOPPED BEFORE RESTARTING PYTHON" | The install changed something the runtime needs to start, and `cell 3` noticed before restarting, so the session is still alive. Detach the notebook and attach it again to undo the install, and tell whoever maintains AIVA which package pip named. |
| `cell 3` says pip could not find versions that fit | The index has no version of a package AIVA needs that works with this runtime's own packages. Nothing was changed. Ask for an older version of the package pip names to be added to the index. |
| The status cell says the run waits for a fresh token | The token ran out. Paste a new one (mode B: then run `cell 5`). No question is repeated. |
| "The time box of this foreground run is over" | Mode C stopped by itself. Paste a fresh token and run `cell 12` again. |
| "Many calls in a row failed, so the run paused itself" | The gateway is not answering. Check it with `cell 7`, then run `cell 12` again. |
| The cluster stopped | Start it, run `cell 2` to `cell 8` in order, choose the same run in the run widget, and run `cell 12`. The run resumes after its last finished step. |
| An input changed | Start a **new run** in the same project. `Model_Package_Info` lists what changed since the previous run. Never edit inputs of a run that has started. |
| A unit of kind *File not read* | That file or expression could not be parsed. It has a flagged item with the reason; the rest of the package was still read. |
| "... belongs to another run or another list of items" | The uploaded workbook is not this run's `Output.xlsx`. Download the current one and fill it again. |
| A cell reads "This text could not be shown in plain words" | AIVA withheld a text that contained technical traces; the text is in `_audit/run_log.txt`. Please report it; it is a defect in AIVA. |
| "This is a defect in AIVA, not in the model under review" | The coverage identity did not hold and the run stopped on purpose. Keep the run folder and report it. |

## 12. Known limitations

- The content of images is never evidence. Formulas given only as pictures end *Not assessed* or make the linked code *Traced - check undecided*. Where the optional OCR package is installed, the words inside a picture are shown under it, headed *Words read from the picture by OCR*; a machine misreads digits, so check them against the picture itself. The Figure still ends *Not assessed - for manual review*.
- **LLM Interpretation** on `Chunks_Model` says in plain words what a function, a formula statement, a top-level statement or a test block does. The AI is shown the piece itself together with where it sits in the whole package: the function a statement is inside, the package's own documentation of it, what calls it, what it calls, the stored data it reads, and an outline of every file. The words are the model's, so the cell shows them in quotation marks. They are an aid to reading and nothing more: an interpretation gives a unit no status, raises no flagged item, and is never used in a check. AIVA only accepts an answer whose quotation is in the code word for word; where an answer could not be used the cell says why. Other kinds of unit (documentation blocks, help pages, stored data) are not asked about.
- **Para no.** shows the paragraph number the document itself gives (`36.`), gaps included, where it gives one. A PDF gives none, so its paragraphs are labelled with their page and their place on it (`p.4 ¶2`); so are the paragraphs of a Word file in which Word noted where its pages ended. Otherwise it is AIVA's own count under the heading.
- The items of a list are shown inside the paragraph that introduces them, each on its own line behind `- ` or its number, and are not rows of their own. A list under a heading, with no paragraph before it, keeps its items as rows.
- A table of sentences is shown with each cell on its own line under the heading of its column (`Very Strong: ...`); a table of short values is shown as a grid, cells joined by `; `.
- Page headers, page footers and logos that repeat in the margins of a PDF are left out, and `Model_Package_Info` lists every one that was.
- A reading guided by the model (`agentic_reading: rules`) can put a statement under the wrong heading. It cannot lose a word or add one: every answer is a choice among tags AIVA showed it and families from a fixed list, and the content account on `Model_Package_Info` balances whatever the answer says. Check the changed rows at cell 10 before confirming the outline.
- A run with `agentic_reading` on is reproducible from its recorded answers, and two fresh runs on the same inputs may cut a file it is unsure of differently. The reading notes say which files were read that way.
- AIVA reads XML (also inside a `.txt`), `.mhtml`, `.docx`, `.pdf`, Markdown, `.csv` and `.tsv`, `.xlsx`, `.rtf` and `.tex`. It does not read slide decks, OpenDocument files, e-books, old Office files (`.doc`, `.xls`, `.ppt`) or pictures on their own; each of those becomes one row on the sheet saying so, with what to save it as instead. Folders inside an Inputs corner are read, in name order; a Word lock file, Thumbs.db and a saved web page's support folder are left out and listed on `Model_Package_Info`.
- A spreadsheet is read sheet by sheet, each sheet a heading over one table. A formula is never worked out: the value the spreadsheet saved with it is what is read, so save the workbook after it has calculated.
- The model package may be a tarball, a `.zip` of it, or its source folder. Only R is read as code: a package in another language is said to be one, and its files are kept as running text that nothing can be linked to.
- PDF input is read by position on the page; multi-column layouts and tables without ruling lines may be cut wrongly. Check the outline.
- R code is parsed by AIVA's own reader, not by R. Unusual syntax becomes a *File not read* unit for that expression only. Functions with loops or branches are compared statement by statement; R semantics that AIVA's evaluator does not cover (recycling of vectors, matrix products) end as "uses operations AIVA cannot evaluate".
- Stored data is decoded without R. Objects that are not tables, vectors or short lists are described and not compared; missing values of different kinds are not told apart.
- The percentage after "AI judgement" is not calibrated.
- The evaluation so far used invented sample projects and the stand-in `chat()`; results with a real model on a real package are the owner's Phase 12 campaign (chapter 27).
