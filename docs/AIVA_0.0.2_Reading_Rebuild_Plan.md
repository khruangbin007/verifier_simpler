# AIVA 0.0.2 — Reading Rebuild Plan

**Agent-guided slicing with a closed content account, for the three unit sheets only**

Companion to `AIVA_0.0.1_Build_Plan.md`. Same house rules, same phase discipline (Section 3.2 of that plan applies to every phase here unchanged).

---

# 0. Scope

**In scope.** How the units on three sheets of `Output.xlsx` are prepared:

| You said | Sheet name in `workbook_layout.yaml` | Step | Skill | Record kind |
|---|---|---|---|---|
| Chunk_Methodology | `Chunks_Canon` | 02 | read-methodology | `chunks_canon` |
| Chunk_Documentation | `Chunks_Doc` | 03 | read-documentation | `chunks_doc` |
| Chunk_Model | `Chunks_Model` | 04 | read-package | `model_units` |

The sheets keep their present names. Renaming them ripples into the layout file, the workbook tests and the manual for no gain.

**The one requirement.** Reading may be guided by the model, but it must **add nothing that is not in the input and lose nothing that is**. This plan turns that sentence into an identity that is checked on every run.

**Frozen interface.** Everything downstream of step 04 is untouched. Concretely, these do not change: the `Chunk` and `ModelUnit` dataclasses (one defaulted field is appended, see 2.8); the record kinds above plus `parameter_tables`, `package_info`, `read_repairs`, `info_rows`, `outline`; reference numbering (`C-`, `D-`, `M-` in reading order); `content_hash`; the columns of the three sheets.

**The regression bar that makes the scope truly local.** On the four existing sample projects (`A_minimal`, `D_dosing`, `F_capital`, `F_capital_known`) every existing field of every unit record must come out **identical** to today. Then no gold file, no harness number and no recall figure moves, and steps 05 to 18 need no re-baselining. The agent earns its place on inputs the present reader handles badly, not by reshuffling inputs it already handles well.

**Out of scope** (Section 5): mapping, checks, headings as units, the R parser, value decoding, the formula parser, the skills-folder reorganisation.

---

# 1. Findings that shape this plan

Measured in the repository as it stands, not assumed.

| # | Finding | Consequence |
|---|---|---|
| F1 | `aiva1_documents.py` is **1,497 of 1,500** lines. `aiva0_shared.py` is **450 of 450**. `aiva5_run_report.py` is **1,493 of 1,500**. | None of the new code can live where the reading code lives. A sixth bundle is unavoidable, and R11 must say so. |
| F2 | The generic asking machinery (`load_prompt`, `estimate_tokens`, `prompt_budget`, `cut_text`, `last_json_object`, `strict_json`, the front half of `validate_answer`) lives in `aiva3_mapping.py`, which sits **above** `aiva1` and `aiva2` in the one-way import order. | Steps 02 to 04 cannot reach it. It must move down. This is the only touch outside the reading code, and it is a relocation with no change of behaviour. |
| F3 | Steps 02 to 04 are not in `CHAT_STEPS`, so `run_step` hands them `ask=None`. The `confirm-outline` skill says "Use before any chat() call is spent." | The first calls of a run move from step 07a to step 02. The token must be valid earlier; the call-plan cell and one skill description change. |
| F4 | `read_corner` is one clean seam for both document corners: `read_file_blocks` then `blocks_to_chunks`. | One insertion point serves `Chunks_Canon` and `Chunks_Doc` alike. |
| F5 | The package side already has half a content account: `read_package` records `nonblank_lines` per parsed R file "for identity part 3: the lines that must lie inside a unit". | The ledger for `Chunks_Model` extends something that exists rather than inventing something new. |
| F6 | Five places turn source text into unit text by something other than copying: headings are consumed into `heading_chain` (`blocks_to_chunks` does `continue`); `fold_lists` joins with a space and writes `LIST_MARKER` into `display`; reconstructed numbering is prefixed to the chain; `math_to_linear` and `latex_to_linear` render an equation as linear text that is not in the source; `picture_words` reads text out of a picture. `normalise_text` runs on every block. | None of these is wrong. All of them are **undeclared**. A content account must name each one, or it will report them as loss or as addition. |
| F7 | `element_text` skips the families `figure`, `equation`, `ignore`, `caption`. Three of those become blocks of their own. `ignore` is a true drop. | The model must never be able to assign `ignore`. Only the shipped rules and the analyst's `Inputs/tag_rules.yaml` may. |
| F8 | `infer_levels` ends in `block["level"] = max(1, current) if current else 1`: a heading with no numbering silently takes the level of the heading before it. | That branch is the clearest "the reader is guessing" signal in the code, and the natural trigger for asking. |
| F9 | R5 already reads "Everything except the model's answers is deterministic … A run can be replayed from its recorded answers." | This design does not break R5. It moves where a recorded answer can have effect, which the manual must say plainly. |

