# Reading fidelity: what AIVA's reader keeps and what it loses

**Measured 18 September 2026, engine 0.0.2, phase R1. No language model was involved in any number on this page.**

Every input file is now counted twice over: once by the reader that slices it into units, and once — independently, straight from the bytes — by a content account that knows nothing about what the reader did. The account exists to answer one question that could not be answered before: *does AIVA lose anything when it reads a file, and does it ever show a word the file does not contain?*

## How a file is counted

The atom is the smallest piece of text that can be counted without interpreting it: a run without white space, after the same normalisation every unit's text goes through. Every atom ends in exactly one class.

| Class | Meaning |
|---|---|
| **in unit text** | it is in the text of a unit |
| **relocated** | it is kept, in a field other than text: a heading chain, a caption, the cells of a table, the number a document gave a paragraph |
| **rewritten** | it is read into another form and the form is named: an equation becomes AIVA's linear notation |
| **declared drop** | it is left out under a named rule: page furniture that repeats in a margin, a style or script element, an attribute the rules do not read |
| **not read** | AIVA says so: a part that could not be read, a page with no text layer |
| **unaccounted** | none of the above — **must be zero** |

And the other direction: every token a unit shows must come from an atom or from a transform named in the code (`DECLARED_MARKS`). Anything else is **injected** and must be zero.

`rewritten` is new. The plan named four classes; building the account showed that an equation fits none of them. It is not lost, and calling it relocated would be false — the symbols are read into linear notation and the original characters are kept nowhere. A fifth class that says so is more honest than forcing it into one of the four.

## What the account says about the four sample projects

| Sample | File | Atoms | In unit | Relocated | Rewritten | Dropped | **Missing** | **Added** |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A_minimal | parcel_pricing_method.xml | 436 | 368 | 53 | 8 | 7 | **0** | **0** |
| A_minimal | parcelcost_documentation.docx | 196 | 168 | 28 | 0 | 0 | **0** | **0** |
| A_minimal | the package | 135 | 135 | 0 | 0 | 0 | **0** | **0** |
| D_dosing | dosing_method.mhtml | 115 | 81 | 22 | 1 | 9 | **2** | **0** |
| D_dosing | dosecalc_guide.pdf | 63 | 55 | 8 | 0 | 0 | **0** | **0** |
| D_dosing | the package | 60 | 60 | 0 | 0 | 0 | **0** | **0** |
| F_capital | capital_methodology.txt | 454 | 350 | 78 | 20 | 6 | **0** | **0** |
| F_capital | capreq_model_documentation.docx | 189 | 151 | 38 | 0 | 0 | **0** | **0** |
| F_capital | capreq_user_guide.pdf | 66 | 54 | 12 | 0 | 0 | **0** | **0** |
| F_capital | the package | 183 | 181 | 0 | 0 | 0 | **2** | **0** |
| F_capital_known | *(identical to F_capital)* | | | | | | **2** | **0** |

**Nothing is added anywhere.** Across every sample and every format, not one token a unit shows is absent from its file. That is the stronger of the two guarantees and it holds today, before any guided reading exists.

**Three places lose content.** They are set out below. None was known before this phase; all three were invisible because nothing was counting.

---

## What was lost, and what to do about each

### 1. The title of a web-exported page. `dosing_method.mhtml`, 2 atoms

The `<title>` element of an MHTML file — here "Dosing method" — reaches no unit. It is the document's own name for itself, and in a Word file exported to the web it is often the only place the document's title survives, because the visible heading may be a styled paragraph with no heading level.

Consequence today: a methodology whose title appears nowhere else cannot be cited, linked or covered. It is silently absent from the outline the analyst confirms at step 07.

**Recommended: fix the reader, in R2.** This is a reader fault, not a candidate for guided reading — no model is needed to know that `<title>` is the document's title. A fault is a fault.

### 2. Word footnotes, endnotes, comments, headers, footers and tracked changes. 0 atoms on these samples, but demonstrated

None of the four samples has a `.docx` with a footnote, so the table above shows no loss. The account was built to count these parts anyway, and a fixture in `test_aiva0r_reading.py` plants a sentence in a footnote and in a text box: **the reader drops both, and the account now catches both and says which part they were in.**

This is the largest latent exposure in the reader. Real model documentation carries definitions, caveats and parameter values in footnotes routinely, and a validation tool that reads the body and not the footnotes will report a methodology statement as undocumented when the documentation is in a footnote two lines below.

**Recommended: fix the reader, in R2, for footnotes and endnotes at least.** Comments and tracked changes are a policy question rather than a reading one — a reviewer may or may not want an unaccepted insertion treated as what the document says — and should be a setting, defaulting to counted-and-named rather than read.

### 3. Code fence markers in an R Markdown vignette. `vignettes/capreq.Rmd` lines 7 and 11, 2 atoms

The lines ```` ```{r} ```` and ```` ``` ```` lie inside no unit. The code between them does. These are markup that separates content from content; they say nothing themselves.

**Recommended: declare the drop, do not change the reader.** A fence marker belongs in `declared drop` under a named rule, exactly as a style element does. Nothing is being lost; the account is simply not yet told that these are not content.

---

## What the account costs

It is drawn from the file bytes on every run, in the same pass that reads them. Across the four samples it adds under a second in total and no calls of any kind. It cannot stop a run: an open account writes a reading note, rows on `Model_Package_Info` and a line in the run summary, and every unit is delivered as before (R2, R3).

## What this means for the phases that follow

The plan assumed guided reading was needed where schemas are unfamiliar. The account partly agrees and partly redirects:

- **Two of the three losses are plain reader faults with no ambiguity in them.** No shape digest would help; they should be fixed deterministically in R2 and the account will prove they stay fixed.
- **The samples raise no ambiguity at all** — every one of the four closes on structure, and the two XML/text files with the most complex shapes (436 and 454 atoms, with equations, tables, figures and multi-level numbering) close completely. This is consistent with the frozen-interface rule: on these inputs a guided reading must change nothing, and there is nothing here for it to improve.
- **The case for R3 and R4 therefore rests entirely on the hard samples G, H and I**, which do not exist yet. Until they do, the benefit of guided reading is asserted rather than measured. That is the honest position, and it is an argument for building the hard samples earlier in the sequence than R6.

## Limitations of the account itself

- A PDF page with no text layer is counted as one atom and named as not read. The account cannot say how many words a scanned page holds without reading the picture, and it does not pretend to.
- Atoms are compared as tokens, so a reader that kept every word but garbled their order would still close the account. Order is checked by the frozen-interface snapshot, not here.
- The account of a package counts lines, not tokens, because a line is the unit `read-package` already works in. A member AIVA cannot read as text is counted as one atom.
- `injected` is measured against the transforms named in the code. Naming a transform that does not exist would hide an addition; the tests in `TheAccountClosesBecauseTheTransformsAreNamed` exist to keep that list honest by proving the account fails without each entry.
