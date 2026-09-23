# Verifier — the manual

**Version 0.0.3, September 2026.** One document for everyone: the person who runs a review, the person who reads its output, the person who reviews the code, and the person who maintains it. Part I is for everyone. Part II is for whoever runs a review. Part III is for whoever reads the code. Part IV is reference.

---

# Part I — For everyone

## 1. What the tool is, and what it is not

A model comes with three things: a **methodology** that says what it should do, a **package** of code and data that does it, and **documentation** that describes it. The tool reads all three, works out what corresponds to what, checks by code whether the things that correspond agree — formulas, values, stated rules — and raises what it could not line up as a question for a person.

It does not run the model. It does not judge whether the methodology is sound. It rates nothing: no grade, no score, no verdict. It shows what was read, how the model computes what it returns, and what is covered; a person decides what it means.

It is not tied to any sector. The methodology can be about anything the package computes. Nothing in the code or its vocabulary assumes a field; what it knows about a project comes from the project's own files.

**What comes out.** One run produces a folder with two deliverables and a record:

```
Run_2026-09-22_1430/
  Output.xlsx               five sheets: what was read, and how the model computes what it returns
  _audit/
    Audit_Log.xlsx          the record: the run, every step, every record, every exchange with the model
```

The record is what makes the run an **evidence pack**: from that workbook alone, anyone can check that the inputs are the ones fingerprinted, that the code that ran is the code released, and that nothing was edited afterwards.

## 2. How a review goes

1. **Put the files in.** A project folder has three input folders: the methodology, the package, the documentation. Almost any format works (section 6).
2. **Read.** The tool reads every file into small citable units — a paragraph, a table, a formula, a function — each with its place in the document and a fingerprint of its content. No model is involved yet. You are shown the outline it found and asked to confirm it.
3. **Map.** The tool maps how the model computes what it returns, from each final output down to its rawest inputs, with flowR reading the R code. No step of a review asks your model anything.
4. **Read.** `Output.xlsx` shows everything that was read, and the map.
5. **Keep.** The run folder is the evidence pack.

## 3. Design rules

Fourteen rules, each enforced by named code: its docstring says so (`Enforces: R2`).

| Rule | Statement |
|---|---|
| R1 | The tool shows; people decide. No rating of seriousness. The policy terms never appear in anything the tool produces or names. |
| R2 | Closed accounting. Every unit read is one row of its sheet, and no row is anything else; this identity is checked on every run. A file, a step or a call that fails is written down, and the run goes on. |
| R3 | The model's opinion is never the last word: a review asks the model nothing, and everything the workbook shows is read and parsed by code. |
| R4 | Every record carries its provenance - the step, its version and the run - and every unit can be re-verified by hash. |
| R5 | Everything except the model's answers is deterministic. Results never depend on thread timing. A run can be replayed from its recorded answers. |
| R6 | Inputs are never modified. A run writes only inside its own folder. |
| R7 | Nothing taken from an input or from the model is ever executed or evaluated: no R, no evaluation of text, no unpickling, no string parsing by a symbolic library, safe reading of archives, safe loading of YAML only. |
| R8 | The access token never persists: not in files, logs, manifests, workbooks or messages. |
| R9 | No domain concept in the engine or its vocabulary. Domain flavour lives in the inputs alone. |
| R10 | Plain language outward. No internal names, no technical traces, whole numbers shown as whole numbers, in anything an analyst reads. |
| R11 | One engine file, plain code. The notebook's four cells are calls into it and hold no code of their own but the organisation's `chat()`. |
| R12 | Workspace discipline: build on local disk, copy whole files, keep the file count small, sync after every step. |
| R13 | Reading conserves content. Every smallest piece of text in an input ends in exactly one named class: kept in a unit, kept elsewhere in a unit's fields, read into another form, left out under a named rule, or reported as not read. Every character of a unit traces back to the input or to a named mark. Where the model helps decide how a file is sliced it chooses among options the code has already checked, and never supplies text. |
| R14 | The map is exhaustive and verifiable. Every step of the Model Implementation Map is parsed from the code or quotes it word for word; every model unit is a step of the map, belongs to one, or is in the branch of units no final output reaches; every step ends at a named raw input; and what the tool cannot follow is a named gap, never a silence. |

**The wording rule.** The tool rates nothing. Words that grade how serious something is, and the two policy terms that classify an observation, never appear in anything the tool produces, because grading and classifying are decisions of the validation policy and of people, not of a tool. The tool says what it observed, where, and what a sensible next step would be. The list of words lives in one place in `verifier.py`, and a test scans the engine, the workbook, the report and this manual for them on every build.

## 4. Vocabulary

Every wording the tool shows for a kind of unit, a kind of chunk or a piece that could not be read comes from one list in `verifier.py`; the tables below are that list.

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


---

# Part II — Running a review

## 5. The notebook, four cells

The notebook is `Verifier.ipynb`. Four cells, run in order.