---

# 2. Design

## 2.1 The principle

> **The model chooses; it never writes. And it chooses only among options that code has already proved safe.**

Every answer the model gives in steps 02 to 04 is a selection from a closed list that code built from the input: a tag name *that occurs in this file*, a family *from the fixed list*, a block reference *inside this window*, a level from 1 to 9, a reader *from the fixed list*, a furniture line *that code has verified repeats across pages*. There is no field in any answer through which prose can reach a unit. "No artificial content" therefore is not audited for; it has no channel.

Two options are withheld from the model on purpose, because each is a way to lose content: the family `ignore` (F7), and any way to leave a package file unread. A file of unknown kind becomes a unit with a `read_problem`, as today.

This is R3 and R7 applied one step earlier than before. The untrusted text inside a digest can at worst talk the model into a wrong *label*; the ledger and step 07 then show it. It cannot add or remove a word.

## 2.2 Three layers, one of them guided

```
bytes ──(a) extraction──▶ addressed blocks ──(b) slicing──▶ units
        deterministic      B-0001 … B-0842     guided        C-, D-, M-
        ledger checkpoint 1                    ledger checkpoint 2
```

- **(a) Extraction** stays exactly as it is: `blocks_from_docx`, `blocks_from_pdf`, `blocks_from_markup`, `blocks_from_mhtml`, `unpack_package`, `parse_r_source`, `decode_data_file`. It gains an account of what it took in.
- **Addressed blocks.** Each block gets a reference `B-0001…` per file, in reading order, recorded in the store. Blocks are the only thing the model is ever asked about.
- **(b) Slicing** is where guidance enters, on two rungs (2.5). The unit's text is assembled by code from block text, exactly as `blocks_to_chunks` does today.

## 2.3 The fidelity ledger

**The atom.** The smallest piece of source text each reader can count without interpreting it:

| Format | Atom |
|---|---|
| `.docx` | every `w:t` run, in the body **and** in text boxes, footnotes, endnotes, comments, headers, footers, tracked insertions and deletions |
| XML, HTML | every text node and tail, under every element |
| MHTML | the same, over every decoded part; undecodable parts counted by bytes |
| PDF | every word the text layer yields, per page; pages with no text layer counted as pages |
| Plain text | every non-blank line |
| Package | every member of the tarball (by path and bytes); inside parsed R files, every non-blank line (F5) |

Atoms are compared after `normalise_text` and with white space removed, since white-space normalisation is a declared transform and `fold_lists` joins with a space.

**The classes.** Every atom ends in exactly one:

| Class | Meaning | Examples today |
|---|---|---|
| `in unit text` | appears in the `text` of a unit | paragraphs, list items folded into their paragraph |
| `relocated` | kept, in a field other than `text` | heading → `heading_chain`; caption → `caption`; cells → `table`; equation markup → `equation.source_form` |
| `declared drop` | left out under a named rule | family `ignore` from shipped or analyst rules; `script` and `style` in HTML; page furniture verified to repeat; refused tarball members |
| `not read` | could not be read; a unit says so | `not_read_block`, `read_problem` |
| `unaccounted` | none of the above | **must be zero** |

