# Verifier — the manual

One document for everyone: the person who runs a review, the person who reads its output, the person who reviews the code, and the person who maintains it. Part I is for everyone. Part II is for whoever runs a review. Part III is for whoever reads the code. Part IV is reference.

---

# Part I — For everyone

## 1. What the tool is, and what it is not

A model comes with three things: a **methodology** that says what it should do, a **package** of code and data that does it, and **documentation** that describes it. The tool reads all three into small numbered units, links each piece of the package to the pieces it takes something from and gives something to, and asks the organisation's language model to explain each piece of code, to find the chunks of the methodology behind it, and to flag where the code may depart from them.

It does not run the model. It does not judge whether the methodology is sound. It rates nothing: no grade, no score, no verdict. It shows what was read and what the organisation's model says of it, marked as the model's; a person decides what it means.

Its reading and its accounts assume no field: the methodology can be about anything the package computes, and what the tool knows about a project comes from the project's own files. Its code interpretations are written for credit: step 04 asks the organisation's model to explain each piece of code in the financial credit concepts it implements, for a CFA-level analyst checking it against the methodology. Step 05 then asks it, for each piece, which chunks of the methodology describe, explain or inform it, and where the code departs from them.

**What comes out.** A run writes `Output.xlsm` and an `_Audit` folder into the project's folder, beside its inputs:

```
Projects/<project name>/
  1_Methodology/            the methodology, as you put it there
  2_Model_Package/          the model's R package
  3_Model_Documentation/    the model documentation
  Output.xlsm               five sheets: what was read, what the organisation's model says of the code, and each item it flags
  _Audit/                   the record of the run (section 8):
    Audit_Log.xlsx            the run, every step, every record, every exchange with the model, every file below
    run_log.txt               the run's technical log
    01_prepare-run/ ... 05_search-methodology/
                              a JSON file for everything each step read, made or asked chat(), in the order written
```

A project holds one run at a time. Cell 3 carries it on where it stopped - in the same session or a later one - while the input files, the engine and the settings are the ones it started with; when one of them has changed, it starts a new run, keeping the run before - its `Output.xlsm` and its `_Audit` folder - whole in `_Audit/previous_runs/<run id>`, and `Model_Package_Info` lists what changed since the run before. A new token pasted into widget 02 changes none of them: the run carries on. An `Output.xlsm` you have edited is never replaced: cell 3 asks you to move it aside first.

The record is what makes the run an **evidence pack**: from that workbook alone, anyone can check that the inputs are the ones fingerprinted, that the code that ran is the code released, and that nothing was edited afterwards.

## 2. How a review goes

1. **Put the files in.** A project folder has three input folders: the methodology, the package, the documentation. Almost any format works (section 6).
2. **Read.** The tool reads every file into small citable units — a paragraph, a table, a formula, a function — each with its place in the document and a fingerprint of its content. No model is involved yet. You are shown the outline it found and asked to confirm it.
3. **Link.** The tool links each piece of the package to the pieces it takes something from and gives something to, with flowR reading the R code. No model is involved.
4. **Ask.** Through your `chat()`, the organisation's model explains each piece of code (step 04), finds the chunks of the methodology that bear on it and flags where the code may depart from them (step 05). Its words fill three columns of Chunks_Model, each headed as the model's own.
5. **Read.** `Output.xlsm` shows everything that was read, and what the model said.
6. **Keep.** `Output.xlsm` and the `_Audit` folder, with the inputs beside them, are the evidence pack.

## 3. Design rules

Thirteen rules, each enforced by named code: its docstring says so (`Enforces: R2`).

| Rule | Statement |
|---|---|
| R1 | The tool shows; people decide. No rating of seriousness. |
| R2 | Closed accounting. Every unit read is one row of its sheet, and no row is anything else; this identity is checked on every run. A file, a step or a call that fails is written down, and the run goes on. |
| R3 | The model's opinion is never the last word. What a language model writes is marked as its own - three columns, each headed "(... by LLM ...)" - and recorded, question and answer, in the audit log; code checks that every chunk the model names was shown to it; everything else the workbook shows is read and parsed by code, and nothing the code reads, links or checks depends on an answer. |
| R4 | Every record carries its provenance - the run and the step - and every unit can be re-verified by hash. |
| R5 | Everything except the model's answers is deterministic. Results never depend on thread timing. A run can be replayed from its recorded answers. |
| R6 | Inputs are never modified. A run writes only `Output.xlsm` and its `_Audit` folder, beside the three input folders, and its scratch folder on the driver. The one move the tool makes is bringing a project laid out before, with its folders inside `Inputs`, to this layout: once, each folder whole, no file in it changed (section 6). |
| R7 | Nothing taken from an input or from the model is ever executed or evaluated: no R, no evaluation of text, no unpickling, no string parsing by a symbolic library, safe reading of archives, safe loading of YAML only. |
| R8 | The access token never persists: not in files, logs, manifests, workbooks or messages. |
| R9 | Credit is the domain of the model's interpretations. Step 04 asks the model to explain each piece of code in the financial credit concepts it implements, for a CFA-level analyst checking it against the methodology, and step 05 to find the methodology behind each piece and where the code departs from it; the reading and the accounts assume no field. |
| R10 | Plain language outward. No internal names, no technical traces, whole numbers shown as whole numbers, in anything an analyst reads. |
| R11 | One engine file, plain code. The notebook's four cells are calls into it and hold no code of their own but the organisation's `chat()`. |
| R12 | Workspace discipline: build on local disk, copy whole files - each file of the `_Audit` folder once - and sync after every step. |
| R13 | Reading conserves content. Every smallest piece of text in an input ends in exactly one named class: kept in a unit, kept elsewhere in a unit's fields, read into another form, left out under a named rule, or reported as not read. Every character of a unit traces back to the input or to a named mark. Where the model helps decide how a file is sliced it chooses among options the code has already checked, and never supplies text. |

