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
- A step-level catch in `run_step` would make R2 hold for every step, not only the reading steps. `aiva5` has no room for it and it is outside the scope of ingestion.