**Declared synthesised marks.** The other direction. Characters in unit text that come from no atom, each under a named rule: the list marker; reconstructed numbering; the linear form of an equation; words read from a picture; the display form of a table. Anything else is `injected` and **must be zero**.

**The identity, per file, checked on every run (new part 4 of the coverage identity):**

```
in unit text + relocated + declared drop + not read  =  atoms
unaccounted = 0            injected = 0
every block reference appears in exactly one unit, one heading chain, or one declared drop
```

Following R2 and R3, a failing identity never stops a run. It writes a reading note on the affected units, a row on `Model_Package_Info`, and the file is listed in the run summary. In the offline tests it is a hard failure.

**This is built first and on today's reader, with no model involved (Phase R1).** It will report what the present reader already loses. Those findings say where guidance is actually needed, and they are worth having even if no later phase is ever built.

## 2.4 The shape digest

What the model sees at rung 1: structure and a few short samples, never the document. Built by code from plain facts that `aiva1` and `aiva2` hand over, bounded to about 3,000 estimated tokens, recorded in the store as `shape_digests` so a reviewer can see exactly what was shown.

| Format | One digest row per | Facts in the row |
|---|---|---|
| XML, HTML, MHTML | tag name | count; depth range; parent tags; child tags; share with direct text; mean text length; attribute names; how often first child; three samples cut to 120 characters |
| `.docx` | paragraph style × outline level × numbering format × bold | count; mean length; three samples. Plus counts of text boxes, footnotes, comments, tracked changes, header and footer text |
| PDF | font-size band × bold × indent band | count; mean length; three samples. Plus lines repeating at the same position on several pages (furniture candidates, already verified by code); a column-layout hint per page |
| Plain text | line pattern (numbered, all capitals, short-then-blank, other) | count; three samples |
| Package | tarball member | path; bytes; extension; top folder; for members of unknown kind, the first five lines |

Samples are passed through the same planted-passage defence the mapping prompts use.

## 2.5 Two rungs, three question types

**Rung 1 — propose the rules.** One or two calls per file. Code applies the answer to every block deterministically.

**Rung 2 — decide the contested stretches.** Only where rung 1 leaves doubt. Windows of at most 60 blocks with 5 blocks of overlap; where two windows disagree on an overlap block, the deterministic baseline wins and a reading note says so.

| Type | Rung | Step | Answer (closed vocabularies only) | Validator rejects when |
|---|---|---|---|---|
| `slice-rules` | 1 | 02, 03 | `families`: digest key → family from the fixed list **without `ignore`**; `levels`: digest key → 1…9; `furniture`: keys from the verified candidate list | a key not in the digest; a family not in the list; `ignore`; a level out of range; a furniture key code did not verify |
| `slice-spans` | 2 | 02, 03 | one entry per block in the window: block type from the fixed list; level or none; `joins_previous` true or false | a reference outside the window; a reference missing; a reference twice; an unknown type |
| `package-plan` | 1 | 04 | member path → reader from the fixed list: `r-source`, `r-data`, `help-page`, `vignette`, `table-file`, `prose` | a path not in the manifest; a path missing; an unknown reader. There is no reader that means "skip" |

`package-plan` chooses **which existing reader** takes a file. It never touches `tokenize_r`, `parse_r_source`, `to_expr`, `compose_function` or `decode_data_file`. A file sent to `r-source` that does not parse becomes a unit with a `read_problem`, as today.

All three reuse the existing wrapper unchanged: recorded calls, replay, token refresh, circuit breaker, bad-answer handling.

## 2.6 When the model is asked

Only where the deterministic reader itself admits doubt. Otherwise zero calls, and the units are identical to today's.

| Signal (computed by code) | Asks |
|---|---|
| `state.unknown_tags` is not empty after a first dry walk | `slice-rules` |
| Ledger checkpoint 1 or 2 leaves `unaccounted` above zero | `slice-rules` |
| A heading took the fall-through branch of `infer_levels` (F8), or sibling headings carry contradictory numbering schemes | `slice-rules`, then `slice-spans` on the stretch |
| `discover_table_shape` met ragged rows or no detectable header | `slice-spans` on the table's rows |
| PDF column hint says more than one column, or furniture candidates exist | `slice-rules` |
| A tarball member matches neither `is_parsed_r_file`, `is_data_file` nor a known top folder; or R code sits outside `R/` | `package-plan` |

