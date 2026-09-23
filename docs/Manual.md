# Verifier — the manual

**Version 0.0.3, September 2026.** One document for everyone: the person who runs a review, the person who reads its output, the person who reviews the code, and the person who maintains it. Part I is for everyone. Part II is for whoever runs a review. Part III is for whoever reads the code. Part IV is reference.

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
| R14 | The map is exhaustive and verifiable. Every step of the Model Implementation Map is parsed from the code or quotes it word for word; every model unit is a step of the map, belongs to one, or is in the branch of units no final output reaches; every step ends at a named raw input; and what the tool cannot follow is a named gap, never a silence. |

**The wording rule.** The tool rates nothing. Words that grade how serious something is, and the two policy terms that classify an observation, never appear in anything the tool produces, because grading and classifying are decisions of the validation policy and of people, not of a tool. The tool says what it observed, where, and what a sensible next step would be. The list of words lives in one place in `verifier.py`, and a test scans the engine, the workbook, the report and this manual for them on every build.

## 4. Vocabulary

Every word the tool can show in a status, a relation or a "how established" cell comes from one list in `verifier.py`. The tables are generated from it.

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

## 5. The notebook, four cells

The notebook is `Verifier.ipynb`. Four cells, run in order.

| Cell | What it does | When to run it again |
|---|---|---|
| **cell 1** | Makes the widgets, installs a package only if one the engine imports is missing, loads the engine, and prints what the other three cells do | after a cluster restart, or after pasting a package index |
| **cell 2** | Your organisation's `chat()`, already filled in; it reads the endpoint, token and user id through `live()` at the moment it is called. Asks it one question, then makes the project's `Inputs` folders and prints their paths | when the gateway or your id changes |
| **cell 3** | Reads every input file, maps how the model computes what it returns, and asks your model to interpret the code, name the concepts, close the gaps and judge every link. Prints what each step did | after a token expires, a cluster restarts, or you add an input: finished steps are never repeated |
| **cell 4** | Checks the finished run folder against its own record | after any run |

**The widgets.** Eight: the endpoint and token for the model gateway (01, 02); your user id (03), which is both the id sent to the gateway and the name recorded against the run; the model id (04) and project date (05); a package index (06), used only if a package must be installed; how many calls at once (07); and the token cap (08). Projects live in `Projects` next to the notebook, each in its own folder, `<model id>/<date>/Inputs`. A session keeps working on the run it opened; a new session, after a restart, starts a new run.

**The token.** It is read at the moment `chat()` is called, never stored. When it runs out mid-run, cell 3 says so and stops; paste a fresh one into widget 02 and run cell 3 again, and it carries on from the step that stopped.

**How long a run may take.** Cell 3 works in the cell itself, so you can see it and interrupt it. `FOREGROUND_MINUTES` at the top of the cell is how long it may work before it stops by itself and asks you to run it again; it is 600 by default, which is longer than any run we have seen.

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

| Sheet | What it holds |
|---|---|
| `Model_Package_Info` | what was read and what was not, each file's content account, the coverage identity, the run's progress |
| `Chunks_Canon` | every unit of the methodology, with its place in the outline |
| `Chunks_Doc` | every unit of the documentation, with what it was linked to, what was searched, its checks, its status and its flagged items |
| `Chunks_Model` | every unit of the model package, with the AI's interpretation, its status and its flagged items |
| `Concepts` | one row per concept of the model, with every form it is written in and where |
| `Model_Implementation_Map` | how the model computes what it returns: each final output down to its rawest inputs, one row per variable |
| `Mapping_Coverage` | one row per final output and one per corner: what is covered and what is not |

**How to read one row of the map.** One row is one variable: where it sits (the Map ID, a column per level, and how deep it is), the variable itself with the unit that defines it, the code as written and its concept, the function that defines it with its unit, and what it is computed from — each of those a row beneath it. Section 8 describes the sheet in full.

**How to read one row of `Chunks_Doc`.** What the passage is (blue identity columns and its text), what it was linked to in the methodology and in the model, with the relation and **how established**, what was searched for it and why it was not linked, then its checks, its status and its flagged items. Several values in one cell stand on separate lines, each prefixed with its reference. Text taken from your inputs or from the model is always shown in quotation marks with its citation.

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

**The value-comparison rule** is one rule, used for parameter tables, numbers in code, numbers in roxygen text and numbers in the documentation. Its full text is on `Model_Package_Info`. In short: percent, basis points and scientific notation are converted first; a value agrees at stated precision when rounding it to the decimals of the methodology's value gives that value; there is no hidden tolerance. A cell reads like "package 0.10, methodology 0.15 (C-0017 row Retail): differs".