**No ratings.** The tool rates nothing: grading and classifying are decisions of the validation policy and of people, not of a tool. It says what it read, where, and what the organisation's model says of it, in the model's own words.

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
| Vignette text |
| Compiled code |
| File not read |
| Other file |

Two parts of the package are counted but not read into chunks. Its help pages (`man/*.Rd`) are generated from the roxygen comments in the R files, which are read. Its tests (`tests/`: testthat scripts, their helpers and setup, fixtures, snapshots) check the model rather than compute it, so for now they are left out: they are not model chunks, are not linked to the code, and are not asked about - no Test block is made. Model_Package_Info says how many of each there are, and the package's content account counts every line of them as left out under a named rule.

The rows of Chunks_Model never overlap, and each is a whole piece of code - or one part of a piece too long for one row, shown as `M-0003-1`, `M-0003-2` and so on, cut at line ends, which joined back are the piece exactly, character for character; a chunk of the methodology or the documentation too long for one row is shown in parts the same way, and every such chunk is treated as one wherever it is used: a roxygen block is one row with the function or statement it documents, and what is written inside a function - its statements, a function defined within it - is part of the function's row. A help page (`man/*.Rd`) is not read: it is generated from the roxygen comments in the R files, which are; Model_Package_Info counts how many were left out.

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
| **cell 1** | `verifier.setup(dbutils)`: makes the three widgets, takes your user id from Databricks, installs a package only if one the engine imports is missing (then restarts Python and asks for the cell once more), gets flowR ready, and prints what the other three cells do | whenever Python restarts |
| **cell 2** | Your organisation's `chat()`, already filled in; it returns the model's reply under `"answer"` and reads the endpoint, token and user id through `verifier.live()` at the moment it is called. Cell 3 calls it from many threads at once, up to 256, so it keeps nothing from one call to the next. Then `verifier.check_chat(chat)` asks it one question, makes the project's three input folders and prints their paths, bringing a project laid out before, with its folders inside `Inputs`, to the present layout (section 6) | whenever Python restarts, and when the gateway or your id changes |
| **cell 3** | `verifier.review()`: reads every input file, links the units of the package, then asks your `chat()` to describe each piece of the model's code (step 04), and to find the methodology behind each piece and where the code departs from it (step 05), with a line of progress every minute. Prints what each step did and where the project folder is | when it says a step did not finish - after pasting a fresh token, if it ran out: finished steps are never repeated, and no answer received is asked for again, even after an interruption. After Python restarts, run cells 1 and 2 first: cell 3 carries the run on where it stopped |
| **cell 4** | `verifier.verify()`: nine checks of `Output.xlsm` and the `_Audit` folder against their own record, each Confirmed or Not confirmed | after any run |

**The widgets.** Three: the endpoint and token for the model gateway (01, 02), and the project's name (03), which can be a model id and names the project's folder. Your user id is not a widget: cell 1 takes it from Databricks - the notebook's own user - and `verifier.live("reviewer_id")` gives it to `chat()`, which sends it to the gateway; it is also recorded against the run. Packages come from PyPI, named in the engine. Projects live in `Projects` next to the notebook, each in its own folder, `<project name>`, with its three input folders, and `Output.xlsm` and the `_Audit` folder a run writes beside them. A name holds at most 24 characters, from letters, digits, hyphen and underscore. A run is named by the minute it started, as `2026-09-22_1430`. Cell 3 carries the project's run on, in this session or a later one, until an input file, the engine or a setting changes; then it starts a new one.

**No code of its own.** Every cell is one call into `engine/verifier.py`; the only code in the notebook is your organisation's `chat()` in cell 2. What a cell used to do - the widgets, the install, opening the run, printing what happened - is in the engine, where it is tested with the rest. Packages come from PyPI, named in the engine (section 18).

**The token.** It is read at the moment `chat()` is called, never stored. Cell 2 calls `chat()` once; cell 3 calls it once for each piece of the model's code in step 04, and in step 05 once for each piece and each batch of the methodology, then once more for each piece the methodology bears on. When the token runs out during cell 3, the questions start failing, and once the questions already out and four more have all failed, cell 3 sends no more and says so. Paste a fresh token into widget 02 and run cell 3 again: every answer received is kept, and only the questions still open are asked.

**How long a run may take.** Cell 3 works in the cell itself, so you can see it and interrupt it; a long step says every minute how far it has got. Interrupting it loses no answer that has arrived: they are held for this session, and running cell 3 again writes them and asks only for the rest. Nor does an outage of the model: when `chat()` fails - it raises, as on a 503 or an expired token, or returns no "answer" - the step stops asking after a few questions in a row, writes every answer it received, and says what the last call returned. Once the token is fresh or the gateway back, run cell 3 again - or every cell, from cell 1: neither cell 1 nor cell 2 touches the run - and it carries on where it stopped, asking only the questions still open.

## 6. What goes in

Three folders in the project's folder, beside `Output.xlsm` and the `_Audit` folder:

| Folder | What | Formats |
|---|---|---|
| `1_Methodology` | the canonical methodology | XML (also inside a `.txt`), `.mhtml`, `.docx`, `.pdf`, `.svg` |
| `2_Model_Package` | the model | an R package as a `.tar.gz`, a `.zip` of it, or its source folder |
| `3_Model_Documentation` | the model documentation | as for the methodology; `.docx` preferred |

Only these three folders are read, and the optional `tag_rules.yaml` and `glossary.xlsx` beside them: anything else in the project's folder - `Output.xlsm`, the `_Audit` folder, a copy you saved there - is not an input.

**A project laid out before.** Projects used to keep the three folders inside a folder named `Inputs`. The first time cell 2 or cell 3 meets such a project, it moves each folder up into the project's folder, whole, not a file in it changed, and says so; `Inputs` goes once nothing but hidden files is left in it, and anything of yours still in it stays, and is named. A folder above that holds only the tool's README gives way. If a folder stands in both places and both hold files, the tool moves neither, and cell 3 stops until you keep one. The inputs' fingerprints do not change: they name each file by its path inside its folder.