| Cell | What it does | When to run it again |
|---|---|---|
| **cell 1** | `verifier.setup(dbutils)`: makes the widgets, installs a package only if one the engine imports is missing, gets flowR ready, and prints what the other three cells do | after a cluster restart, or after pasting a package index |
| **cell 2** | Your organisation's `chat()`, already filled in; it reads the endpoint, token and user id through `verifier.live()` at the moment it is called. Then `verifier.check_chat(chat)` asks it one question, makes the project's `Inputs` folders and prints their paths | when the gateway or your id changes |
| **cell 3** | `verifier.review()`: reads every input file and maps how the model computes what it returns. Prints what each step did | after the cluster restarts, or you add an input: finished steps are never repeated |
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

**Only R is read as code.** A package in another language is said to be one, and its files are kept as running text that nothing can be linked to.

## 7. Reading `Output.xlsx`

Five sheets, always in this order; a sheet whose step has not run yet shows its header only, and *Run progress* on the first sheet says where the run stands.

| Sheet | What it holds |
|---|---|
| `Model_Package_Info` | what was read and what was not, each file's content account, the coverage identity, the run's progress |
| `Chunks_Canon` | every unit of the methodology, with its place in the outline |
| `Chunks_Doc` | every unit of the documentation, with its place in the outline |
| `Chunks_Model` | every unit of the model package: each a whole piece of code, as written |
| `Model_Implementation_Map` | how the model computes what it returns: each final output down to its rawest inputs, one row per variable |

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

**Where the two mapping sheets went.** Until version 0.0.3 two mapping sheets held one row per model unit and one per documentation unit, with what each was linked to. The Model Implementation Map now shows each model unit in its place in the computation, so those two sheets are gone.

## 8. The Model Implementation Map


**The Model Implementation Map.** The sheet `Model_Implementation_Map` shows how the model computes what it returns, and nothing else: only what a calculation reaches is on it. One row is one variable. Reading a row from left to right: where it sits (the Map ID, one column per level — `MapID1`, `MapID2`, … — so any level can be filtered, and a parent leaves the deeper columns empty; the columns fold away with the + above them), then **Output Variable**, the one variable that row is about, with the code as written; then **Function Name**, the function that defines it, with its model unit; then **Arguments**, what the variable is computed from, separated by semicolons. Every name in Arguments is the Output Variable of a row directly beneath it, so a value can be followed down to the raw inputs it rests on: an argument of the final output, a column of the data given, a stored table, a file, or a hard-coded number, each a row with no function of its own. A reference is a link: clicking a `M-` reference opens that unit's row on `Chunks_Model`. The rows are grouped, each parent above its members, so a branch opens and closes with the + and − at the left; Excel groups eight levels deep and a deeper row is indented instead.

A called function is entered with the arguments that call gives it, so what it computes inside stands under the value it produces, and a parameter is never a row of its own: the row is the argument the call gave it. A function that calls itself stops there, keeping what the call is given. What no final output reaches is **not on this sheet**: dead code, a second way in, and a function only the tests call are not rows of the map.

**What each row's code is.** A final output's row shows the whole function that assembles it; every other row shows only its own code: an assignment shows its statement, and a named element of a list or a column a verb creates shows `name = value` alone, not the statement it sits in. Every named element of a list is a row, one holding only `NA` as much as any other. A row nothing computes - an argument of a final output, a column of the data given, a stored table, a file, a hard-coded number - is where a calculation starts: its Output Variable says so, `tie_inputs (terminal input)`, and its code is empty.

**Choosing the final outputs.** Code proposes as a final output a function nothing in the package calls that is exported or that the package's tests or vignettes call. Where code proposes none, every function nothing in the package calls stands in, so the map always has a top.

## 11. The run folder as an evidence pack

`_audit/Audit_Log.xlsx` is the record. Its sheet *Run* holds the run's identity and the fingerprint of every input and of every engine file that ran; *Steps* every step and what it did; *Records* every record of every kind, in the order written and never rewritten; *Model_Calls* every exchange with the model, prompt and reply. A text longer than a cell holds is split into numbered parts and joined again when read. Cell 4 verifies a pack from this workbook alone: that the inputs are the ones fingerprinted, that the engine files are the ones installed here, that re-reading the inputs gives the recorded content hashes, that every unit read is in the record, that `Output.xlsx` carries this run's ids and fingerprints, and that no access token was written anywhere in the folder.

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
- The tool was developed against invented sample projects and a stand-in for `chat()`; results with a real model on a real package are still to be measured.

---

# Part III — For whoever reads the code

## 14. The one engine file

`engine/verifier.py` is the whole tool: the contracts and the words it may use, the reading floor, the front door that decides what a file is, the readers for the methodology and the documentation, the reader for the R package, the data flow it traces through that package, the run, and `Output.xlsx`. Beside it are only `pipeline.yaml`, which names the steps, and `requirements.txt`. The tests and the maintainer's tooling live in `engine/tests/`, outside the tool itself.

## 15. The pipeline

Three steps, named and versioned in `pipeline.yaml`; nothing is loaded by path, and only a function the engine offers may be named.

