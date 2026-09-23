# Verifier — the manual

**Version 0.0.3, September 2026.** One document for everyone: the person who runs a review, the person who reads its output, the person who reviews the code, and the person who maintains it. Part I is for everyone. Part II is for whoever runs a review. Part III is for whoever reads the code. Part IV is reference.

---

# Part I — For everyone

## 1. What the tool is, and what it is not

A model comes with three things: a **methodology** that says what it should do, a **package** of code and data that does it, and **documentation** that describes it. The tool reads all three, works out what corresponds to what, checks by code whether the things that correspond agree — formulas, values, stated rules — and raises what it could not line up as a question for a person.

It does not run the model. It does not judge whether the methodology is sound. It rates nothing: no grade, no score, no verdict. It shows what was read, how the model computes what it returns, and what is covered; a person decides what it means.

It is not tied to any sector. The methodology can be about anything the package computes. Nothing in the code, its vocabulary or its prompts assumes a field; what it knows about a project's language comes from the project's own files and, optionally, a glossary the analyst supplies.

**What comes out.** One run produces a folder with two deliverables and a record:

```
Run_2026-09-22_1430/
  Output.xlsx               six sheets: what was read, how the model computes what it returns, what is covered
  _audit/
    Audit_Log.xlsx          the record: the run, every step, every record, every exchange with the model
```

The record is what makes the run an **evidence pack**: from that workbook alone, anyone can check that the inputs are the ones fingerprinted, that the code that ran is the code released, and that nothing was edited afterwards.

## 2. How a review goes

1. **Put the files in.** A project folder has three input folders: the methodology, the package, the documentation. Almost any format works (section 6).
2. **Read.** The tool reads every file into small citable units — a paragraph, a table, a formula, a function — each with its place in the document and a fingerprint of its content. No model is involved yet. You are shown the outline it found and asked to confirm it.
3. **Map and link.** The tool maps how the model computes what it returns, from each final output down to its rawest inputs, with flowR reading the R code. It then links the passages of the methodology and the documentation to the model: the model chooses among candidates code proposes and must quote each word for word, or its answer is refused.
4. **Read.** `Output.xlsx` shows everything that was read, the map, and what is covered.
5. **Keep.** The run folder is the evidence pack.

## 3. Design rules

Fourteen rules. Each is enforced by named code, and a test holds each.

| Rule | Statement |
|---|---|
| R1 | The tool shows; people decide. No rating of seriousness. The policy terms never appear in anything the tool produces or names. |
| R2 | Closed accounting. Every unit read is one row of its sheet, and no row is anything else; this identity is checked on every run. A file, a step or a call that fails is written down, and the run goes on. |
| R3 | The model's opinion is never the last word. Answers are validated by code; a failed or rejected call leaves the unit unlinked and never stops a run. |
| R4 | Every link says how it was established, shows its evidence and carries provenance. Every citation can be re-verified by hash. |
| R5 | Everything except the model's answers is deterministic. Results never depend on thread timing. A run can be replayed from its recorded answers. |
| R6 | Inputs are never modified. A run writes only inside its own folder. |
| R7 | Nothing taken from an input or from the model is ever executed or evaluated: no R, no evaluation of text, no unpickling, no string parsing by a symbolic library, safe reading of archives, safe loading of YAML only. |
| R8 | The access token never persists: not in files, logs, manifests, workbooks or messages. |
| R9 | No domain concept in the engine, its vocabulary or its prompts. Domain flavour lives in sample data and in the optional glossary. |
| R10 | Plain language outward. No internal names, no technical traces, whole numbers shown as whole numbers, in anything an analyst reads. |
| R11 | One engine file, plain code, line budgets. The notebook is built from code and never edited by hand. |
| R12 | Workspace discipline: build on local disk, copy whole files, keep the file count small, sync after every step. |
| R13 | Reading conserves content. Every smallest piece of text in an input ends in exactly one named class: kept in a unit, kept elsewhere in a unit's fields, read into another form, left out under a named rule, or reported as not read. Every character of a unit traces back to the input or to a named mark. Where the model helps decide how a file is sliced it chooses among options the code has already checked, and never supplies text. |
| R14 | The map is exhaustive and verifiable. Every step of the Model Implementation Map is parsed from the code or quotes it word for word; every model unit is a step of the map, belongs to one, or is in the branch of units no final output reaches; every step ends at a named raw input; and what the tool cannot follow is a named gap, never a silence. |