Folders inside a corner are read too, in name order. A Word lock file, `Thumbs.db` and a saved web page's support folder are left out and listed. A format the tool does not read — a slide deck, an old `.doc`, a picture on its own — becomes one row on `Model_Package_Info` saying so and what to save it as instead. Nothing is decoded as text that is not text.

**SVG pictures.** An SVG holds its text as text, so the tool reads a chart or a table drawn as a picture without guessing: every word comes from the picture's own `<text>` elements. Text that stands in a grid of at least two rows of the same width becomes a table, with the first row as its header; anything else becomes a figure whose words are the picture's labels in reading order. Where the methodology's XML refers to a picture beside it — `<figure src="floors.svg">` — that figure takes the picture's table or labels as its own, under the caption the XML gives. Only a picture in the same folder as the document, or a folder inside it, is followed; a missing picture or a path that leaves the folder stays a plain figure.

**Only R is read as code.** A package in another language is said to be one, and its files are kept as running text that nothing can be linked to.

## 7. Reading `Output.xlsm`

Five sheets, always in this order; a sheet whose step has not run yet shows its header only, and *Run progress* on the first sheet says where the run stands.

| Sheet | What it holds |
|---|---|
| `Model_Package_Info` | what was read and what was not, each file's content account, the coverage identity, the run's progress |
| `Chunks_Methodology` | every unit of the methodology, with its place in the outline |
| `Chunks_Documentation` | every unit of the documentation, with its place in the outline |
| `Chunks_Model` | every unit of the model package: each a whole piece of code, as written, the units it takes from and gives to, and what the organisation's model says of it - its interpretation, the chunks of the methodology behind it, and where the code may depart from them |

**The sheets and columns.** As laid out in the one place that defines them, `verifier.WORKBOOK_LAYOUT_YAML`:

**Model_Package_Info**

| Column | Colour group | What it shows |
|---|---|---|
| Group | identity |  |
| Item | identity |  |
| Value | assessments |  |

**Chunks_Methodology**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity | `C-0001`, or, for a chunk too long for one row, `C-0001-1`, `C-0001-2` and so on: one chunk in parts, cut at line ends. The parts are the ones step 05 shows the model, and the chunk is treated as one wherever it is used: a part found relevant makes the whole chunk relevant, named by its own ref, and a comparison is shown all its parts. Model_Package_Info lists these chunks. |
| Section (heading chain) | identity |  |
| Type | identity |  |
| Text | methodology |  |
| Source file | identity |  |

**Chunks_Documentation**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity | `D-0001`, or, for a chunk too long for one row, `D-0001-1`, `D-0001-2` and so on: one chunk in parts, cut at line ends. Model_Package_Info lists these chunks. |
| Section (heading chain) | identity |  |
| Type | identity |  |
| Text | documentation |  |
| Source file | identity |  |

**Chunks_Model**

| Column | Colour group | What it shows |
|---|---|---|
| Ref | identity | `M-0001`, or, for a piece too long for one row, `M-0001-1`, `M-0001-2` and so on: one piece of code in parts, each part with its own lines. It is treated as one wherever it is used: the model is asked about its parts one by one, and what it says of them - the parts' explanations together, the chunks of the methodology found for any part, and the deviations flagged against those - stands once, from the piece's first row down. Model_Package_Info lists these pieces. |
| Kind | identity |  |
| File | identity |  |
| Lines | identity |  |
| Text | code text | The unit exactly as read, whole: a function or statement as written, a stored table with every row, after a first line naming it, its file and its size, any other file of the package in full. Too long for one row, it continues on the rows below (see Ref). |
| Immediate Upstream Model Chunk | links | The units this code takes something from, as Refs joined with "; ": a function it calls, a variable set at the top level of an R file or earlier in the same script, a stored table or a data file it reads. Worked out in step 03 from flowR's reading of the code. A cell that lists references is a link: see Following a reference, below. |
| Immediate Downstream Model Chunk | links | The units that take something from this one: the same links, seen from the other end. A cell that lists references is a link: see Following a reference, below. |
| Code Interpretation (by LLM) | model | What the organisation's model says the code does, in the language of credit, for a CFA-level analyst checking it against the methodology: the credit concept it implements, what its inputs mean, how it computes its result, the floors, caps and constants it fixes, and where it follows or departs from a standard convention. The model saw the code the row takes from and the code that takes from it, and chose how much detail to give. Written in step 04 through your `chat()`. It is the model's reading, not the tool's, and nothing else in the workbook depends on it. "No interpretation" means the model gave no answer - run cell 3 again; "Not asked" means nothing was read from the file. |
| Relevant Chunks in Methodology (searched by LLM) | model | The chunks of Chunks_Methodology that describe, explain or inform this piece, as Refs joined with "; ", in reading order. Found in step 05: the piece - its code and its interpretation - is put to the model with each batch of the methodology in turn, until every chunk has been searched for it, and the model names the chunks an analyst needs to read to check the piece. Code keeps only chunks that were shown to it. "None found" means every chunk was searched and none bears on the piece; "Not searched in full" says how far the search got and what is still to search. A cell that lists references is a link: see Following a reference, below. |
| Count of Flagged Items (by LLM) | model | How many items the model flagged for this piece, each a row of Flagged_Items: a whole number - 0 where the chunks were compared and nothing was flagged, or where no chunk of the methodology was found. Empty before the methodology is searched in full; while comparisons are still open, the number so far and the chunks still to compare. A count above 0 is a link: a click shows Flagged_Items with this piece's items only. Filter it above 0 to see every piece with an item to review. |

**Flagged_Items** - one row for each item the model flagged, so that each can be assessed on its own:

