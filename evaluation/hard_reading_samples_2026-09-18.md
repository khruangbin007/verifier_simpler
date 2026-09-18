# The hard reading samples: G, H and I

**Built and measured 18 September 2026, engine 0.0.2. No language model was involved in any number on this page.**

R1's report closed with an argument against its own plan: every existing sample closes its content account on structure, so the case for guided reading was asserted rather than measured, and the samples that could measure it did not exist. This phase builds them.

Each sample is a complete project that runs end to end. Each stresses one corner of the reader and is ordinary everywhere else, so that a number that moves can be attributed. R9 holds throughout: the flavours — library lending, greenhouse irrigation, courier shift pay — are invented and carry no domain concept.

| | Stresses | The hard file |
|---|---|---|
| **G_schema** | an XML schema whose tags are named nothing the rules know, with lists inside table cells | `lending_rules.xml` |
| **H_twocolumn** | a PDF in two columns, running header and footer on every page, a footnote, an annex whose heading carries no number | `irrigate_field_guide.pdf` |
| **I_wordtraps** | a Word file whose headings are bold paragraphs with no style, words inside a text box, an unaccepted insertion and an unaccepted deletion | `shiftpay_documentation.docx` |

Each carries a `gold_reading.csv`: a phrase a correct reading puts in some unit, where it sits in the file, and the depth of the heading it belongs under where the file makes that plain. It is reading gold — it says nothing about links, checks or statuses.

## Where the reader stands

| Sample | Gold phrases read | Heading depths right | Units carrying a chain | Content account |
|---|---|---|---|---|
| G_schema | **8 / 8** | **0 / 4** | **5 / 17** | open, 9 atoms |
| H_twocolumn | **7 / 7** | **2 / 3** | 20 / 21 | open, 3 atoms |
| I_wordtraps | **7 / 8** | **3 / 3** | 20 / 20 | open, 6 atoms |

The reader is considerably better than the plan assumed, and worse in one specific way the plan did not name.

**The PDF is not the problem.** H was built to break the weakest reader in the engine, and it did not break it. Two columns are read in the right order, the running header and footer are dropped as furniture and named, the footnote is read, and the unnumbered annex heading is placed. `irrigate_field_guide.pdf` closes its content account completely: 213 atoms, nothing lost, nothing added. The plan's expectation that PDF layout would be the main casualty was wrong.

**Word's traps are mostly survived.** A heading made of nothing but bold — no style, no outline level, no number — is placed at depth 1, all three times. The words inside a text box reach a unit. An unaccepted deletion is left out, which is correct: an unaccepted deletion is not what the document says, and the account is the right place to name it rather than the units.

**The unfamiliar schema is the real gap, and it is a gap of shape, not of words.** Every one of G's eight gold phrases reaches a unit. Not one of its four heading depths is right, and 12 of its 17 units carry no heading chain at all. `discover_families` reads `<statementbody>` as a paragraph and `<gridholder>` as a table — it is doing its job on the tags that hold content — but it does not see `<blockcaption>` as the heading of `<ruleblock>`, so the document arrives as a flat list of statements. A rule stated under "Fines" cannot be told from one stated under "Renewals".

That is exactly the shortfall guided reading is for, and it is now a number rather than a belief: **0 of 4.**

## What building the samples found in the reader

### The reader was inventing words. Fixed here.

G puts two list items inside one table cell. `element_text` ran the children of an element straight together, so the cell arrived as

> renewable twice**no** fine in the first two days

producing the tokens `twiceno` and `renewablefine` — words that appear nowhere in the file. The content account caught it as **injected**, which is the first time anything has been.

This is not a shortfall to be measured later. R13 says nothing may be added, and text AIVA made up is a breach of it, not a weakness in it. `element_text` now separates a child that is a block of its own with a space. The frozen-interface snapshot confirms no existing sample unit moved.

R1's report said "nothing is added anywhere". That was true of the four samples then in the repository and false of the reader. This is the argument for hard samples in one line.

### A section number reaches no unit

H and I number their sections in an attribute the rules read (`num="1."`). The number reaches the block and then stops: the heading chain says "Watering windows", never "1. Watering windows". The account reports the numbers as lost, which is what they are.

This matters more than three atoms suggests: a citation to "section 2" cannot be resolved against a document whose section numbers AIVA never kept. **Recommended for R2**, with the other reader faults.

### G's table caption is dropped

`<gridcaption>Table 1. Loan period by item class</gridcaption>` reaches neither the table's caption field nor any unit. Part of the same shape problem as the headings: the tag is not recognised for what it is. Likely to be fixed by the same work.

## How the samples are held

`test_hard_reading_samples.py` holds two lines at once.

**A floor that may not fall.** What is read today stays read: phrases found, heading depths right, units carrying a chain, all recorded as numbers in the test. Any phase may raise them. None may lower them. And on all three samples, nothing may ever be added again.

**An expectation that is allowed to be short.** What the gold asks for, with each shortfall named in plain words in the test that records it. When R3 closes G's heading gap the test that says "an unfamiliar schema is still read flat" will fail, and it says so in its own message: *raise the floor and say so in the report.* A test that fails because the engine got better is the right way round.

## What this changes about the plan

- **R2's list is now specific and evidenced.** Four reader faults, all deterministic, none needing a model: the MHTML `<title>`, Word footnotes and endnotes, XML section numbers, G's table caption. The `.Rmd` fence markers want a declared drop rather than a fix.
- **R3's case is made, and narrowed.** Guided reading has one measured job on this evidence: work out the shape of a schema the rules do not know. Not layout, not Word, not PDF — shape. The digest for G needs to carry what `<ruleblock>` contains and how `<blockcaption>` sits inside it, and nothing about page geometry.
- **R4's case is not yet made.** Nothing in G, H or I needs a block-by-block decision that rung 1 could not settle with a rule. R4 should wait for an input that demonstrates the need, rather than being built because the plan lists it.
- **The sign-off bar in R6 is now runnable.** It compares `off`, `rules` and `rules_and_spans` on these three samples against these numbers.

## Limitations

- Three samples cannot represent the range of real inputs. They represent three specific difficulties, chosen because the reader's code has the least support for them.
- The gold is written by the same hand that built the sample, so it tests the reader and not the gold. Levels in the first draft conflated a section's printed number with its depth, which the measurement caught and which was corrected before the numbers above were taken.
- `I_wordtraps` deliberately leaves open what should happen to an unaccepted insertion. The reader treats it as what the document says. That is a policy question for a setting in a later phase, not a reading question, and this sample exists partly to keep it visible.