| Step | Name | What it does |
|---|---|---|
| 01 | prepare-run | the run folder, the manifest, the fingerprints of the inputs |
| 02 | read-inputs | the methodology, the documentation and the model package, each read into units |
| 03 | build-map | the data flow of the package, read by flowR |

**How the data flow is read.** The package's R code is read by flowR, a static dataflow analyser for R (Sihler and Tichy, Ulm University; GPLv3). flowR parses the code with tree-sitter and decides, for every name, the definition it reads; for every call, the function it calls; and for every argument, the parameter it becomes there. The tool decides what is particular to a model: a column a dplyr verb creates, a stored table, a file a reader opens, and the places code cannot follow, recorded as gaps. flowR is run on the cluster itself in one-shot mode: it reads the code as text and never runs it, starts no R process, opens no port and needs no network. It is fetched once by cell 1 and refused unless its SHA-256 is the one pinned in `verifier.py`. On a cluster that cannot reach GitHub, download the archive on an approved machine and put it next to the notebook; cell 1 uses it from there.

A step that carries out several parts keeps them in order, and a later part reads what the earlier ones have just recorded, as it would if each were still a step of its own.

## 16. How the model is used, and held

A review asks the model nothing. Cell 2 asks your `chat()` one question, to check the gateway answers; what the workbook shows - the reading, the map, every row - is made by code alone.

## 17. Reading, and the content account

Every file read keeps a **content account** (`verifier.account`): the file's smallest pieces of text are counted straight from its bytes, then counted again in the units the tool produced, and the two must agree. A piece that is read but lands in no unit leaves the account open, and the file is named on `Model_Package_Info` with the reason, so nothing is dropped in silence.

## 18. What ships

The tool is `Verifier.ipynb` and three files in `engine/`: `verifier.py`, `pipeline.yaml` and `requirements.txt`. The repository holds nothing else that runs: no tests, sample projects or maintainer's scripts, and nothing in the engine ever read them. `Engine_Map.xlsx` lists every function of the engine as of this version. To change the notebook, edit its four cells directly: each is one call into the engine, and the only code of your own is `chat()` in cell 2.

---

# Part IV — Reference

## 19. Settings

Settings are an allow-list: a name that is not in this table is refused. The notebook sets the concurrency limit, the token cap, the reviewer id and the reviewer role from its widgets.

| Setting | Default | Meaning |
|---|---|---|
| `concurrency_limit` | 4 | How many questions are asked at the same time. |
| `token_cap` | 40000 | The gateway's limit for one call, in tokens. |
| `max_parameter_cells` | 5000 | A stored object with more cells is profiled and not compared. |
| `max_parameter_columns` | 50 | A stored object with more columns is profiled and not compared. |
| `protect_sheets` | True | Lock every cell except the yellow ones (filtering stays allowed; no password). |
| `trivial_numbers` | ['0', '1', '2', '-1', '10', '100'] | Numbers that are not looked up in the methodology. |
| `bm25_k1` | 1.2 | Text ranking: how fast repeated words stop counting. |
| `bm25_b` | 0.75 | Text ranking: how much long passages are scaled down. |
| `max_file_mb` | 200.0 | A larger input file is not read and becomes a not-read unit. |
| `reviewer_id` |  | Who runs the notebook; recorded against the run. |
| `read_pictures` | True | Read the words inside pictures by OCR when the optional package rapidocr-onnxruntime is installed. The words are shown under the Figure as a machine reading; a Figure still ends for manual review. |

`map_granularity` (default `statement`): how fine the map is — `statement` gives a row for every variable; `function` folds a variable into what it rests on, leaving the values that cross a function call and the raw inputs. `map_rows_max` (default 5000): where a map stops; it says so in a row of its own, and names the setting.

## 21. Extending the tool safely

| You want to add | Where |
|---|---|
| a tag rule for a new XML schema | `Inputs/tag_rules.yaml` of the project; or, for every project, `verifier.TAG_RULES_YAML` |
| a column or a sheet of `Output.xlsx` | `verifier.WORKBOOK_LAYOUT_YAML` and the row builder of that sheet in `verifier.py` |

After any change, see section 23.

## 22. What the tool needs

**Dependencies.**

| Package | Needed | Note |
|---|---|---|
| openpyxl>=3.1 | required | Output.xlsx and the record of a run |
| PyYAML>=6.0 | required | the pipeline and the tool's own rule files |
| numpy>=1.24 | required | reading stored data |
| rdata>=1.0 | required | reads stored R data without running R |
| pdfplumber>=0.10 | optional | PDF text and tables |
| pypdf>=4.0 | optional | a second PDF reader |
| rapidocr-onnxruntime>=1.3 | optional | the words inside pictures (OCR) |
| flowR 2.15.8 (not a Python package) | required | reads the package's R code; fetched and checked by cell 1 |

## 23. Maintaining the tool

Everything that runs is in `engine/verifier.py`; the manual names the one place each thing lives (section 21). After a change, run a review on a project you know and compare its `Output.xlsx` with the one before: every sheet should differ only where the change meant it to.