**The wording rule.** The tool rates nothing. Words that grade how serious something is, and the two policy terms that classify an observation, never appear in anything the tool produces, because grading and classifying are decisions of the validation policy and of people, not of a tool. The tool says what it observed, where, and what a sensible next step would be. The list of words lives in one place in `verifier.py`, and a test scans the engine, the workbook, the report and this manual for them on every build.

## 4. Vocabulary

Every wording the tool records for a link, a refusal or a piece that could not be read comes from one list in `verifier.py`; the tables below are that list.

**Relations, as recorded**

| Wording |
|---|
| Implements |
| Partly implements |
| Differs from |
| Same topic (not implemented here) |
| Describes |
| Consistent with |

**How a link was established**

| Wording |
|---|
| Parsed from the files |
| AI judgement ({confidence}%) |

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

The rows of Chunks_Model never overlap, and each is a whole piece of code: a roxygen block is one row with the function or statement it documents, and what is written inside a function - its statements, a function defined within it - is part of the function's row. Model_Implementation_Map is where a function is taken apart: every assignment is a step of its own, so a value set four times is four steps, each computed from the one before; a named element of a list, such as `overrides_and_caps`, is a step of its own too; and a function's row has the value it returns as its child.

**Kinds of chunk**

| Wording |
|---|
| Paragraph |
| Table |
| Figure |
| Equation |

**Why an equation was not read**

| Wording |
|---|
| the equation is an image |
| the equation could not be read |

**Why an answer of the model could not be used**

| Wording |
|---|
| it could not be read |
| it named a passage that was not shown |
| it quoted words that are not in the text |
| it accepted a planted control passage |
| it contradicted itself |
| it repeated an action it had already taken |

**Fixed cell texts**

| Wording |
|---|
| Not run yet |
| The AI's wording is not displayed here; the full text is in the audit records. |

---

# Part II — Running a review

## 5. The notebook, four cells

The notebook is `Verifier.ipynb`. Four cells, run in order.

| Cell | What it does | When to run it again |
|---|---|---|
| **cell 1** | `verifier.setup(dbutils)`: makes the widgets, installs a package only if one the engine imports is missing, gets flowR ready, and prints what the other three cells do | after a cluster restart, or after pasting a package index |
| **cell 2** | Your organisation's `chat()`, already filled in; it reads the endpoint, token and user id through `verifier.live()` at the moment it is called. Then `verifier.check_chat(chat)` asks it one question, makes the project's `Inputs` folders and prints their paths | when the gateway or your id changes |
| **cell 3** | `verifier.review()`: reads every input file, maps how the model computes what it returns, asks your model to close the gaps code could not follow, and links the passages of the three inputs. Prints what each step did | after a token expires, a cluster restarts, or you add an input: finished steps are never repeated |
| **cell 4** | `verifier.verify()`: checks the finished run folder against its own record | after any run |

**The widgets.** Eight: the endpoint and token for the model gateway (01, 02); your user id (03), which is both the id sent to the gateway and the name recorded against the run; the model id (04) and project date (05); a package index (06), used only if a package must be installed; how many calls at once (07); and the token cap (08). Projects live in `Projects` next to the notebook, each in its own folder, `<model id>/<date>/Inputs`. A session keeps working on the run it opened; a new session, after a restart, starts a new run.

**No code of its own.** Every cell is one call into `engine/verifier.py`; the only code in the notebook is your organisation's `chat()` in cell 2. What a cell used to do - the widgets, the install, opening the run, printing what happened - is in the engine, where it is tested with the rest. Nothing is installed from an index you did not name: to install from pip's own default index, call `verifier.setup(dbutils, allow_default_index=True)`.

**The token.** It is read at the moment `chat()` is called, never stored. When it runs out mid-run, cell 3 says so and stops; paste a fresh one into widget 02 and run cell 3 again, and it carries on from the step that stopped.

**How long a run may take.** Cell 3 works in the cell itself, so you can see it and interrupt it. It may work for 600 minutes before it stops by itself and asks you to run it again - longer than any run we have seen; `verifier.review(foreground_minutes=...)` changes that.

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