**The mathematical check.** For a linked function or statement and a passage that states a formula, the tool aligns the symbols first (shown as "with rho = ρ"), then tries to show symbolically that both sides are equal, then evaluates both at 200 seeded points, including points at and around every threshold. *Differs* always comes with a counterexample: the inputs and both results. *Could not be decided* names one reason from a fixed list and is never clean.

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

**Where the two mapping sheets went.** Until version 0.0.3 two mapping sheets, one of the model to the methodology and the documentation, the other of the documentation to the methodology and the model, held one row per model unit and one row per documentation unit: what each was linked to, what was searched for it, its checks, its status and its flagged items. The Model Implementation Map now shows the model unit in its place in the computation, so those two sheets are gone and nothing they held is lost. A model unit's status and flagged items are on `Chunks_Model`, beside the unit itself. A documentation unit's links, what was searched, its checks, its status and its flagged items are on `Chunks_Doc`, beside the passage.

**Mapping_Coverage**, read off the map. One row for each final output: how many steps it takes and how deep they run, what it rests on — arguments, columns of the data given, stored tables, files, hard-coded numbers — how many of its steps are linked to a methodology passage (*Covered*) and how many are not, what its checks said (agreeing, differing, undecided), how many of its units need attention, and its flagged items with a count by category. Then one row for each corner, each read the way that corner needs:

| Row | Covered | Not covered |
|---|---|---|
| Model units | units a final output reaches: a row of the map, or the roxygen, help page, test or statement belonging to one | the units no final output reaches: dead code, a second way in, a function only the tests call |
| Methodology passages | passages a unit on the map is linked to | passages stating a number, formula or rule that no step implements. The rest state nothing to implement |
| Documentation passages | passages a unit on the map is linked to | passages describing nothing in the map and naming none of the model's concepts |

Every number on this sheet is counted from the rows written to the map and to the Chunks sheets, so the sheet and the map always agree. The coverage identity is checked separately, by counting the statuses on `Chunks_Model` and `Chunks_Doc` against what the step account-coverage counted.

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

## 8. The Model Implementation Map


**The Model Implementation Map.** The sheet `Model_Implementation_Map` shows how the model computes what it returns, and nothing else: only what a calculation reaches is on it. One row is one variable. Reading a row from left to right: where it sits (the Map ID, one column per level — `MapID1`, `MapID2`, … — so any level can be filtered, and a parent leaves the deeper columns empty; the columns fold away with the + above them), then **Output Variable**, the one variable that row is about, with the model unit that defines it, the code as written, and the concept it is (a `K-` reference); then **Function Name**, the function that defines it, with its model unit; then **Arguments**, what the variable is computed from, separated by semicolons. Every name in Arguments is the Output Variable of a row directly beneath it, so a value can be followed down to the raw inputs it rests on: an argument of the final output, a column of the data given, a stored table, a file, or a hard-coded number, each a row with no function of its own. A reference is a link: clicking a `M-` reference opens that unit's row on `Chunks_Model`, and a `K-` reference its row on `Concepts`. The rows are grouped, each parent above its members, so a branch opens and closes with the + and − at the left; Excel groups eight levels deep and a deeper row is indented instead.

A called function is entered with the arguments that call gives it, so what it computes inside stands under the value it produces, and a parameter is never a row of its own: the row is the argument the call gave it. A function that calls itself stops there, keeping what the call is given. What no final output reaches is **not on this sheet**: dead code, a second way in, a function only the tests call, the methodology no step implements and the documentation describing nothing in the map are all counted on `Mapping_Coverage`, where each has its row.

**Choosing the final outputs.** Code proposes as a final output a function nothing in the package calls that is exported or that the package's tests or vignettes call (step 05a); cell 3 and cell 4 both say which. Where code proposes none, every function nothing in the package calls stands in, so the map always has a top.

## 8a. Concepts

**The model is the basis.** A concept is one of the model's: a name its code gives something — a function, an argument, a variable a statement sets, a stored table or one of its columns — together with how the model's own roxygen and help pages describe it, word for word (`pd`, described by its `@param` as *probability of default*). Names the code only calls, such as base functions, and generic names such as `x`, `data` or `result`, are not concepts.

**The documents are searched for those, and nothing else.** A term of the methodology or the documentation is extracted only when it has a likely equivalent in the model; a term with none is never extracted, however important it looks. Three kinds of evidence, kept apart:

