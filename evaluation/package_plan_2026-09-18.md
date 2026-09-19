# The package reading plan: what a file with no reader costs

**Measured 18 September 2026, engine 0.0.2, phase R5, with the stand-in model.**

R1's ledger extended the line coverage `read-package` already kept for parsed R files to every member of the tarball. On every sample it closes. This phase asks what that closing actually guarantees, and finds that the answer is less than it looks.

## The gap the account cannot see

The built-in tests place a member by where it lies: R code under `R/`, `tests/`, `data/`, `inst/`, `data-raw/` or `demo/`; stored data by its extension; a help page under `man/`. A member they place nowhere falls through to one unit of running text, cut at two thousand characters.

The line account reports that file as fully covered, and it is right to: every line does lie inside a unit. But the unit is undifferentiated prose. Nothing in it can be linked to a methodology statement, checked against a formula, or counted in coverage. **Conservation is not the same as usefulness**, and this is the one place the ledger's identity holds while the reading is still poor.

## The fixture

`engine/tests/fixture_package.py` is a tarball laid out the way real packages sometimes are and the tests do not expect:

| Member | What it is | Built-in reader |
|---|---|---|
| `R/main.R` | R code where it is expected | r-source |
| `inst/extra/helpers.R` | R code under `inst/` | r-source (already covered) |
| `inst/rates/zone_rates.csv` | a table of values | r-data (already covered) |
| `inst/doc/round_up_quarter.Rd` | a help page outside `man/` | **none** |
| `tools/calculations.R` | R code in a folder no list reaches | **none** |
| `tools/build.notes` | a member of no known kind | **none** |

## The result

| | off | rules |
|---|---|---|
| Units | 13 | **19** |
| Functions parsed | 3 | **6** |
| `tools/calculations.R` | one "Other file" | **3 Functions, 4 Formula statements** |
| `inst/doc/round_up_quarter.Rd` | "Other file" | **Help page** |
| `tools/build.notes` | "Other file" | "Other file" (named prose, correctly) |
| Calls | 0 | **1** |
| Content account | closed | closed |

**Three functions become six.** The R code in `tools/` that arrived as one block of text is parsed into functions and formula statements, which is what lets it be linked to a methodology statement, checked mathematically and counted in coverage. The account closed both times and told you nothing about the difference.

**A tidy package costs nothing.** With every member placed by the built-in tests, no question is asked at all — held as a test.

## What the answer may and may not do

It names, for each unplaced member, one of six readers AIVA already has: `r-source`, `r-data`, `help-page`, `vignette`, `table-file`, `prose`.

- **There is no reader that means skip.** An answer that leaves a member out is refused as self-contradictory. This is the one thing the vocabulary had to make impossible.
- **A wrong answer is allowed.** A member sent to a reader that cannot make sense of it becomes a unit saying so, exactly as today. A test sends every unplaced member to `help-page` and checks that all three still reach units.
- **The answer never reaches the parsers.** Not the R tokenizer, not the expression trees, not the decoder of stored data. A model's reading of code is an assertion *about* the code; a parse is a parse. The chosen reader is a router, and the routing is all it is.
- **It cannot touch a placed member.** Naming `R/main.R` is refused. The built-in tests are not its business.

18 corpus cases cover every way the answer can be wrong. The content account closes whatever the answer says, including a deliberately perverse one.

## Cost

One call per tarball that has an unplaced member, at the front of the run. A package the tests place entirely costs nothing.

## Limitations

- **Measured with the stand-in.** It reads the manifest and applies the rule the prompt describes — assignments and calls mean R code, braces after a backslash mean a help page. That shows the machinery and the vocabulary are sound. It does not show a real model classifies an unfamiliar layout well.
- **One fixture.** Built from the shapes the code's own folder lists exclude, not from a survey of real packages.
- **The account still cannot see the difference this makes.** It measures whether lines reach a unit, not whether the unit is any use. A second measure — how many members reach a reader more specific than "Other file" — would close that, and does not exist yet.
- **`prose` is a real answer, not a hiding place.** `tools/build.notes` is correctly given `prose` and correctly stays an "Other file" unit. That is the right outcome, but it means a genuinely unreadable member and a misclassified one look the same on the sheet.