Six sheets, always in this order; a sheet whose step has not run yet shows its header only, and *Run progress* on the first sheet says where the run stands.

| Sheet | What it holds |
|---|---|
| `Model_Package_Info` | what was read and what was not, each file's content account, the coverage identity, the run's progress |
| `Chunks_Canon` | every unit of the methodology, with its place in the outline |
| `Chunks_Doc` | every unit of the documentation, with its place in the outline |
| `Chunks_Model` | every unit of the model package: each a whole piece of code, as written |
| `Model_Implementation_Map` | how the model computes what it returns: each final output down to its rawest inputs, one row per variable |
| `Mapping_Coverage` | one row per final output and one per corner: what is covered and what is not |

**How to read one row of the map.** One row is one variable: where it sits (the Map ID, a column per level, and how deep it is), the variable itself with the code as written, the function that defines it with its unit, and what it is computed from — each of those a row beneath it. Section 8 describes the sheet in full.

**The sheets and columns.** As laid out in the one place that defines them, `verifier.WORKBOOK_LAYOUT_YAML`:

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
| Section (heading chain) | identity |  |
| Type | identity |  |
| Text | methodology |  |
| Source file | identity |  |

**Chunks_Doc**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity |  |
| Section (heading chain) | identity |  |
| Type | identity |  |
| Text | documentation |  |
| Source file | identity |  |

**Chunks_Model**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity |  |
| Kind | identity |  |
| File | identity |  |
| Lines | identity |  |
| Text | code text |  |

**Where the two mapping sheets went.** Until version 0.0.3 two mapping sheets held one row per model unit and one per documentation unit, with what each was linked to. The Model Implementation Map now shows each model unit in its place in the computation, and `Mapping_Coverage` what is covered, so those two sheets are gone.

**Mapping_Coverage**, read off the map. One row for each final output: how many steps it takes and how deep they run, what it rests on — arguments, columns of the data, stored tables, files and hard-coded numbers — and how many of its steps a methodology passage is linked to (*Covered*) and how many are not. Then one row for each corner, each read the way that corner needs:

| Row | Covered | Not covered |
|---|---|---|
| Model units | units a final output reaches: a row of the map, or the roxygen, help page, test or statement belonging to one | the units no final output reaches: dead code, a second way in, a function only the tests call |
| Methodology passages | passages a unit on the map is linked to | passages stating a number, formula or rule that no step implements. The rest state nothing to implement |
| Documentation passages | passages a unit on the map is linked to | passages describing nothing in the map |

Every number on this sheet is counted from the rows written to the map and to the Chunks sheets, so the sheet and the map always agree. The coverage identity is checked separately, by counting the statuses on `Chunks_Model` and `Chunks_Doc` against what the step account-coverage counted.


## 8. The Model Implementation Map


**The Model Implementation Map.** The sheet `Model_Implementation_Map` shows how the model computes what it returns, and nothing else: only what a calculation reaches is on it. One row is one variable. Reading a row from left to right: where it sits (the Map ID, one column per level — `MapID1`, `MapID2`, … — so any level can be filtered, and a parent leaves the deeper columns empty; the columns fold away with the + above them), then **Output Variable**, the one variable that row is about, with the code as written; then **Function Name**, the function that defines it, with its model unit; then **Arguments**, what the variable is computed from, separated by semicolons. Every name in Arguments is the Output Variable of a row directly beneath it, so a value can be followed down to the raw inputs it rests on: an argument of the final output, a column of the data given, a stored table, a file, or a hard-coded number, each a row with no function of its own. A reference is a link: clicking a `M-` reference opens that unit's row on `Chunks_Model`. The rows are grouped, each parent above its members, so a branch opens and closes with the + and − at the left; Excel groups eight levels deep and a deeper row is indented instead.

A called function is entered with the arguments that call gives it, so what it computes inside stands under the value it produces, and a parameter is never a row of its own: the row is the argument the call gave it. A function that calls itself stops there, keeping what the call is given. What no final output reaches is **not on this sheet**: dead code, a second way in, a function only the tests call, the methodology no step implements and the documentation describing nothing in the map are all counted on `Mapping_Coverage`, where each has its row.