1. **The same words, found by code** (step 06, `extract-concepts`, in cell 3, before any model call): the words of the model's name (`asset_correlation` in *asset correlation*), or the words the model uses to describe it (*probability of default*), compared in lower case and singular, with only spaces, hyphens or underscores between them. Where the documents define an acronym — *stand-alone credit profile (SACP)*, or a glossary entry written as its own heading — and one side of it is already one of the model's forms, the other side becomes one too, with the unit that defines it.
2. **The rest of the model**: other model files that write a concept's name — a test, a vignette, a help page — found the same way.
3. **Candidate synonyms and acronyms, guessed by the model** (step 07b, `judge-concepts`, after you confirm the outline): only for methodology and documentation units where code sees a likely model concept it could not prove — a name whose parts begin the unit's words (`adj_rating`, *adjusted rating*), an acronym-like name spelled by the initials of words in a row, a description sharing its words. The model is shown those concepts and asked which the unit names, copying the unit's words; a name not in the unit word for word refuses the whole answer.

**Verbatim, always.** The Chunks sheets' column **Extracted concepts with candidate equivalent in model** shows, for each unit, the words that unit writes, character for character — *PD*, not the model's `pd`; *PDc* as the text capitalises it — joined by `;`. It never shows the model's name for them. That mapping, and every guess in it, is on the sheet **Concepts** only: one row per model concept, with the names the code gives it, how the model describes it, the same words found in the methodology, the documentation and the rest of the model, and — in a column of their own, headed as the AI's guess — the synonyms and acronyms the model found, each as written and with its units.

**How concepts steer the mapping.** The search for corresponding passages (step 07c) runs after the concepts, and a passage that names the same model concept as the unit comes first: that signal counts `concept_weight` times as much as any other and is the first to fill the places reserved on each shortlist. The reason shown for such a candidate begins *shares the concept*.

## 11. The run folder as an evidence pack

The three files in `_audit/` are the record. `records.jsonl` holds every record of every kind, one per line, each tagged with its kind, in the order written and never rewritten; `calls.jsonl.gz` holds every exchange with the model, prompt and reply; `manifest.json` holds the run's identity, the fingerprint of every input, the fingerprint of every engine file that ran, the coverage account and the package as described. Cell 5 verifies a pack from these three files alone: that the inputs are the ones fingerprinted, that the engine files match the release, that re-reading the inputs gives the recorded content hashes, that the hash chains verify (the graph, the determinations, and your decisions on what is in scope and what the final outputs are), that every unit has one status and every citation resolves, and that no token was written anywhere. A changed byte in an input, a removed record or an edited status is caught.

## 12. When something goes wrong

| What you see | What it means and what to do |
|---|---|
| "Your notebook session has crashed" right after `cell 3`, with *compiled using NumPy 1.x cannot be run in NumPy 2* or *PyArrow must be installed* in the output | An install moved a package the runtime needs to start, so every restart crashes. Detach the notebook from the cluster and attach it again: that discards what `cell 3` installed, and only this notebook was affected. Do not restart the cluster for this. Then run `cell 2` onwards again. Since 21 September 2026 `cell 3` keeps the runtime's own numpy, pandas, pyarrow and scipy exactly as they are, and checks before restarting that they still import together, so this should not happen again; if it does, tell whoever maintains the tool. |
| `cell 3` says "STOPPED BEFORE RESTARTING PYTHON" | The install changed something the runtime needs to start, and `cell 3` noticed before restarting, so the session is still alive. Detach the notebook and attach it again to undo the install, and tell whoever maintains the tool which package pip named. |
| `cell 3` says pip could not find versions that fit | The index has no version of a package the tool needs that works with this runtime's own packages. Nothing was changed. Ask for an older version of the package pip names to be added to the index. |
| The status cell says the run waits for a fresh token | The token ran out. Paste a new one (mode B: then run `cell 1`). No question is repeated. |
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

## 14. The one engine file

`engine/verifier.py` is the whole tool: the contracts and the words it may use, the reading floor, the front door that decides what a file is, the readers for the methodology and the documentation, the reader for the R package, the data flow it traces through that package, the search and the judgement of every link, the concepts, the map's agents, the run, and `Output.xlsx`. Beside it are only `pipeline.yaml`, which names the steps, and `requirements.txt`. The tests and the maintainer's tooling live in `engine/tests/`, outside the tool itself.

## 15. The pipeline

Five steps, named and versioned in `pipeline.yaml`; nothing is loaded by path, and only a function the engine offers may be named.