Setting `agentic_reading`: `off` (today's behaviour, the default until Phase R6 is signed off), `rules`, `rules_and_spans`. One entry on the existing allow-list line.

## 2.7 When the model fails, or is not there

A rejected, failed or absent answer falls back to the deterministic baseline, which is today's reader. The affected units get the reading note "Read by the built-in rules; a guided reading was not available." Worst case equals today. Enforces: R3.

## 2.8 What the analyst sees

No new sheet and no new column.

- **`Reading note`** (already on all three sheets) says how a unit was sliced when it was not by the built-in rules: "Heading level proposed by the model and confirmed at step 07", "Tag 'clause' read as a paragraph on the model's proposal". To carry this, `Chunk` gains one defaulted field, `reading_how: str = ""`, appended to an existing line of the dataclass (zero net lines in `aiva0`); it is not part of `content_hash`. `chunk_note` reads it.
- **`Model_Package_Info`** (through the existing `info_rows`) gains, per file: atoms counted, the five class totals, and "Content account closed" or what is open.
- **Step 07, `confirm-outline`.** The outline record gains difference lines, built in `read_corner`: *what the model's proposal changed against the built-in reading* — headings that moved level, tags that changed family, lines dropped as furniture with their count. The analyst confirms a difference, not a result. The proposal they accept is recorded with their determination.

## 2.9 Where the code lives

A sixth bundle, **`engine/aiva0r_reading.py`** (the name is the owner's to change; the position is not). It imports only `aiva0_shared`. It is imported by `aiva1`, `aiva2`, `aiva3` and `aiva5`. Budget 1,100 lines.

| Contents | From |
|---|---|
| `load_prompt`, `estimate_tokens`, `prompt_budget`, `cut_text`, `last_json_object`, `strict_json`, the generic front half of `validate_answer` | **moved** out of `aiva3_mapping.py` (F2); `aiva3` calls them from here |
| `discover_families`, `discover_table_shape`, `infer_levels`, `without_page_furniture` — now named the **baseline** | **moved** out of `aiva1_documents.py`, freeing about 150 lines there |
| The ledger; block addressing; digest builders; the three question builders and validators; overlay merge; window reconciliation; difference lines | new |

Allowances in the full files: `aiva0_shared.py` 0 net lines; `aiva5_run_report.py` at most 5 net lines (the `CHAT_STEPS` tuple and the settings line are edits, not additions; validator routing sits in `aiva3`, which has room). If a phase needs more in either file, it moves code out first. Raising a budget is not an available answer.

Prompts: `slice-rules.txt`, `slice-spans.txt`, `package-plan.txt` in `engine/references/prompts/`, in the existing `=== SYSTEM === / === MAIN ===` form. The `Procedure`, `Quality rules` and `Never` sections of the three reading skills are prepended to the system half **of these three prompts only**. No existing prompt changes, so no recorded mapping answer is invalidated.

## 2.10 Design rules: what changes

| Rule | Change |
|---|---|
| R5 | Unchanged in wording. The manual adds: "From 0.0.2 a recorded answer can shape how a file is sliced. A replay reproduces the same units. A fresh run on the same inputs may not, and says so in the reading notes." |
| R11 | "Five flat bundles" becomes "Six". `count_lines.py` and the import test gain the new file. |
| **R13 (new)** | **Reading conserves content.** Every atom of every input is accounted for in one of four named classes; every character of every unit traces to an atom or to a named mark; the model chooses among options code has verified and never supplies text; it can neither drop content nor leave a file unread. Enforced where: `aiva0r` ledger and validators; coverage identity part 4. |

---

# 3. The phases

Section 3.2 of the 0.0.1 plan applies to each. One addition for every phase here: **the frozen-interface test passes** (R0 builds it).

## 3.1 Summary

| Phase | Delivers | Model involved | Sessions |
|---|---|---|---|
| R0 | Room to build; the interface frozen by a test | no | 2 |
| R1 | The fidelity ledger on today's reader; a findings report | no | 4 |
| R2 | Addressed blocks and the shape digest | no | 3 |
| R3 | Rung 1 for `Chunks_Canon` and `Chunks_Doc` | yes | 4 |
| R4 | Rung 2 for contested stretches | yes | 3 |
| R5 | The reading plan for `Chunks_Model` | yes | 2 |
| R6 | Hard sample projects, measurement, manual, sign-off | yes | 4 |
| | | **Total** | **22** |

**R0 to R2 (9 sessions) stand alone.** They ship a reader that can prove it lost nothing, with no model call and nothing new to explain to a validation committee.

## Phase R0. Make room and freeze the interface

**Goal.** Create the sixth bundle by relocation only, and pin down "downstream is untouched" as a test before anything is allowed to change.

**What gets built.**
- `engine/aiva0r_reading.py` with the moved functions of 2.9, bodies unchanged. `aiva1` and `aiva3` call them from there.
- `tools/count_lines.py`, `test_layout_rules.py`: six files, new budget, import direction (`aiva0r` imports `aiva0` only).
- `engine/tests/test_frozen_interface.py`: for each of the four sample projects, runs steps 01 to 04 with the stand-in and compares every existing field of every `chunks_canon`, `chunks_doc`, `model_units` and `parameter_tables` record against a stored snapshot under `engine/tests/frozen/`.
- R11 reworded; R13 added to the plan and the manual.

**Offline tests.** Every existing test passes **with no edit to any test of `aiva3` or `aiva4`**. That is the proof the relocation changed nothing. Frozen-interface test green.

**Databricks check.** Run `F_capital` end to end. **Seen in Output.xlsx:** the three unit sheets identical to the last 0.0.1 run (same SHA-256 of each sheet's cell values; a helper prints them).

**Dependencies.** None. **Risks.** A moved function reaches for a module-level name left behind; the unchanged tests catch it. **Rough size.** 2 sessions; about 0 net engine lines, 200 test lines.

## Phase R1. The fidelity ledger on today's reader

**Goal.** Know, per file, exactly what the present reader keeps, relocates, drops and misses. No model.

**What gets built.**
- Atom counters per format (2.3), each fed by facts `aiva1` and `aiva2` hand over.
- The five classes; the named marks; both checkpoints; coverage identity part 4.
- Each of the transforms in F6 registered by name, with a test that shows the ledger closes because of the registration and opens without it.
- `.docx`: atoms from text boxes, footnotes, endnotes, comments, headers, footers and tracked changes are **counted** even where they are not yet read, so that they surface as `unaccounted` instead of vanishing.
- Rows on `Model_Package_Info`; reading notes; run-summary line.
- `evaluation/reading_fidelity_<date>.md`: the ledger over all four samples, plus any real files the owner cares to run.

**Offline tests.** A fixture per format with a planted sentence in each hard place (a text box, a footnote, a second PDF column, an unknown XML tag, a tail after an inline element, an MHTML part in an odd encoding): the ledger reports each as `unaccounted` with its locator. A fixture with a synthetic character forced into a unit: reported as `injected`. Identity holds on all four samples **or the finding is written down and the owner decides** whether it is a reader fault to fix now or a named drop.

**Databricks check.** Run one real methodology file and one real documentation file. **Seen in Output.xlsx:** the content-account rows on `Model_Package_Info`.

**Dependencies.** R0. **Risks.** PDF atoms are only as good as the text layer; scanned pages are counted as pages and said so. The findings may be uncomfortable; that is the point. **Rough size.** 4 sessions; about 380 engine lines, 450 test lines.

## Phase R2. Addressed blocks and the shape digest

**Goal.** Everything the model will later be shown, built and recorded, with still no model.

**What gets built.** Block references per file, recorded as `blocks` in the store (additive record kind). Digest builders per format (2.4) with the token bound. The doubt signals of 2.6 computed and recorded per file as `reading_doubts`. Furniture candidates verified by repetition. A notebook appendix cell that prints a file's digest and its doubts.

**Offline tests.** Digest is stable under re-run; stays under the bound on the largest sample; contains no text beyond the sample cut; every key in it occurs in the file. On the four samples the doubt list is **empty** — which is what guarantees zero calls and identical units later.

**Databricks check.** Print the digest of a real file; the owner judges whether a person could decide the slicing from it. If a person cannot, the model cannot either, and the digest is revised before R3.

**Dependencies.** R1. **Risks.** A digest that is too thin to decide from; caught by the check above. **Rough size.** 3 sessions; about 300 engine lines, 300 test lines.

## Phase R3. Rung 1 for `Chunks_Canon` and `Chunks_Doc`

**Goal.** An unfamiliar schema or layout is read well on the first run, with no release.

**What gets built.**
- `slice-rules.txt`; its question builder and validator (2.5); the overlay merged into `WalkState.rules` per file, never across files (the existing `__post_init__` copy already guarantees this).
- `read-methodology`, `read-documentation` added to `CHAT_STEPS`; their `SKILL.md` bodies rewritten as instructions to a model and prepended to this prompt's system half; versions raised. `confirm-outline` description corrected (F3).
- Precedence, fixed: analyst's `Inputs/tag_rules.yaml` > shipped `tag_rules.yaml` > model overlay > baseline discovery. The model never overrides a person.
- `reading_how` on `Chunk`; difference lines in the outline record; fallback of 2.7.
- `standin_chat.py` answers `slice-rules`; `tests/bad_answers/slice_answers.yaml` covers every rejection reason, including an answer that asks for `ignore`.
- The call-plan cell counts reading calls (at most two per file with a doubt).

**Offline tests.** Every bad answer is rejected for the right reason and the run falls back. With a good answer on a fixture with an unknown schema: `unaccounted` falls to zero and the ledger closes. With **any** answer at all, property-tested over random valid overlays: `injected` stays zero and the partition holds. Frozen-interface test green, because the four samples raise no doubt. Replay reproduces identical units.

**Databricks check.** One real file that the 0.0.1 reader handled badly, `agentic_reading: rules`. **Seen in Output.xlsx:** reading notes naming the model's proposals; at step 07, the difference lines.

**Dependencies.** R2. **Risks.** A small model mislabels a family; the ledger cannot see a *wrong* label, only a *lossy* one, so step 07 carries that weight and must be read, not clicked through. **Rough size.** 4 sessions; about 300 engine lines, 450 test lines, three skill bodies.

## Phase R4. Rung 2 for contested stretches

**Goal.** Where rules cannot settle it, decide block by block, and only there.

**What gets built.** `slice-spans.txt`; windows and overlap; the validator's exactly-once rule; reconciliation (baseline wins a disagreement, with a note); `joins_previous` applied by the same code path `fold_lists` uses, so the join is a declared transform and not a new one.

**Offline tests.** A window answer that omits, repeats or invents a reference is rejected. Property test: for any valid answer, the partition holds and `injected` is zero. A long unnumbered stretch and a ragged table fixture each come out better than baseline against a small gold file. Cost test: calls scale with the number of doubts, not with file length.

**Databricks check.** A real file with an unnumbered stretch, `rules_and_spans`.

**Dependencies.** R3. **Risks.** Windows cut a thought in two; the overlap and the baseline-wins rule bound the damage. **Rough size.** 3 sessions; about 220 engine lines, 350 test lines.

## Phase R5. The reading plan for `Chunks_Model`

**Goal.** A package laid out in an unusual way is read completely. The R parser is not touched.

**What gets built.** The manifest digest; `package-plan.txt`, builder and validator; `read-package` added to `CHAT_STEPS`, body rewritten, version raised. `file_units` takes the chosen reader where the built-in tests (`is_parsed_r_file`, `is_data_file`, top folder) give none. The line-coverage identity (F5) extended from parsed R files to **every** member: each is in a unit, refused with a reason, or carries a `read_problem`.

**Offline tests.** A fixture tarball with R code under `inst/`, a parameter table as `.csv` under `inst/extdata`, and a member of no known kind. Without the model: the ledger reports them. With it: each reaches the right existing reader; the odd member becomes a unit with a `read_problem`; nothing is skipped. `test_aiva2_package.py` passes with no edit to any parser test.

**Databricks check.** One real tarball. **Seen in Output.xlsx:** `Chunks_Model` rows for the files that were previously missed, each with a reading note.

**Dependencies.** R2. Independent of R3 and R4; may run in parallel. **Rough size.** 2 sessions; about 160 engine lines, 250 test lines.

## Phase R6. Hard samples, measurement, manual, sign-off

**Goal.** Show the benefit with numbers, and write down the limits.

**What gets built.**
- Three new sample projects with gold unit files: **G** — an XML schema unlike any of the three known ones, with lists inside table cells; **H** — a two-column PDF with running headers, footnotes and an unnumbered annex; **I** — a `.docx` with text boxes, tracked changes and headings made by bold alone. R9 holds: no domain concept in any of them beyond sample flavour.
- `evaluation/reading_report.md`: for `off`, `rules`, `rules_and_spans` on G, H, I — atoms unaccounted; heading levels right against gold; unit boundaries right against gold; calls spent; tokens spent. Appended to `history.csv`.
- Manual: a new chapter "How AIVA reads a file it has not seen before"; known limitations; the R5 sentence of 2.10; the reviewer's checklist for step 07.

**Sign-off bar for changing the default from `off` to `rules`.** On G, H and I: `unaccounted` and `injected` are zero in every mode; heading levels and unit boundaries are better than `off` on each; on the four old samples nothing moved. If the bar is not met, the default stays `off`, R0 to R2 still ship, and the report says why.

**Dependencies.** R3, R4, R5. **Rough size.** 4 sessions.

---

# 4. What this costs per run

On a familiar input: **zero calls**, identical units. On an unfamiliar one: one or two `slice-rules` calls per file, a handful of `slice-spans` calls per contested stretch, one `package-plan` call per unusual tarball. Typically 5 to 15 calls, against the hundreds `judge-links` spends. All at the front of the run, so a stale token shows itself in the first minute rather than the fortieth.

---

# 5. Out of scope, on purpose

| Not in this plan | Why |
|---|---|
| Steps 05 to 18: graph, search, judging, checks, coverage, report | The frozen interface exists so that these need no change and no re-measurement |
| Headings as units of their own | A real question (a rule stated only in a heading can never be linked), but it moves every reference and every gold file. The ledger classes headings as `relocated`, which is honest. Decide separately. |
| Changing `fold_lists`, `normalise_text`, the list marker, or `content_hash` | Each would move hashes and gold. They are declared, not changed. |
| The R tokenizer and parser, `to_expr`, `compose_function`, `decode_data_file`, the formula parser | Exact by construction. A model's reading of code is an assertion about it, not a parse of it. |
| Reading scanned pages by the model | Different risk, different argument. Pages without a text layer are counted and said to be unread. |
| Moving step functions into skill folders; `contract.yaml`; the registry | The wider skills rebuild. Nothing here blocks it, and R0's bundle is where its shared machinery would live. |

---

# 6. Decisions for the owner before R0

1. **The sixth bundle and the reworded R11.** Without it nothing here fits (F1).
2. **The relocation out of `aiva3`.** It is the one touch outside the reading code. The guarantee offered is that no `aiva3` or `aiva4` test is edited.
3. **Calls before step 07.** Accept that the first calls of a run are now at step 02, and that `confirm-outline` becomes a control the reviewer must actually read.
4. **What to do with R1's findings.** If the ledger shows the present reader loses real content in a common case, is that fixed in the deterministic reader first (recommended: a fault is a fault), or left for the guided reading to cover?
5. **Default setting after R6.** `off` until the sign-off bar is met; then `rules`. `rules_and_spans` stays opt-in for a release.