**What each row's code is.** A final output's row shows the whole function that assembles it; every other row shows only its own code: an assignment shows its statement, and a named element of a list or a column a verb creates shows `name = value` alone, not the statement it sits in. Every named element of a list is a row, one holding only `NA` as much as any other. A row nothing computes - an argument of a final output, a column of the data given, a stored table, a file, a hard-coded number - is where a calculation starts: its Output Variable says so, `tie_inputs (terminal input)`, and its code is empty.

**Choosing the final outputs.** Code proposes as a final output a function nothing in the package calls that is exported or that the package's tests or vignettes call. Where code proposes none, every function nothing in the package calls stands in, so the map always has a top.

## 11. The run folder as an evidence pack

`_audit/Audit_Log.xlsx` is the record. Its sheet *Run* holds the run's identity and the fingerprint of every input and of every engine file that ran; *Steps* every step and what it did; *Records* every record of every kind, in the order written and never rewritten; *Model_Calls* every exchange with the model, prompt and reply. A text longer than a cell holds is split into numbered parts and joined again when read. Cell 4 verifies a pack from this workbook alone: that the inputs are the ones fingerprinted, that the engine files are the ones installed here, that re-reading the inputs gives the recorded content hashes, that the graph's hash chain verifies, that every unit read is in the record, that `Output.xlsx` carries this run's ids and fingerprints, and that no access token was written anywhere in the folder.

## 12. When something goes wrong

| What you see | What it means and what to do |
|---|---|
| `cell 1` says "STOPPED BEFORE RESTARTING PYTHON" | The install could not do what it should; the message says what is missing or what changed, and Python was not restarted. If it names a package the runtime itself needs, detach the notebook, attach it again and run `cell 1` once more. |
| `cell 1` says "flowR IS NOT READY" | The reason follows it. If the download failed, download the archive it names on an approved machine and put it next to the notebook. If flowR "could not run on this cluster", the cluster does not let a notebook start a program: use one in dedicated (single-user) access mode. |
| `cell 3` says "WAITING FOR A FRESH TOKEN" | The token ran out. Paste a new one into widget 02 and run `cell 3` again; the steps already finished are not repeated. |
| "Many calls in a row failed, so the run paused itself" | The gateway is not answering. Check it with `cell 2`, then run `cell 3` again. |
| The cluster stopped, or the notebook detached | Start or reattach it and run `cell 1` to `cell 3` in order. A new session starts a new run; the earlier run folder stays as it was. |
| An input changed | Start a **new run** in the same project. `Model_Package_Info` lists what changed since the previous run. Never edit inputs of a run that has started. |
| A unit of kind *File not read* | That file or expression could not be parsed. `Model_Package_Info` lists it with the reason; the rest of the package was still read. |
| A cell reads "This text could not be shown in plain words" | The tool withheld a text that contained technical traces; the text is in `_audit/run_log.txt`. Please report it; it is a defect in the tool. |
| "This is a defect in the tool, not in the model under review" | The coverage identity did not hold and the run stopped on purpose. Keep the run folder and report it. |

## 13. Known limitations

- The content of images is never evidence. A formula given only as a picture is kept as a figure and never read as a formula. Where the optional OCR package is installed, the words inside a picture are shown under it, headed *Words read from the picture by OCR*; a machine misreads digits, so check them against the picture itself.
- The items of a list are shown inside the paragraph that introduces them, each on its own line behind `- ` or its number, and are not rows of their own. A list under a heading, with no paragraph before it, keeps its items as rows.
- A table of sentences is shown with each cell on its own line under the heading of its column (`Very Strong: ...`); a table of short values is shown as a grid, cells joined by `; `.
- Page headers, page footers and logos that repeat in the margins of a PDF are left out, and `Model_Package_Info` lists every one that was.
- the tool reads XML (also inside a `.txt`), `.mhtml`, `.docx`, `.pdf`, Markdown, `.csv` and `.tsv`, `.xlsx`, `.rtf` and `.tex`. It does not read slide decks, OpenDocument files, e-books, old Office files (`.doc`, `.xls`, `.ppt`) or pictures on their own; each of those becomes one row on the sheet saying so, with what to save it as instead. Folders inside an Inputs corner are read, in name order; a Word lock file, Thumbs.db and a saved web page's support folder are left out and listed on `Model_Package_Info`.
- A spreadsheet is read sheet by sheet, each sheet a heading over one table. A formula is never worked out: the value the spreadsheet saved with it is what is read, so save the workbook after it has calculated.
- The model package may be a tarball, a `.zip` of it, or its source folder. Only R is read as code: a package in another language is said to be one, and its files are kept as running text that nothing can be linked to.
- PDF input is read by position on the page; multi-column layouts and tables without ruling lines may be cut wrongly. Check the outline.
- R code is never run. The package's units are read by the tool's own reader, and its data flow by flowR. Unusual syntax becomes a *File not read* unit for that expression only.
- Stored data is decoded without R. Objects that are not tables, vectors or short lists are described but not taken apart; missing values of different kinds are not told apart.
- The evaluation so far used invented sample projects and the stand-in `chat()`; results with a real model on a real package are still to be measured (section 22).