| Step | Name | What it does |
|---|---|---|
| 01 | prepare-run | the run folder, the manifest, the fingerprints of the inputs |
| 02 | read-inputs | the methodology, the documentation and the model package, each read into units |
| 03 | build-map | by code alone: the graph, the data flow of the package (read by flowR), and the model's concepts |
| 04 | read-with-ai | what each piece of code does, the concepts only a reader can confirm, the map's agents closing the gaps code named |
| 05 | link-units | two passes of search and judgement: candidates by code, then the model's judgement on each |

**How the data flow is read.** The package's R code is read by flowR, a static dataflow analyser for R (Sihler and Tichy, Ulm University; GPLv3). flowR parses the code with tree-sitter and decides, for every name, the definition it reads; for every call, the function it calls; and for every argument, the parameter it becomes there. The tool decides what is particular to a model: a column a dplyr verb creates, a stored table, a file a reader opens, and the places left as gaps for the model's agents. flowR is run on the cluster itself in one-shot mode: it reads the code as text and never runs it, starts no R process, opens no port and needs no network. It is fetched once by cell 1 and refused unless its SHA-256 is the one pinned in `verifier.py`. On a cluster that cannot reach GitHub, download the archive on an approved machine and put it next to the notebook; cell 1 uses it from there.

A step that carries out several parts keeps them in order, and a later part reads what the earlier ones have just recorded, as it would if each were still a step of its own.

## 16. How the model is used, and held

The model is asked questions whose answers are **choices among things code has already decided to show**: which of these lettered passages corresponds, quoting words from each; what this function does, in plain words; which reader should take this file; what this tag is for. Every answer is validated by `verifier.validate_answer` before anything is done with it: a quotation that is not word for word in the passage, a reference to a passage that was not shown, a planted control passage accepted, a self-contradiction — each is a refusal, and a refusal leaves the unit untraced and flagged. Nothing is repaired. A refused, failed or absent answer never stops a run and never changes an input.

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
| `reviewer_id` |  | Who runs the notebook; recorded with confirmations and determinations. |
| `reviewer_role` |  | The role of that person. |
| `read_pictures` | True | Read the words inside pictures by OCR when the optional package rapidocr-onnxruntime is installed. The words are shown under the Figure as a machine reading; a Figure still ends for manual review. |
| `interpret_code` | True | Ask the AI to say in plain words what each function, formula statement, top-level statement and test block does, shown with where it sits in the whole package. Fills the column LLM Interpretation on Chunks_Model. One question per piece of code; switch it off to save the calls. |
| `signals` | ['fields', 'bridge', 'references', 'anchors', 'signatures', 'propagation'] | The search signals in use; the recall ladder (`develop.recall`) switches them off one by one. |

`concept_weight` (default 2.0): how much more a shared concept counts in the search than any other signal. `concept_batch` (default 8): how many units one extraction question shows the model. `concept_candidates_max` (default 40): the most model concepts shown to the model in one question, and the most suggested for one unit. `concepts_with_ai` (default true): whether the model is asked for synonyms and acronyms code could not prove; switched off, only what code proved stands.

`map_granularity` (default `statement`): how fine the map is — `statement` gives a row for every variable; `function` folds a variable into what it rests on, leaving the values that cross a function call and the raw inputs. `map_rows_max` (default 5000): where a map stops; it says so in a row of its own, and names the setting. `map_hops_max` (default 8): the most turns the Tracer takes on one gap. `map_calls_max` (default 200): the most questions the map's agents ask in one run, the Tracer's and the Namer's together. `map_with_ai` (default true): whether the map's agents are asked at all.

## 21. Extending the tool safely

| You want to add | Where | What must be re-evaluated |
|---|---|---|
| a tag rule for a new XML schema | `Inputs/tag_rules.yaml` of the project; or, for every project, `verifier.TAG_RULES_YAML` | `test_documents.py`; the outline of one real document |
| a question type | a prompt in `verifier.PROMPTS`, a validator branch in `verifier.validate_narrow`, a handler in the stand-in | the bad-answer corpus; the token budget for the largest unit |
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

**The implementation map.** `develop.map_measure` measures the map of `J_pipeline` against its answer key, part by part, and `develop.map_report` is the sign-off bar of its agents, four tests: the map holds every part of the answer key, including the gaps on the path the agents traced; every link the AI declared quotes the code word for word; the shape of the map is the same as with no model at all, because code decides it; and every question the agents asked was answered and accepted the first time, with every gap on the path ending traced or with a reason. With the stand-in all four hold, and the bar says so while reporting itself **not met**: the stand-in shows the machinery is sound, not how a model traces a gap it has never seen. Run it on your own gateway from cell 5 with `APPENDIX = "map-sign-off"`. Rehearsed against a model that declares links quoting code that is not there, the fourth test does not hold and the bar says NOT met.



## 23. Maintaining the tool

