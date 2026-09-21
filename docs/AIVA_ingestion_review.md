# Ingestion review: findings and what was done about them

**Review 18 September 2026; fixes 21 September 2026. Engine 0.0.2.**

The review ended on one sentence: *almost every problem in ingestion was a failure to be honest about failure.* The reader rarely got a file wrong in a way that showed. It got it wrong in a way that closed the content account, produced units and looked fine.

Every finding below is pinned by number in `engine/tests/test_formats.py`, so none of them can come back quietly.

## Before and after

| # | Input | Before | After |
|---|---|---|---|
| 1 | A subfolder in an Inputs corner | **Run stopped**: `IsADirectoryError` | Walked into, files read, named by their path in the folder |
| 1 | An encrypted PDF | **Run stopped**: `PdfminerException` | One unit: *protected by a password; save an unprotected copy* |
| 1 | A package as a `.zip` | **Run stopped**: `ReadError` | Read, under the same limits as a tarball |
| 1 | A package's source folder | **Run stopped** | Read as the package |
| 1 | A damaged tarball | **Run stopped** | *could not be opened: it is damaged* |
| 1 | One file a reader fails on | **Run stopped**, every other file lost | That file named; the others read |
| 2 | `.xlsx` | Read as Word, failed, **account closed over nothing** | Read sheet by sheet: a heading over a table of stored values |
| 2 | `.pptx`, `.odt`, `.epub`, `.zip` | Read as Word, failed, account closed | Refused in plain words, with what to save it as |
| 2 | A large file that yields nothing and says nothing | Account **closed** | Account **open**: *it has probably not been opened* |
| 3 | Legacy `.doc`, pictures, binary data | **Decoded as Latin-1**, shown as paragraphs of mojibake | Refused; never decoded as text |
| 4 | Markdown | Flat paragraphs; `# Capital` a paragraph | Headings at their depth, lists, tables, fenced code |
| 5 | `.csv` / `.tsv` in a document corner | One paragraph | A table, first row naming the columns |
| 6 | RTF | Control words mixed into the units | Words only; font tables, pictures and control words left out |
| 6 | LaTeX | One paragraph | Sections as headings, items as a list; preamble left out |
| 7 | A Python model | `Other file` units, **nothing said** | *This does not look like an R package*, on the sheet and in the run summary |
| 8 | `~$method.docx`, `Thumbs.db`, `desktop.ini` | Read as documents | Left out, and listed |
| 8 | A saved web page's `_files` folder | *(would have been)* style sheets read as documents | Left out as the page's support folder, and listed |
| 9 | Any run | Nothing said about formats | *Read as: 2 XML, 1 Word. Not read: deck.pptx - a slide deck…* |
| 10 | Package lines held only as running text | Invisible to the account | Counted, and said on `Model_Package_Info` |
| 11 | Extend shape digests to `.docx` and PDF | *Retest before assuming* | Retested: **not extended**. See below |

## Finding 11: retested, and the answer is no

The review said the `.docx` and PDF readers had not been the problem *on the samples built to break them*, and asked for a retest before assuming that generalised.

The retest found a fault — in the measurement, not the reader. H's gold file scored "capped at two hundred litres" at the wrong depth, because the same sentence sits word for word in H's methodology, where the section has no title above it. The measurement found the methodology's unit first. Once the gold names the file a row is about, **the PDF reader places all three of H's headings, and the Word reader all three of I's**, with no guidance and no call.

There is no doubt in either reader for a digest to resolve, so none was built. The hard-sample floor for H rises from 2 to 3.

## What had to change in the design

**An eighth bundle.** The fixes needed about 300 engine lines, `aiva5_run_report.py` had 3 to spare and `aiva1_documents.py` 53, and a budget may not be raised. Following R0's precedent, `aiva1f_formats.py` holds the front door of reading: what a file is, how its bytes become text, which files of a folder are documents, and converting the formats AIVA has no reader of its own for. R11 now reads *eight* flat bundles. `aiva5` ended at exactly the 1,497 lines it started at.

**The content account gained a rule about nothing.** An account over nothing balances, so a file whose reader found nothing and said nothing used to close. That was the one place the identity held while everything was lost. A file over 1 KB that yields no text, and was neither refused nor said to be unreadable, now opens the account.

**Converted formats are counted from their own words.** Each converter returns markup, made by reading the structure, and words, made by taking the syntax away by rule — two pieces of code, so the account still sees the walker lose or add a word. It does trust the syntax rule. The two disagreed on LaTeX during the work (the words path counted `\documentclass{article}`, the markup path read only the body), which is what keeping them apart is for; the preamble is now left out by one rule shared by both.

## Limits that remain

- Slide decks, OpenDocument files, e-books and old Office files are refused, not read. A PowerPoint reader would need `python-pptx`, which is not on the approved index.
- A spreadsheet's formulas are never worked out: the value it saved is read. A workbook saved before it calculated shows stale values.
- LaTeX mathematics is kept as words and symbols, not read as an equation.
- Only R is read as code. A Python, SAS or MATLAB model is now *named* as one, which is honest, and is still not checkable.

## The three items left open, and what became of them (21 September 2026)

**The samples were not reproducible.** Wider than first reported: *every* sample's tarball and Word file changed on every rebuild, including A, D and F, which predate this branch. Two causes, both timestamps: the writer of stored R data stamps each `.rda` with the time and a file name in its gzip header, and Word stamps every member of its archive with the moment of saving. Both are now fixed at the source in `tools/build_samples.py`. `test_samples_are_reproducible.py` holds that two builds give identical bytes and that the samples in the repository are exactly what the builder gives. The frozen snapshot moved once, on one field (`file_sha256` of the six `.rda` units), recorded in `engine/tests/frozen/REFRESHED.md` as the last refresh of its kind.

**A fault outside reading could still stop a run.** Fixed. `run_step` now catches a step that cannot finish, writes it down in plain words, keeps the details in the run's work folder for a maintainer (not in the evidence pack), and goes on. Broken on purpose at step 05, the run still reached step 16 with every reading unit in `Output.xlsx`, and the steps after it did not cascade into failures. A pause is still a pause: it is how a run waits for a person or a token, and is never recorded as a step that did not finish. Room was made by moving the Inputs folder knowledge into the front door, where it belongs; `aiva5` ends at 1,497 lines, where it started.

**The sign-off bar is not met, and cannot be met here.** It needs the production model behind the Databricks gateway. What was done instead:

- **Cell 19** of the notebook runs the whole bar against the real `chat()` of cell 6. It changes no setting.
- **A dress rehearsal found a hole in the bar itself.** Against the stand-in in its misbehaving mode, every answer about F_capital's shape was refused, guided reading silently never happened, and test 4 said HELD. It had been inferring retries from call counts against a guessed allowance. It now counts refused answers from the call records, and says when guidance did not happen at all.
- **Against a misbehaving model, the first three tests still held.** No word lost or added, never worse than without guidance, the settled samples untouched. A bad model makes guidance useless; it cannot make it harmful. That is the difference between *safe* and *ready*, and only the fourth test, on the real model, can show ready.