---

# Part III — For whoever reads the code

## 14. The one engine file

`engine/verifier.py` is the whole tool: the contracts and the words it may use, the reading floor, the front door that decides what a file is, the readers for the methodology and the documentation, the reader for the R package, the data flow it traces through that package, the search and the judgement of every link, the map's agents, the run, and `Output.xlsx`. Beside it are only `pipeline.yaml`, which names the steps, and `requirements.txt`. The tests and the maintainer's tooling live in `engine/tests/`, outside the tool itself.

## 15. The pipeline

Five steps, named and versioned in `pipeline.yaml`; nothing is loaded by path, and only a function the engine offers may be named.

| Step | Name | What it does |
|---|---|---|
| 01 | prepare-run | the run folder, the manifest, the fingerprints of the inputs |
| 02 | read-inputs | the methodology, the documentation and the model package, each read into units |
| 03 | build-map | by code alone: the graph, and the data flow of the package (read by flowR) |
| 04 | read-with-ai | the map's agents closing the gaps code named |
| 05 | link-units | two passes of search and judgement: candidates by code, then the model's judgement on each |

**How the data flow is read.** The package's R code is read by flowR, a static dataflow analyser for R (Sihler and Tichy, Ulm University; GPLv3). flowR parses the code with tree-sitter and decides, for every name, the definition it reads; for every call, the function it calls; and for every argument, the parameter it becomes there. The tool decides what is particular to a model: a column a dplyr verb creates, a stored table, a file a reader opens, and the places left as gaps for the model's agents. flowR is run on the cluster itself in one-shot mode: it reads the code as text and never runs it, starts no R process, opens no port and needs no network. It is fetched once by cell 1 and refused unless its SHA-256 is the one pinned in `verifier.py`. On a cluster that cannot reach GitHub, download the archive on an approved machine and put it next to the notebook; cell 1 uses it from there.

A step that carries out several parts keeps them in order, and a later part reads what the earlier ones have just recorded, as it would if each were still a step of its own.

## 16. How the model is used, and held

The model is asked questions whose answers are **choices among things code has already decided to show**: which of these lettered passages corresponds, quoting words from each; and, for the map's agents, which of a fixed list of actions to take next, quoting the code each link rests on. Every answer is validated by `verifier.validate_answer` before anything is done with it: a quotation that is not word for word in the passage, a reference to a passage that was not shown, a planted control passage accepted, a self-contradiction — each is a refusal, and a refusal leaves the unit unlinked. Nothing is repaired. A refused, failed or absent answer never stops a run and never changes an input.

Every exchange is recorded, and `verifier.replay_chat` answers from the record, so that a run can be reproduced without a model and its graph version compared.

## 17. Reading, and the content account

Every file read keeps a **content account** (`verifier.account`): the file's smallest pieces of text are counted straight from its bytes, then counted again in the units the tool produced, and the two must agree. A piece that is read but lands in no unit leaves the account open, and the file is named on `Model_Package_Info` with the reason, so nothing is dropped in silence.

## 18. Tests and sample projects