| Column | Colour | What it holds |
|---|---|---|
| Ref | identity | The item's own reference, F-0001, F-0002 and so on, numbered in the order of Chunks_Model and, within a piece, in the order the model gave them. |
| Location of Flagged Item | links | The piece of Chunks_Model the item was found in, as a link: a click shows Chunks_Model with that piece only. |
| Ref in Chunks_Methodology | links | The chunks of the methodology the item rests on, as a link: a click shows Chunks_Methodology with those chunks only. |
| Type | model | How the code departs - it differs, it omits something, it adds something, or the methodology can be read more than one way - and the item's title: one sentence naming what differs and where. |
| Methodology Says | model | What those chunks require, quoted where the wording matters. |
| Code Does | model | What the piece does instead, naming its variables, functions and lines. |
| Why Potential Flagged Item | model | How the code's result comes to depart from what the methodology prescribes, step by step. |
| Effect | model | Which inputs or cases are affected, in which direction, and by how much where the code shows it. |
| Concrete Example of Potential Deviation | model | One case followed through in clear prose, with numbers where the chunks and the code give them: what the methodology gives, what the code gives, and why the two part. "The model gave no example." where it gave none. |
| Decision (by Human Reviewer) | reviewer | Yours: choose True Positive, False Positive, True Negative, False Negative, For further discussion, or Other Case (see notes) from its list. |
| Human Reviewer's Notes | reviewer | Yours: free text. |

The two reviewer's columns, shaded, are where your decision and notes go. No sheet is locked - Excel greys out Data > Clear on a locked sheet, and a filter a link applies must be cleared from the ribbon - so any cell can be typed in: change only those two columns. Once you have typed in the workbook, the tool never writes over it: running cell 3 again leaves your copy as it is and says so, and a new run stops until you move it aside (section 8).

**How the links are found.** R looks a name up inside the function first, then in the script it runs in, then in the package, and the two link columns follow the same order. flowR reads each function, and each script whole: a test file, a vignette, or the top-level code of an R file. It resolves every name it can to where it is defined, such as a parameter, a value set earlier, or a variable an earlier statement of the same script set, so a link between statements of one script is flowR's own. A name flowR cannot resolve inside a unit is one the unit takes from outside, and the package names it: one of its functions, a variable its R files set at top level, or its stored data. A data file named in the code, as in `read.csv(system.file("extdata", "limits.csv", ...))`, links to that file's row. A package function named like a base function wins, as it does in R. A function or variable set in a test or vignette is seen only later in the same file, and a test helper by every test. What is not a link: a name of another package (`dplyr::filter`), a parameter or local value that shares a name with a package function, the export list in `NAMESPACE`, and documentation naming a dataset.

**Stored data, followed further.** The package's parameters - its `.rda`, `.rdata` and `.rds` files, and tables under `data/` or `inst/` - are linked to the code that reads them however the code reaches them. Besides a plain use of an object's name, `package::name`, and `data()`, `get()`, `readRDS()` or `load()` given its name or its file's name, the tool follows three more ways:
- **Through helpers.** A function that takes a name as text and hands it on - `get_param <- function(name) get(name)` - is a helper; wherever it is called with a name, `get_param("lgd_floors")`, the caller and the helper are both linked to `lgd_floors`, through as many helpers as the code has. A name put together from known text, such as `paste0(kind, "_floors")` called with `"lgd"`, is put together the same way.
- **Through environments.** A member one unit stores in an environment the package keeps - `cache$floors <- lgd_floors`, `cache[["floors"]] <- ...` or `assign("floors", ..., envir = cache)` - links to every unit that reads it back as `cache$floors`, `cache[["floors"]]` or `get("floors", envir = cache)`. A name stored in the package's own environment, by `assign(..., envir = topenv())` or `<<-`, links to every unit that uses the name.
- **By a name built when the code runs.** Where only part of the name is known, as in `get(paste0(kind, "_floors"))` with `kind` given at run time, the stored objects it could be are listed with `(possible)` after them: the code may read them, and the tool cannot prove which. Where nothing of the name is known, the row says "reads stored data by a name known only when it runs".

So a cell of Immediate Upstream or Immediate Downstream Model Chunk holds the links the code proves, then the possible ones, then what could not be known. A stored object that no code reads says "None: no code of the package reads it." - often a finding in itself: a parameter the model ignores, or a value the code hard-codes instead - and Model_Package_Info counts the stored objects read and names those that are not. Each stored object's own row opens with its name, its file and its size, such as `lgd_floors - data/lgd_floors.rda: 3 rows, 2 columns`, so that every link to it can be recognised. A click on a link cell shows every chunk it names, the possible ones too.

**Following a reference.** In Chunks_Model, every cell of Relevant Chunks in Methodology (searched by LLM), Immediate Upstream Model Chunk and Immediate Downstream Model Chunk that lists references is a link, in blue. A click on a cell of Relevant Chunks in Methodology shows Chunks_Methodology with only the chunks that cell names; a click on a cell of Immediate Upstream Model Chunk or Immediate Downstream Model Chunk shows Chunks_Model with only the chunks that cell names and the row you clicked, so that clicking on up the chain walks the code back to its inputs, and down it forward to what uses them. There the cell you clicked stays the active cell; a click that shows another sheet takes you to the top of it. A chunk shown in several rows is shown whole. On Flagged_Items, a click on an item's Location of Flagged Item shows its piece on Chunks_Model, and a click on its Ref in Chunks_Methodology shows those chunks; on Chunks_Model, a click on a Count of Flagged Items above 0 shows that piece's items on Flagged_Items. Each click replaces the filter before it; to see every row again, clear the filter (Data > Clear). The filtering is done by one small macro in the workbook, which is why the file is `Output.xlsm`: it reads the references of the cell clicked and filters the sheet's Ref column, and does nothing else - it changes no value and sends nothing anywhere. You can read it in Excel (Alt+F11, then ThisWorkbook) or in the engine (`verifier.WORKBOOK_MACRO`). Without macros, a click still takes you to the first chunk the cell names.

