# Part III. For the five code reviewers

## 13. How to review a bundle

The engine is five flat files, `aiva1_documents.py` to `aiva5_run_report.py`, plus the small shared file `aiva0_shared.py`. A file imports only the shared file and lower-numbered files, which `test_layout_rules.ImportDirection.test_a_file_imports_only_the_shared_file_and_lower_numbered_files` proves. Each reviewer owns one bundle.

1. **Read `aiva0_shared.py` first** (chapter 14). It holds the vocabulary and every data contract.
2. Read the opening overview of your bundle: what it does, what it takes in and produces, which sheets show its results, which design rules it enforces and in which functions, and how to sanity-check it.
3. Read the file top to bottom; it is written in reading order. Appendix C lists every function with its line number.
4. Run your test file: `python -m unittest discover -s engine/tests -p "test_aiva3_mapping.py"` (with your file's name).
5. Run your sanity check: `cell 17` of the notebook, with `REVIEWER` set to your number. It runs the steps of your bundle on a sample project with the stand-in `chat()` and tells you where the workbook is.
6. Work through the checklist at the end of your chapter. Every line names a test, a function or a place in the workbook that exists; `tools/check_docs.py` fails when one does not.
7. Record your review under `docs/review_records/`: your name, the date, the commit you read, each checklist line with what you saw, your questions and how each was resolved.

Two things hold for every bundle. Nothing taken from an input or from the model is executed (`test_layout_rules.LineBudgetsAndStyle.test_only_the_dataclass_decorator_and_no_execution_of_text`). And no sentence the engine can write uses a rating word (`test_layout_rules.StaticWordingLint.test_no_banned_wording`).

## 14. aiva0_shared.py, for everyone

**Purpose.** One vocabulary and one set of data contracts for all bundles, so that no bundle invents its own words or record shapes.

**Walk through.** Vocabulary of Appendix A as constants (relations, the phrases of "how established", statuses, categories, decision words, unit kinds, the fixed reasons for an undecided check and for a rejected answer); the wording rule as a function, `aiva0_shared.has_banned_wording`; the dataclasses (chunks, model units, edges, candidates, flagged items, determinations, step context and result); canonical JSON and hashes (`aiva0_shared.canonical_json`, `aiva0_shared.content_hash`, `aiva0_shared.swhid_content`); hash chains (`aiva0_shared.chain_records`, `aiva0_shared.verify_chain`); numbers as written (`aiva0_shared.parse_number`, `aiva0_shared.find_numbers`, `aiva0_shared.plain_number`); symbols (`aiva0_shared.normalise_symbol`); and the neutral expression tree with its linear notation (`aiva0_shared.expr_to_text`).

**Checklist for everyone.**

- The content hash ignores white space and line endings and nothing else: `test_aiva0_shared.CanonicalJsonAndHashes.test_content_hash_ignores_white_space_and_line_endings_and_nothing_else`.
- A chain detects an edited, a removed and a re-ordered record: `test_aiva0_shared.CanonicalJsonAndHashes.test_chain_detects_edited_removed_and_reordered_records`.
- Percent, basis points and scientific notation give the same value, and the form as written is kept: `test_aiva0_shared.Numbers.test_percent_basis_points_and_scientific_notation_become_the_same_value`, `test_aiva0_shared.Numbers.test_form_as_written_and_decimals_are_kept`.
- No category and no status rates seriousness: `test_aiva0_shared.Wording.test_no_category_or_status_rates_seriousness`.

## 14a. The reading floor: aiva0r_reading.py

**Purpose.** Hold what the reading steps and the mapping steps both need, below either of them. Two things live here. The asking machinery: a prompt template in its three parts (`aiva0r_reading.load_prompt`), a token estimate made from characters because no tokenizer can be installed (`aiva0r_reading.estimate_tokens`), what the cap leaves for the main prompt (`aiva0r_reading.prompt_budget`), a cut that keeps the words that matter (`aiva0r_reading.cut_text`), the last balanced object in a reply (`aiva0r_reading.last_json_object`) and strict parsing that repairs nothing (`aiva0r_reading.strict_json`). And the baseline slicing decisions: a family for every tag a document uses (`aiva0r_reading.discover_families`), whether a shape is really a table (`aiva0r_reading.discover_table_shape`), the level of every heading (`aiva0r_reading.infer_levels`) and the lines a page carries only because it is a page (`aiva0r_reading.without_page_furniture`).

**Why it exists.** The asking machinery used to sit in `aiva3_mapping.py`, which reads the documents' output and therefore sits above the reading steps. Steps 02 to 04 could not reach it, so they could not ask anything. Moving it down is what lets a reading step ask a question at all. The baseline decisions moved with it because they are what a guided reading is compared against: they are what AIVA does with no model, and what it falls back to when an answer is refused or the model is not there.

**Contracts.** In: a prompt template, the tag rules, a parsed element or a list of page lines, a reply as text. Out: prompts, budgets, parsed answers or refusals, a family for each tag with its reason, a level on each heading, page lines without their furniture and a note naming what was left out. Nothing here writes a record; what it decides reaches `Chunks_Canon`, `Chunks_Doc` and `Chunks_Model` through Reviewer 1 and Reviewer 2, and `Model_Package_Info` through their reading notes.

**Known limitations.** The token estimate is made from characters and is deliberately on the safe side, so a prompt is sometimes called too large when it would have fit. Discovery only speaks where the tag rules are silent: a schema the rules already name is read exactly as the rules say, and an analyst's `Inputs/tag_rules.yaml` always wins.

## 15. Reviewer 1: aiva1_documents.py

**Purpose.** Turn methodology and documentation files of any supported form into chunks in reading order: paragraphs, tables, figures and equations, each with its level, heading chain, numbering as written, locator and content hash.

**Walk through.** The formula reader (`aiva1_documents.parse_formula`) and the converters from Office Math, MathML and LaTeX to AIVA's linear notation (`aiva1_documents.math_to_linear`, `aiva1_documents.latex_to_linear`); format detection from content (`aiva1_documents.detect_format`); recorded repairs of malformed markup (`aiva1_documents.repair_markup`) and the tolerant reader; the walker driven by `engine/references/tag_rules.yaml` (`aiva1_documents.walk_element`); Word's web export (`aiva1_documents.blocks_from_mhtml`), Word files (`aiva1_documents.blocks_from_docx`) and PDF (`aiva1_documents.blocks_from_pdf`); level inference (`aiva0r_reading.infer_levels`, the baseline); chunks (`aiva1_documents.blocks_to_chunks`); the two steps (`aiva1_documents.read_methodology`, `aiva1_documents.read_documentation`).

**Contracts.** In: the input files. Out: chunks_canon, chunks_doc, read_repairs, info_rows, outline. Shown on `Chunks_Canon`, `Chunks_Doc` and `Model_Package_Info`.

**Known limitations.** PDF layout is guessed from positions: a heading is a short line set larger or bolder than the body, and a header or footer is a line that repeats in a page margin, so an unusual layout can be misread and `Model_Package_Info` says what was left out. Juxtaposition is read as a product only inside structured markup, never in running text. The words OCR reads from a picture are shown to help a person and are never evidence; the bundled OCR model can drop the spaces between words.

**Checklist.**

- Every table of a sample methodology is exactly one row on `Chunks_Canon`: `test_aiva1_documents.ReadingFiles.test_one_table_is_one_chunk_and_inline_formulas_are_found`.
- Levels and heading chains match the document's own outline, also for a flat-numbered annex: `test_aiva1_documents.ReadingFiles.test_xml_in_a_txt_file_nested_levels_tables_equations`; compare with the outline printed by `cell 9`.
- Repairs are recorded: `test_aiva1_documents.ReadingFiles.test_malformed_markup_is_repaired_and_the_repairs_are_recorded`.
- An equation or figure that cannot be read is still a chunk and ends with a flagged item: `test_aiva4_checks.SeededSample.test_an_equation_given_as_an_image_is_never_skipped`.
- The format is detected from the content: `test_aiva1_documents.ReadingFiles.test_format_is_found_from_content_not_from_the_extension`.
- Nothing from an input is executed, ambiguous notation is not guessed, and document-type declarations are removed before parsing: `aiva1_documents.parse_formula`, `aiva1_documents.safe_xml`, `aiva1_documents.repair_markup`; `test_aiva1_documents.FormulaNotation.test_ambiguous_notation_is_not_guessed`, `test_aiva1_documents.ReadingFiles.test_entities_defined_inside_an_office_file_are_never_expanded`.
- The same bytes give the same chunks: `test_aiva1_documents.ReadingFiles.test_same_bytes_give_the_same_chunks`.
- A file that cannot be read never stops the run: `test_aiva1_documents.ReadingFiles.test_a_file_that_cannot_be_read_gives_a_not_read_unit_and_never_stops_the_run`.

## 16. Reviewer 2: aiva2_package.py

**Purpose.** Read an R source tarball without R: unpack it safely in memory, parse the code with AIVA's own reader, turn functions and formula statements into neutral expression trees, read roxygen blocks, help pages, tests and vignettes as units, and decode stored data into parameter tables.

**Walk through.** Safe unpacking (`aiva2_package.unpack_package`); DESCRIPTION and NAMESPACE; the tokenizer and the operator-precedence parser (`aiva2_package.tokenize_r`, `aiva2_package.parse_r_source`), which recovers expression by expression; facts about code (`aiva2_package.code_facts`, `aiva2_package.has_arithmetic`); conversion to the neutral tree through `engine/references/r_function_map.yaml` (`aiva2_package.to_expr`) and composition of straight-line functions (`aiva2_package.compose_function`); units from R files, roxygen, help pages and vignettes; stored data (`aiva2_package.decode_data_file`, `aiva2_package.table_of`); reads of stored data (`aiva2_package.data_reads`); the step (`aiva2_package.read_package`).

**Contracts.** In: the tarball. Out: model_units, parameter_tables, package_info. Shown on `Chunks_Model` and `Model_Package_Info`. The column *LLM Interpretation* of `Chunks_Model` is filled later, by step `07a` in `aiva3_mapping.interpret_code` (Reviewer 3), from the record kind `interpretations`.

**Known limitations.** No second, independent reader of stored data and no extraction of R classes and attributes beyond what the decoder gives. S4 and R5 classes are read as code, not as structures. Missing values of different kinds are not told apart.

**Checklist.**

- Every non-blank line of every parsed R file lies inside a unit: `test_aiva2_package.ReadingR.test_every_non_blank_line_lies_inside_a_unit`.
- A broken expression gives a *File not read* unit and the rest is still read: `test_aiva2_package.ReadingR.test_a_broken_expression_is_kept_as_not_read_and_the_rest_is_still_parsed`.
- Roxygen blocks attach to the object that follows them; help pages out of step are seen: `test_aiva2_package.ReadingR.test_roxygen_blocks_help_pages_tests_and_vignettes_become_units`.
- Unsafe archive members are refused one by one: `test_aiva2_package.UnpackingSafely.test_paths_that_leave_the_package_links_and_devices_are_refused_and_nothing_touches_disk`.
- Stored data decodes without R and nothing in it is evaluated: `test_aiva2_package.StoredData.test_rda_and_rds_are_decoded_without_r_and_profiled`, `test_aiva2_package.StoredData.test_a_data_file_that_is_not_r_data_is_recorded_as_not_assessed`.
- Reads of stored data are recognised: `test_aiva2_package.StoredData.test_reads_of_stored_data_are_recognised`.
- Every entry of `engine/references/r_function_map.yaml` has been read and agreed: the function, its arguments, its valid domain.
- A sign changed above the return reaches the comparison: `test_aiva2_package.ReadingR.test_straight_line_functions_are_composed_so_that_a_sign_above_the_return_is_seen`.
- Supporting code by syntax never holds arithmetic or a non-trivial number, also not as a default: `test_aiva2_package.ReadingR.test_supporting_code_by_syntax_never_holds_arithmetic_or_a_non_trivial_number`.

## 17. Reviewer 3: aiva3_mapping.py

**Purpose.** Record what the readers found as a graph; propose, deterministically and with plain reasons, which passages a unit may correspond to; ask the judge; validate every answer; write accepted links.

**Walk through.** The ledger (`aiva3_mapping.ledger_records`, `aiva3_mapping.verify_ledger`, `aiva3_mapping.find_path`); words (`aiva3_mapping.split_words`); what is indexed for a unit (`aiva3_mapping.unit_fields`, `aiva3_mapping.chunk_fields`); the signals: field-aware text ranking (`aiva3_mapping.bm25_scores`), the bridge vocabulary (`aiva3_mapping.harvest_bridge`), explicit references (`aiva3_mapping.resolve_reference`), rare shared anchors and the restart walk (`aiva3_mapping.anchor_weights`, `aiva3_mapping.restart_walk`), formula signatures and table shape; fusion by rank (`aiva3_mapping.fuse`) and reasons; the steps `aiva3_mapping.build_graph` and `aiva3_mapping.find_candidates`; questions (`aiva3_mapping.assemble_question`, `aiva3_mapping.choose_decoys`); validators (`aiva3_mapping.validate_answer`); `aiva3_mapping.judge_links` and the second, oppositely framed question.

**Contracts.** In: chunks, units, tables, word lists and prompts under `engine/references/`. Out: graph_ledger, bridge_vocabulary, candidates, search_records, judgement_problems, second_opinions. Shown in the reference, relation, "How established", "What was searched" and "Why not mapped" columns of both mapping sheets.

**Known limitations.** Recall is complete on the small samples, so they cannot show which signal earns its place on a large methodology; that is measured in Phase 12 with `tools/recall_at_k.py`. The stemmer is deliberately weak.

**Checklist.**

- The ledger offers no way to change or remove a record, and verification detects tampering: `test_aiva3_mapping.Ledger.test_a_later_record_is_appended_and_never_replaces_an_earlier_one`, `test_aiva3_mapping.Ledger.test_an_edited_a_removed_and_a_reordered_record_are_each_detected`.
- The search is deterministic: `test_end_to_end.TwoRunsAreTheSame.test_same_inputs_give_the_same_audit_records_and_the_same_graph_version`.
- A reason shown in the workbook can be reproduced by hand: `test_aiva3_mapping.Words.test_bm25_by_hand`, `test_aiva3_mapping.Search.test_the_gold_passage_is_proposed_and_every_proposal_gives_its_reason`.
- Common anchors count for nothing: `test_aiva3_mapping.Search.test_an_anchor_that_too_many_units_mention_is_dropped`.
- Signatures re-order and never propose alone; propagated candidates never become links without the judge: `test_aiva3_mapping.Search.test_signatures_reorder_and_never_propose_alone`, `aiva3_mapping.propagated_candidates`.
- The bad-answers corpus passes: `test_aiva3_mapping.QuestionsAndValidators.test_the_bad_answer_corpus`, `test_aiva3_mapping.QuestionsAndValidators.test_letters_come_from_a_hash_not_from_the_score_and_the_question_id_is_the_prompt_hash`.
- A rejected answer never becomes a link: `test_aiva3_mapping.QuestionsAndValidators.test_a_rejected_answer_never_becomes_a_link`.
- No prompt contains a domain concept: `test_layout_rules.StaticWordingLint.test_no_domain_concept_in_engine_prompts_or_stop_words`.

## 18. Reviewer 4: aiva4_checks.py

**Purpose.** Confirm or contradict by code every link that involves a formula, a value, a table or a stated rule; check roxygen blocks and help pages against the code; decide the one status of every unit; raise the flagged items; prove the coverage identity.

**Walk through.** The value rule (`aiva4_checks.compare_values`); tree to SymPy, node by node (`aiva4_checks.to_sympy`) and the bounded symbolic step; AIVA's own evaluator and the sample points (`aiva4_checks.evaluate`, `aiva4_checks.sample_points`, `aiva4_checks.numeric_step`); alignment, settled before comparing (`aiva4_checks.align`, `aiva4_checks.prepare_alignment`, `aiva4_checks.compare_formulas`); the step `aiva4_checks.check_mathematics`; tables (`aiva4_checks.reconcile`) and `aiva4_checks.check_values`; rules (`aiva4_checks.stated_rules`, `aiva4_checks.rule_in_trees`, `aiva4_checks.check_rules`); `aiva4_checks.check_package_docs`; the ordered status rules (`aiva4_checks.model_unit_outcome`, `aiva4_checks.doc_unit_outcome`), items (`aiva4_checks.build_items`), the identity (`aiva4_checks.check_identity`) and `aiva4_checks.account_coverage`.

**Contracts.** In: everything before it. Out: math_checks, value_checks, rule_checks, package_doc_checks, new ledger edges, unit_status, flagged_items, coverage. Shown in the assessment columns, *Overall status*, `Mapping_Coverage` and `Flagged_Items`.

**Known limitations.** A statement that does not agree on its own takes the result of the check of its whole function when both are linked to the same passage; a statement without a link counts as traced when the agreeing check of its function ran through it. Both extend the plan's rules and are listed in chapter 27. Prose numbers are compared only when they sit among the same words.

**Checklist.**

- *Differs* only ever comes with a counterexample, and the same seed gives the same one: `test_aiva4_checks.FormulaComparison.test_differs_always_comes_with_a_counterexample_and_the_same_seed_gives_the_same_one`.
- No differing pair of the corpus is ever reported as agreeing: `test_aiva4_checks.FormulaComparison.test_the_corpus_no_differing_pair_ever_agrees`.
- An undecided check is never clean: `test_aiva4_checks.SeededSample.test_the_flipped_sign_in_cond_pd_is_caught_with_a_counterexample`, `test_aiva4_checks.SeededSample.test_an_equation_given_as_an_image_is_never_skipped`.
- No string is ever parsed by SymPy: read `aiva4_checks.to_sympy`.
- One value-comparison function is used everywhere, and its rule text is shown on `Model_Package_Info`: `aiva4_checks.compare_values`, `test_aiva4_checks.ValueRule.test_the_table_of_the_rule`.
- Alignment is fixed before the comparison: `test_aiva4_checks.FormulaComparison.test_alignment_is_fixed_before_comparing_so_swapped_symbols_end_as_differs`.
- The status rules in the code are the rules in chapter 6: `test_aiva4_checks.SeededSample.test_every_status_was_decided_by_a_rule_of_the_ordered_list`.
- Each part of the identity stops the run when it is violated: `test_aiva4_checks.SeededSample.test_a_broken_identity_stops_the_run_and_names_the_part`, `test_aiva4_checks.SeededSample.test_the_identity_not_clean_if_and_only_if_an_item_names_the_unit`.
- All six seeded differences of the known sample are flagged in an expected category: `test_aiva4_checks.SeededSample.test_all_six_seeded_differences_are_flagged_in_an_expected_category`.
- The clean baselines flag none of the units listed as clean: `test_aiva4_checks.CleanSamples.test_the_clean_baseline_flags_none_of_the_units_listed_as_clean`.

## 19. Reviewer 5: aiva5_run_report.py

**Purpose.** Everything around the review itself: settings, paths, the live values with the token, the only place where `chat()` is called, the audit store, the runner, the workbook, the report, determinations and verification.

**Walk through.** Settings as an allow-list (`aiva5_run_report.make_settings`); paths (`aiva5_run_report.setup_project`, `aiva5_run_report.open_run`); live values (`aiva5_run_report.LiveValues`); the store (`aiva5_run_report.AuditStore`); the wrapper (`aiva5_run_report.call_chat`, `aiva5_run_report.ask_one`, `aiva5_run_report.make_asker`) and replay (`aiva5_run_report.replay_chat`); the runner (`aiva5_run_report.load_pipeline`, `aiva5_run_report.run_pipeline`, `aiva5_run_report.run_step`); the plain-language gate for every cell (`aiva5_run_report.plain_cell`); the workbook (`aiva5_run_report.build_workbook`, `aiva5_run_report.check_written_totals`) and the overwrite guard (`aiva5_run_report.rebuild_outputs`); the call plan (`aiva5_run_report.call_plan`); determinations (`aiva5_run_report.find_uploads`, `aiva5_run_report.read_yellow_cells`, `aiva5_run_report.record_determinations`); the report (`aiva5_run_report.build_report_file`); verification (`aiva5_run_report.verify_evidence_pack`).

**Contracts.** In: every audit record. Out: the two output files, `_audit`, determinations. Shown everywhere.

**Known limitations.** Files are synced after every batch of calls and every step, not on a timer. A report with several thousand items is long; its build time has not been measured at that size.

**Checklist.**

- The token never persists, and no question is lost or asked twice: `test_aiva5_run_report.TokenRefresh.test_pause_resume_nothing_lost_nothing_twice_no_token_on_disk`.
- All three failure shapes of `chat()` are handled: `test_aiva5_run_report.TokenRefresh.test_all_three_failure_shapes_are_classified_as_authentication`, `test_aiva5_run_report.ResumeAndBreaker.test_breaker_opens_and_a_second_call_finishes_without_repeating`.
- The runner calls only functions of its explicit dictionary and refuses version drift: `test_aiva5_run_report.RunnerAndWorkbook.test_pipeline_refuses_unknown_functions_and_version_drift`.
- A run writes only inside its run folder: `test_aiva5_run_report.RunnerAndWorkbook.test_a_run_writes_only_inside_its_own_folder`.
- The workbook format is right: `test_aiva5_run_report.RunnerAndWorkbook.test_workbook_format`.
- No cell contains technical text or a rating word, and whole numbers are whole: `test_end_to_end.WhatAnAnalystReads.test_every_cell_of_the_workbook_is_in_plain_words`, `test_end_to_end.WhatAnAnalystReads.test_the_word_files_are_in_plain_words_and_the_report_holds_every_item_once`.
- Coverage on the sheet equals what filtering gives: `test_end_to_end.WhatAnAnalystReads.test_coverage_on_the_sheet_equals_what_filtering_overall_status_gives`.
- Determinations: `test_end_to_end.HumanRoundTrip.test_a_renamed_sorted_workbook_with_an_added_sheet_is_read_by_item_id`, `test_end_to_end.HumanRoundTrip.test_a_changed_decision_appends_and_a_cleared_one_is_recorded_as_withdrawn`, `test_end_to_end.HumanRoundTrip.test_an_edited_workbook_is_never_overwritten_before_it_has_been_read_in`, `test_end_to_end.HumanRoundTrip.test_a_workbook_of_another_run_and_an_xls_file_are_refused_in_plain_words`.
- The verification cell detects tampering: `test_end_to_end.VerifyingARunFolder.test_a_changed_chunk_a_broken_chain_and_a_deleted_status_are_each_detected`, `test_end_to_end.VerifyingARunFolder.test_a_changed_input_byte_is_detected`.
- Replaying the recorded answers reproduces the run: `test_end_to_end.TwoRunsAreTheSame.test_replaying_the_recorded_answers_reproduces_graph_statuses_and_items`.
- The notebook's cells run: `test_notebook.NotebookCells.test_the_cells_run_from_setup_to_verification_with_the_stand_in`.