`engine/tests/` holds the tests, all offline, run with `python -m unittest discover engine/tests`. Eight sample projects under `engine/tests/sample_projects/` are built from source by `engine/tests/build_samples.py`, byte for byte the same on every build: four settled ones with gold links and gold clean units, and three built to be read badly — an XML schema unlike any the rules know, a two-column PDF with running headers and a footnote, a Word file with bold-only headings, a text box and tracked changes; and one built for the implementation map: a package, `J_pipeline`, with one R file among many help pages, dplyr pipelines that create columns, a purrr lambda, `do.call` over a list built at run time, a recursive function, dead code and a file read from `inst/`, whose `gold_map.yaml` says what a complete map of it must hold. `engine/tests/frozen/` holds a snapshot of every unit the four settled samples produce, so that a change to reading shows as a diff; `REFRESHED.md` beside it records every deliberate refresh and why.

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
| `reviewer_id` |  | Who runs the notebook; recorded against the run. |
| `read_pictures` | True | Read the words inside pictures by OCR when the optional package rapidocr-onnxruntime is installed. The words are shown under the Figure as a machine reading; a Figure still ends for manual review. |
| `signals` | ['fields', 'bridge', 'references', 'anchors', 'signatures', 'propagation'] | The search signals in use; the recall ladder (`develop.recall`) switches them off one by one. |

`map_granularity` (default `statement`): how fine the map is — `statement` gives a row for every variable; `function` folds a variable into what it rests on, leaving the values that cross a function call and the raw inputs. `map_rows_max` (default 5000): where a map stops; it says so in a row of its own, and names the setting. `map_hops_max` (default 8): the most turns the Tracer takes on one gap. `map_calls_max` (default 200): the most questions the map's agents ask in one run, the Tracer's and the Namer's together. `map_with_ai` (default true): whether the map's agents are asked at all.

## 21. Extending the tool safely

| You want to add | Where | What must be re-evaluated |
|---|---|---|
| a tag rule for a new XML schema | `Inputs/tag_rules.yaml` of the project; or, for every project, `verifier.TAG_RULES_YAML` | `test_documents.py`; the outline of one real document |
| a question type | a prompt in `verifier.PROMPTS`, a validator in `verifier.validate_answer`, a handler in the stand-in | the bad-answer corpus; the token budget for the largest unit |
| a search signal | `verifier.search_one`, `verifier.REASON_TEMPLATES`, the `signals` setting | `develop.recall`: the signal must earn its place on the recall ladder |
| a word the search should ignore, or a code-to-prose bridge | `verifier.STOPWORDS_TEXT`, `verifier.BRIDGE_PATTERNS_YAML` | the layout lint, which checks both for domain words |
| a column or a sheet of `Output.xlsx` | `verifier.WORKBOOK_LAYOUT_YAML` and the row builder of that sheet in `verifier.py` | `test_runner.py`; the end-to-end tests |

A prompt's text is part of every question id made from it, and recorded answers are found by that id: change a prompt's words and raise its `VERSION` line together, so that no answer to the old question is taken for an answer to the new one.

After any change, see section 23.

## 22. How the tool was measured


**Line counts.** `python engine/tests/develop.py budgets` prints them. The plan asked for at least 30 percent of each file to be docstrings, comments and overview; the files are below that share, and the numbers are reported as they are rather than padded.

**Dependencies.**

| Package | Needed | Note |
|---|---|---|
| openpyxl>=3.1 | required | Output.xlsx and the record of a run |
| PyYAML>=6.0 | required | the pipeline and the tool's own rule files |
| numpy>=1.24 | required | reading stored data and the search's own arithmetic |
| rdata>=1.0 | required | reads stored R data without running R |
| pdfplumber>=0.10 | optional | PDF text and tables |
| pypdf>=4.0 | optional | a second PDF reader |
| rapidocr-onnxruntime>=1.3 | optional | the words inside pictures (OCR) |
| flowR 2.15.8 (not a Python package) | required | reads the package's R code; fetched and checked by cell 1 |

**The implementation map.** `develop.map_measure` measures the map of `J_pipeline` against its answer key, part by part, and `develop.map_report` is the sign-off bar of its agents, four tests: the map holds every part of the answer key, including the gaps on the path the agents traced; every link the AI declared quotes the code word for word; the shape of the map is the same as with no model at all, because code decides it; and every question the agents asked was answered and accepted the first time, with every gap on the path ending traced or with a reason. With the stand-in all four hold, and the bar says so while reporting itself **not met**: the stand-in shows the machinery is sound, not how a model traces a gap it has never seen. Run it on your own gateway by calling `develop.map_report` with your `chat()`. Rehearsed against a model that declares links quoting code that is not there, the fourth test does not hold and the bar says NOT met.



## 23. Maintaining the tool