**Letting the macro run.** Excel blocks the macros of a file that came from the internet, which a file downloaded from Databricks is: it shows a red bar saying so, or opens it in Protected View. On Windows, close the file, right-click it, choose Properties, tick Unblock, and open it again; then choose Enable Editing and Enable Content if Excel asks. Where your organisation allows macros only in trusted locations, save the file in one. Excel for the web, LibreOffice and Google Sheets do not run it: there the links only take you to the first chunk.

## 8. Output.xlsm and the _Audit folder as an evidence pack

`_Audit/Audit_Log.xlsx` is the record. Its sheet *Run* holds the run's identity and the fingerprint of every input and of every engine file that ran; *Steps* every step and what it did; *Records* every record of every kind, in the order written and never rewritten; *Model_Calls* every exchange with the model, prompt and reply; *Files* every file of the `_Audit` folder, in the order written, with what it holds, when it was written, its size and its SHA-256 - its path a link that opens the file. A text longer than a cell holds is split into numbered parts and joined again when read. Cell 4 verifies a pack from this workbook alone: that the inputs are the ones fingerprinted, that the engine files are the ones installed here, that re-reading the inputs gives the recorded content hashes, that every unit read is in the record, that `Output.xlsm` carries this run's ids and fingerprints, and that no access token was written into either file.

**Reading the `_Audit` folder in order.** Beside `Audit_Log.xlsx` and `run_log.txt`, the run's technical log, is one folder for each step, numbered as the steps run: `01_prepare-run`, `02_read-inputs`, `03_link-chunks`, `04_interpret-code`, `05_search-methodology`. In each, the files are numbered in the order the step wrote them, and a step run again goes on with the next number, so the folders read top to bottom as the run happened:

| Step | Its files |
|---|---|
| 01 | `run-manifest`: the run's identity, the fingerprints of its inputs and of the engine's files, the settings |
| 02 | for each methodology and documentation file, how it was read, the repairs made to it and every chunk made of it; for each file of the package, every unit made of it; the package's account; the lines of Model_Package_Info |
| 03 | `unit-links`: each unit's links, and how each was found |
| 04, 05 | one file for each exchange with `chat()` - `M-0003_code-interpretation`, `M-0003_methodology-search_C-0001-C-0028`, `M-0003_methodology-comparison_C-0012` - holding the SystemPrompt and the MainPrompt exactly as sent (and any later MainPrompt, when an answer was asked for again), the answer as returned, when it was sent and returned, the outcome, and what went wrong if anything did |
| every step | `step_attempt-1`, `-2` ...: what the attempt did, counted and said, and whether it finished; `fault_attempt-N` when it could not finish, with the fault inside the tool |

The sheet *Files* of `Audit_Log.xlsx` lists every one of them, numbered across the whole run; an exchange's line also says when it was sent and returned. The columns *Sent at* and *Returned at* sort the exchanges into the order they happened. No file holds the access token.

**Running again.** The rules that keep the record whole, whatever happens:
- **A run carried on only adds.** When cell 3 runs again - after an expired token, a gateway that was down, a stopped cell - nothing in `_Audit` is overwritten or deleted: a step run again goes on with the next number, its failed exchanges stay, each with what `chat()` returned, and a question already answered is never asked again. The sheet *Steps* lists every attempt.
- **Answers survive a stopped cell and a restart of Python.** Each answer is written, the moment it arrives, to a journal on the driver's own disk, the token removed, and the next run of the step writes it into the record with the time it was first sent. A restart of the cluster wipes that disk: answers not yet written are then asked again.
- **A new run keeps the run before.** A changed input file, a changed engine or a changed setting starts a new run - a new token does not - and the run before, its `Output.xlsm` and everything in `_Audit`, is moved whole into `_Audit/previous_runs/<run id>/`, byte for byte, never deleted, and a run's id is never given twice. Cell 4 checks the current run, and searches the kept ones for the token too. Delete a kept run yourself once it is no longer needed.
- **Never change `_Audit` by hand.** Cell 4's ninth check catches a changed or missing file.

## 9. When something goes wrong

| What you see | What it means and what to do |
|---|---|
| `cell 1` says "STOPPED BEFORE RESTARTING PYTHON" | The install could not do what it should; the message says what is missing or what changed, and Python was not restarted. If it names a package the runtime itself needs, detach the notebook, attach it again and run `cell 1` once more. |
| `cell 1` says "flowR IS NOT READY" | The reason follows it. If the download failed, download the archive it names on an approved machine and put it next to the notebook. If flowR "could not run on this cluster", the cluster does not let a notebook start a program: use one in dedicated (single-user) access mode. |
| "Step 04 (interpret-code) did not finish" | The model gave no answer for some pieces of code - the gateway was busy or down, or the token ran out. Check it with `cell 2`, paste a fresh token if needed, then run `cell 3` again: only those pieces are asked again. |
| "Step 05 (search-methodology) did not finish" | Some pieces of code are not yet searched and compared in full; their rows say how far each got. Paste a fresh token if needed and run `cell 3` again: only what is open is asked. |
| "The model stopped answering: the last N questions got no answer" | The message says what the last call returned. An expired token - a 401, say, or an error in place of the answer - wants a fresh one pasted into widget 02; a gateway that is down - a 503, say - wants waiting until it is back. Then run `cell 3` again, or every cell from cell 1: nothing is lost either way (section 13). If it happens again at once with a fresh token and a gateway that is up, the gateway may hold fewer tokens than `chat_token_limit` allows for: lower it (section 16). |
| A click on a reference only takes you to the first chunk, and nothing is filtered | Excel is not running the workbook's macro: it blocks macros in a file from the internet. Unblock the file and enable its content (section 7, Letting the macro run). Excel for the web, LibreOffice and Google Sheets do not run macros at all. |
| "No question showing C-0012 has been answered" | Questions showing the rest of the methodology were answered, but none showing that chunk: the gateway may refuse what it holds. The rows of the pieces affected say which chunk is still to search. |
| The cluster stopped, or the notebook detached | Start or reattach it and run `cell 1` to `cell 3` in order. Cell 3 carries the project's run on where it stopped: a finished step is not repeated, and no recorded answer is asked for again. |
| An input changed | Run `cell 3`: it says the input files changed and starts a new run, keeping the run before in `_Audit/previous_runs`; `Model_Package_Info` lists what changed since the run before. The same happens when the engine or a setting changes. |
| "Output.xlsm ... has been changed since the tool wrote it" | A new run would replace an `Output.xlsm` you have edited, so cell 3 stopped. Move it to another folder or rename it, then run `cell 3` again. |
| A unit of kind *File not read* | That file or expression could not be parsed. `Model_Package_Info` lists it with the reason; the rest of the package was still read. |
| A cell reads "This text could not be shown in plain words" | The tool withheld a text that contained technical traces; the text is in `run_log.txt`, in the run's scratch folder on the driver. Please report it; it is a defect in the tool. |
| "This is a defect in the tool, not in the model under review" | The coverage identity did not hold and the run stopped on purpose. Keep `Output.xlsm` and the `_Audit` folder and report it. |

## 10. Known limitations

- **Filtering on a click needs desktop Excel with macros enabled.** The links of Chunks_Model filter through a macro in `Output.xlsm`; Excel for the web, LibreOffice and Google Sheets do not run it, and there a click only takes you to the first chunk named. The macro was checked in LibreOffice's Excel mode, which loads and compiles it and runs it to the end, but filters on a list of values only in Excel.

- The content of images is never evidence. A formula given only as a picture is kept as a figure and never read as a formula. The words inside a picture are not read: the figure's caption and description stand for it, and the file's notes say so.
- The items of a list are shown inside the paragraph that introduces them, each on its own line behind `- ` or its number, and are not rows of their own. A list under a heading, with no paragraph before it, keeps its items as rows.
- A table of sentences is shown with each cell on its own line under the heading of its column (`Very Strong: ...`); a table of short values is shown as a grid, cells joined by `; `.
- Page headers, page footers and logos that repeat in the margins of a PDF are left out, and `Model_Package_Info` lists every one that was.
- the tool reads XML (also inside a `.txt`), `.mhtml`, `.docx`, `.pdf` and `.svg`. It does not read Markdown, LaTeX, RTF, spreadsheets or delimited text as documents, slide decks, OpenDocument files, e-books, old Office files (`.doc`, `.xls`, `.ppt`) or pictures on their own; each of those becomes one row on the sheet saying so, with what to save it as instead. Folders inside an input folder are read, in name order; a Word lock file, Thumbs.db and a saved web page's support folder are left out and listed on `Model_Package_Info`.
- The model package may be a tarball, a `.zip` of it, or its source folder. Only R is read as code: a package in another language is said to be one, and its files are kept as running text that nothing can be linked to.
- PDF input is read by position on the page, each line across its full width, from the top down: a page set in two or more columns is not split into them, so lines of different columns at the same height are read as one, and tables without ruling lines may be cut wrongly. The content account still closes - no word is lost - but the order can mix the columns. Check the chunks of such a file against the PDF, or give a `.docx` where there is one.
- R code is never run. flowR reads it, for the package's units and for the links between them. Unusual syntax becomes a *File not read* unit for that expression only.
- Stored data is decoded without R. Objects that are not tables, vectors or short lists are described but not taken apart; missing values of different kinds are not told apart.
- The relevant chunks and the deviations are the model's readings, not the tool's: code checks only that every chunk named was shown to the model. A search judges one batch of the methodology at a time, so a chunk that counts only beside another in a different batch can be missed; the comparison then sees every chunk found at once. A comparison whose chunks do not fit one question is asked in parts, each part seeing only its own chunks.
- A piece of code too long for one question is asked about part by part, since no question could show it whole: each part's question says it is a part, and what that part relies on in another part is said, not shown. What the model says of the parts is brought together for the piece; a comparison is made only once every part has been searched, and against everything found for the whole piece. Where one part is compared against a chunk and another part meets the requirement, the model may flag it all the same, having been told only that the other part exists.
- The model's tokenizer is not at hand, so the tool counts tokens its own way, on the high side (section 13): questions are smaller than they could be, never larger.
- The tool was developed against invented sample projects and a stand-in for `chat()`; results with a real model on a real package are still to be measured.

---

# Part III — For whoever reads the code

## 11. The one engine file

`engine/verifier.py` is the whole tool: the contracts and the words it may use, the front door that decides what a file is, the readers for the methodology and the documentation, the reader for the R package, the links between its units, the organisation's model and the two steps that ask it, the run, and `Output.xlsm`. Beside it is only `requirements.txt`; the steps are named in the engine itself, in `verifier.PIPELINE`. The tests and the maintainer's tooling live in `engine/tests/`, outside the tool itself.

## 12. The pipeline

Five steps, named in `verifier.PIPELINE`; nothing is loaded by path, and only a function the engine offers may be named.

| Step | Name | What it does |
|---|---|---|
| 01 | prepare-run | the manifest: the fingerprints of the inputs and of the engine, the settings, and what changed since the run before |
| 02 | read-inputs | the methodology, the documentation and the model package, each read into units |
| 03 | link-chunks | the links between the units of Chunks_Model - the Immediate Upstream and Downstream Model Chunk columns - read by flowR |
| 04 | interpret-code | each unit of Chunks_Model put to the organisation's model through your `chat()`, with the units it takes from and gives to as context, `parallel_chats` questions at a time, for the Code Interpretation (by LLM) column; a step with questions left unanswered does not finish, and cell 3 run again asks only for those |
| 05 | search-methodology | each unit of Chunks_Model searched against every batch of the methodology, then compared with the chunks found, through your `chat()`, `parallel_chats` questions at a time, for the column Relevant Chunks in Methodology (searched by LLM), the count of flagged items beside it, and the sheet Flagged_Items; it finishes only when every unit is searched and compared in full |

**How R code is read.** All of the package's R code is read by flowR, a static dataflow analyser for R (Sihler and Tichy, Ulm University; GPLv3); the tool has no R parser of its own. In step 02 one flowR run reads every R file of the package and its NAMESPACE: the syntax trees give the units of Chunks_Model - functions, statements, tests - and the NAMESPACE says which functions are exported. A package too large for one answer is read a file at a time. In step 03 flowR reads each function alone, so that memory stays bounded by the largest function, and each script - a test file, a vignette, the top-level code of an R file - whole. flowR parses the code with tree-sitter and decides, for every name, the definition it reads and, for every call, the function it calls; what it leaves unresolved, the package names (section 7). flowR is run on the cluster itself in one-shot mode: it reads the code as text and never runs it, starts no R process, opens no port and needs no network. It is fetched once by cell 1 and refused unless its SHA-256 is the one pinned in `verifier.py`. On a cluster that cannot reach GitHub, download the archive on an approved machine and put it next to the notebook; cell 1 uses it from there.

A step that carries out several parts keeps them in order, and a later part reads what the earlier ones have just recorded, as it would if each were still a step of its own.

## 13. How the model is used, and held

Cell 2 asks your `chat()` one question, to check the gateway answers. Cell 3 asks it three kinds of question, all through the same machinery.

**Step 04, one question per unit** of Chunks_Model, for the column Code Interpretation (by LLM). The question gives the unit's code, then, for context, the code of the units it takes something from (with the names it takes) and of the units that take something from it: the two link columns of the same row. The model is asked to explain the piece in the language of credit, for a CFA-level analyst checking it against the methodology - the concept, the inputs, the formula, the fixed parameters, and where it follows or departs from a standard convention - to state fact rather than rate or judge, and to decide itself how much detail the analyst needs.

**Step 05, searching the methodology.** The methodology's chunks are laid out in reading order, each headed by its Ref, the headings it sits under and its type, and packed into batches of up to `methodology_batch_tokens` tokens; a chunk too long for a batch is cut into parts at line ends, so that no line of it goes unsearched. The batches are the same for every unit. Each unit is put to the model once for each batch - the batch first, then the unit's code, the units it takes from and gives to, by name, and its interpretation from step 04 - and the model names the chunks of that batch an analyst needs to read to check the unit: those that describe what it computes, explain it, or inform it with a definition, a parameter, a floor or a convention. It is asked to judge by meaning rather than by shared words, and to answer in a fixed form (JSON); code reads the answer, keeps only chunks that were shown, and asks again, saying what was wrong, when the form or a Ref is off.

**Step 05, comparing.** As soon as a unit has been searched against every batch, the chunks found for it are put to the model together - with the unit's code, the code of the units it takes from and gives to, and its interpretation - and the model lists every potential deviation: a different formula, constant, floor, boundary, unit or order of steps; a requirement the code leaves out; something the code does to its result that the chunks do not describe; a chunk the code reads one way of several. Each deviation names the Refs it rests on and gives a pointed title saying exactly what differs, what the methodology requires, what the code does instead, why that is a deviation, and what it changes - which cases, in which direction, by how much where the code shows it. The model is shown one worked example of that depth, and told that statements which would fit any code, such as "this may affect the results", are no use. The comparison is a round of its own so that the model sees every chunk that bears on the unit at once: a floor stated in one batch and the formula it applies to in another are compared together, not flagged apart.

**What one question may hold.** Your `chat()` holds a question and its answer together up to `chat_token_limit` tokens. The model's own tokenizer is not at hand, so the tool counts tokens its own way, on the high side: a word one token for every six letters, every digit, sign and line break one, a character outside ASCII one for each of its bytes. Measured on prose, R code, tables of numbers, mathematics and JSON against six tokenizers (three of OpenAI's, Llama's, Mistral's and Claude's), its count was never below theirs. Each question is built to fit what is left once a share is kept for its answer - 6,000 tokens in step 04, 4,000 for a search, 10,000 for a comparison - and 1,000 more for the gateway's own wrapping; nothing of a piece of code or of a chunk of the methodology is cut: one too long for a question - or for a cell of Excel - is shown in several rows, and each row of a piece of code is a question of its own, which says which part of which piece it is; each part of a chunk of the methodology is shown under its own head, [C-0045-2, part 2 of 3 of C-0045]. Either is treated as one: what the model finds in any part of a piece counts for the whole piece, a chunk of the methodology found in any of its parts is compared in all of them, and the parts of a piece are compared only once all of them are searched, each against everything found for the whole. Only what the model wrote about a piece, and the context around it, are cut where they would not otherwise fit, and the cut is said. One kind of piece is shown to the model as a view rather than whole: a stored dataset - a table larger than `max_parameter_cells` - is asked about once, from its size, its columns and its first 50 rows, and the question says so; the workbook still shows every row of it.

**Many questions at once, and none lost.** As many questions go out at once as your gateway takes, up to `parallel_chats` (256). Asking starts with 32 out at once and doubles the number every round while no call fails, so it climbs to the gateway's limit within a few rounds; when a call fails - the gateway refuses it as one too many, or is busy - the number is halved, once a round, and then grows by one a round, so that it settles just under what the gateway takes. This is how TCP paces a network. A refused call is tried again after a pause with a random part, so that many refused together do not come back together. Against a gateway that took at most 40 calls at once, F_capital's 345 questions took 6.0 seconds this way, with nothing left for another cell, where sending 256 at once from the start took 15.9 seconds and left 136 to ask again. Against one with no limit, they took 3.1 seconds, against 9.9 seconds sixteen at a time. Every answer is held in memory the moment it arrives, by the thread that received it; only one thread writes records, in the order of the units, so the record never depends on which answer came back first. A cell that is interrupted, or a step that stops, therefore loses no answer: cell 3 run again writes what arrived and asks only for the rest. What `chat()` returns without an answer - a dictionary without "answer", or with an empty one, or anything else - counts as a failed call, as an exception does, and is tried again after the same pause. Once a cell stops asking, however it ends, its threads make no further try: a call still out is held when it returns, and nothing is asked twice when cell 3 runs again. A question is exact - its id is the hash of what was sent - so one already answered in this run is never asked again. When the questions already out, and four more, all come back without an answer, no more are sent: the model has stopped answering, most often because the token ran out. A question of step 05 left without an answer that shows more than one piece of the methodology is asked again split in two, so that one chunk the gateway refuses, or a question too long for it, holds up only itself.

**What is recorded.** The audit log's Model_Calls sheet holds every exchange: the question's id, the unit, the pieces of the methodology it showed, the tokens it took, every try and what went wrong with it, the answer, and what code read from it. A question of step 04 is kept word for word; a question of step 05 is kept by what it was built from - its unit, its pieces and its id - because it repeats the methodology, which the Records sheet holds already. An answer holding technical text - a Python trace, an internal name - is asked for again, naming it; any other word is kept as the model wrote it. Everything else the workbook shows - the reading, the accounts, the links - is made by code alone, and nothing in it depends on an answer.

## 14. Reading, and the content account

Every file read keeps a **content account** (`verifier.account`): the file's smallest pieces of text are counted straight from its bytes, then counted again in the units the tool produced, and the two must agree. A piece that is read but lands in no unit leaves the account open, and the file is named on `Model_Package_Info` with the reason, so nothing is dropped in silence.

## 15. What ships

The tool is `Verifier.ipynb` and two files in `engine/`: `verifier.py` and `requirements.txt`; this manual, `engine/Manual.md`, sits beside them. The repository holds nothing else that runs: no tests, sample projects or maintainer's scripts, and nothing in the engine ever read them. To change the notebook, edit its four cells directly: each is one call into the engine, and the only code of your own is `chat()` in cell 2.

---

# Part IV — Reference

## 16. Settings

Settings are an allow-list: a name that is not in this table is refused. The notebook sets the reviewer id, taken from Databricks.

| Setting | Default | Meaning |
|---|---|---|
| `max_parameter_cells` | 5000 | A stored table with more cells is a dataset rather than a parameter table: Chunks_Model still shows it whole, steps 04 and 05 ask about it once, from a view of its columns and first 50 rows, and Model_Package_Info lists it as not assessed. |
| `max_parameter_columns` | 50 | A stored table with more columns is a dataset, as for `max_parameter_cells`. |
| `max_file_mb` | 200.0 | A larger input file is not read and becomes a not-read unit. |
| `reviewer_id` |  | Who runs the notebook, taken from Databricks by cell 1; sent to the gateway by `chat()` and recorded against the run. |
| `parallel_chats` | 256 | The most questions steps 04 and 05 have out with the model at once. Asking starts at 32 and doubles while no call fails, then settles just under what the gateway takes (section 13); lower this only if the gateway must never see more than so many calls at once. |
| `chat_token_limit` | 40000 | How many tokens your `chat()` holds, a question and its answer together. Every question is built to fit it. |
| `methodology_batch_tokens` | 12000 | About how many tokens of the methodology go into one search question of step 05. Smaller batches mean more questions, each judged more closely; a batch never takes more than the question has room for. |


## 17. Extending the tool safely

| You want to add | Where |
|---|---|
| a tag rule for a new XML schema | `tag_rules.yaml` in the project's folder, beside its three input folders; or, for every project, `verifier.TAG_RULES_YAML` |
| a column or a sheet of `Output.xlsm` | `verifier.WORKBOOK_LAYOUT_YAML` and the row builder of that sheet in `verifier.py` |

After any change, see section 19.

## 18. What the tool needs

**Dependencies.**

| Package | Needed | Note |
|---|---|---|
| openpyxl>=3.1 | required | Output.xlsm and the record of a run |
| PyYAML>=6.0 | required | the pipeline and the tool's own rule files |
| numpy>=1.24 | required | reading stored data |
| rdata>=1.0 | required | reads stored R data without running R |
| pdfplumber>=0.10 | optional | PDF text and tables |
| pypdf>=4.0 | optional | a second PDF reader |
| flowR 2.15.8 (not a Python package) | required | reads the package's R code; fetched and checked by cell 1 |

**Installing.** Every package comes from PyPI (`https://pypi.org/simple/`), named in the engine, so the cluster's network has to let it reach PyPI; a pip index set for the whole cluster is not used. Cell 1 does not install rapidocr-onnxruntime, the optional reader of the words inside pictures: it brings OpenCV, whose newest wheels carry an OpenSSL that a FIPS-mode cluster refuses by stopping the whole Python process. A picture is then kept as a Figure, and says that its words were not read.

**What leaves the cluster.** Only this. In cell 1, pip asks PyPI for packages - their names and versions, nothing of yours - and flowR is downloaded from GitHub unless its archive is staged. In cell 2, one short test question goes to your `chat()`. In cell 3, step 04 sends each piece of the model's code - its text, file and lines, as Chunks_Model shows them - to your `chat()`, and so to your organisation's model gateway; step 05 sends the methodology too, chunk by chunk as Chunks_Methodology shows it, with each piece of code and its interpretation. Nothing else of a review leaves: the documents are read on the cluster by the tool itself, and flowR reads the code there in one-shot mode, needing no network.

## 19. Maintaining the tool

Everything that runs is in `engine/verifier.py`; the manual names the one place each thing lives (section 17). After a change, run a review on a project you know and compare its `Output.xlsm` with the one before: every sheet should differ only where the change meant it to.
