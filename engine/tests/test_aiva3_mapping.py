"""Tests of aiva3_mapping: the ledger, the deterministic search signals, questions and validators."""
import math
import unittest

import yaml

import helpers
import aiva0_shared as shared
import aiva3_mapping as mapping
import aiva5_run_report as run

SETTINGS = run.make_settings()
PROVENANCE = shared.Provenance("Run_X", "05", "build-graph", "0.0.1")


def edge(source, target, kind="contains"):
    return shared.Edge(source, target, kind, shared.HOW_PARSED, PROVENANCE)


class Ledger(unittest.TestCase):
    def ledger(self):
        records = [mapping.node_record(ref, "Function", "model") for ref in ("M-0002", "M-0001", "M-0003")]
        return mapping.ledger_records([], records + [edge("M-0001", "M-0002"), edge("M-0001", "M-0003", "calls")])

    def test_the_same_content_gives_the_same_graph_version_whatever_the_order(self):
        first = self.ledger()
        records = [edge("M-0001", "M-0003", "calls"), edge("M-0001", "M-0002")] + [mapping.node_record(ref, "Function", "model") for ref in ("M-0003", "M-0001", "M-0002")]
        self.assertEqual(mapping.graph_version_id(first), mapping.graph_version_id(mapping.ledger_records([], records)))

    def test_an_edited_a_removed_and_a_reordered_record_are_each_detected(self):
        good = self.ledger()
        self.assertTrue(mapping.verify_ledger(good)[0])
        edited = [dict(r) for r in good]
        edited[3]["target"] = "M-0003"
        removed = good[:2] + good[3:]
        reordered = good[:3] + [good[4], good[3]]
        for tampered in (edited, removed, reordered):
            self.assertFalse(mapping.verify_ledger(tampered)[0])

    def test_a_later_record_is_appended_and_never_replaces_an_earlier_one(self):
        first = self.ledger()
        more = mapping.ledger_records(first, [edge("M-0002", "M-0003", "calls")])
        self.assertTrue(mapping.verify_ledger(first + more)[0])
        self.assertEqual(more[0]["prev_hash"], first[-1]["record_hash"])
        self.assertFalse([name for name in dir(mapping) if name.startswith(("delete_", "remove_", "update_edge", "edit_"))])

    def test_paths_are_found_over_typed_edges(self):
        graph = mapping.load_graph(self.ledger())
        path = mapping.find_path(graph, "M-0002", lambda ref: ref == "M-0003")
        self.assertEqual([reached for _, reached in path], ["M-0001", "M-0003"])
        self.assertIsNone(mapping.find_path(graph, "M-0002", lambda ref: ref == "M-0003", allowed_kinds=("contains",)))


class Words(unittest.TestCase):
    def test_identifiers_are_split_and_stemmed(self):
        self.assertEqual(mapping.split_words("computeRiskWeights cond_pd applied.floors", {"of"}), ["comput", "risk", "weight", "cond", "pd", "apply", "floor"])
        self.assertEqual(mapping.stem("applies"), mapping.stem("applied"))

    def test_bm25_by_hand(self):
        index = mapping.build_index({"A": {"fields": {"body": ["floor", "rate"]}}, "B": {"fields": {"body": ["rate", "rate", "cap"]}}})
        scores = mapping.bm25_scores(index, {"floor": 1.0}, 1.2, 0.75)
        idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
        expected = idf * 1 * 2.2 / (1 + 1.2 * (1 - 0.75 + 0.75 * 2 / 2.5))
        self.assertEqual(list(scores), ["A"])
        self.assertAlmostEqual(scores["A"][0], expected, places=12)

    def test_field_weights_count_a_name_more_than_the_body(self):
        index = mapping.build_index({"A": {"fields": {"name": ["floor"], "body": []}}, "B": {"fields": {"name": [], "body": ["floor"]}}})
        scores = mapping.bm25_scores(index, {"floor": 1.0}, 1.2, 0.75)
        self.assertGreater(scores["A"][0], scores["B"][0])

    def test_bridge_entries_are_harvested_from_the_inputs_own_definitions(self):
        patterns = {"definition_verbs": ["denotes", "represents"]}
        text = "The loss given default (LGD) applies, see (see Table 3), where R denotes the asset correlation. Let K be the capital requirement."
        found = {(term, phrase) for term, phrase, _, _ in mapping.harvest_text(text, "C-0001", patterns)}
        self.assertEqual(found, {("LGD", "loss given default"), ("R", "asset correlation"), ("K", "capital requirement")})


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths, cls.settings, _ = helpers.run_sample("F_capital", stop_after="06")
        cls.store = run.open_store(cls.paths, cls.settings)

    def test_every_searched_unit_has_a_search_record_with_words_an_analyst_can_read(self):
        units = [u for u in self.store.read("model_units") if mapping.is_searched(u, self.settings)]
        records = {(r["unit_ref"], r["target_corner"]) for r in self.store.read("search_records")}
        for unit in units:
            self.assertIn((unit["ref"], "canon"), records)
        text = next(r["searched_text"] for r in self.store.read("search_records") if r["unit_ref"] == "M-0024" and r["target_corner"] == "canon")
        self.assertTrue(text.startswith("Searched the methodology for: cond, pd"))

    def test_the_gold_passage_is_proposed_and_every_proposal_gives_its_reason(self):
        candidates = [c for c in self.store.read("candidates") if c["unit_ref"] == "M-0024" and c["target_corner"] == "canon"]
        self.assertIn("C-0012", [c["target_ref"] for c in candidates][:5])
        self.assertTrue(all(c["reason"].startswith("Proposed") for c in candidates))
        self.assertLessEqual(len(candidates), self.settings["k_candidates"])

    def test_an_anchor_that_too_many_units_mention_is_dropped(self):
        mentions = {("symbol", "x"): ["U%d" % n for n in range(40)], ("number", "0.999"): ["U1", "U2"], ("number", "7"): ["U3"]}
        weights = mapping.anchor_weights(mentions, dict(self.settings, anchor_max_share=0.10))
        self.assertEqual(list(weights), [("number", "0.999")])

    def test_the_walk_agrees_with_an_independent_personalised_pagerank(self):
        try:
            import networkx
        except ImportError:
            self.skipTest("networkx is only present in the build environment")
        mentions = {("number", "0.999"): ["M-1", "C-1", "C-4"], ("symbol", "rho"): ["M-1", "C-1", "C-2"], ("term", "floor"): ["M-2", "C-3", "C-2"], ("number", "0.03"): ["M-2", "C-3"]}
        weights = mapping.anchor_weights(mentions, dict(self.settings, anchor_max_share=1.0))
        ours = mapping.restart_walk(mentions, weights, ["M-1"], dict(self.settings, walk_rounds=200))["M-1"]
        graph = networkx.Graph()
        for anchor, refs in mentions.items():
            for ref in refs:
                graph.add_edge(ref, "anchor:%s:%s" % anchor, weight=weights[anchor])
        theirs = networkx.pagerank(graph, alpha=1 - self.settings["walk_restart"], personalization={"M-1": 1.0}, weight="weight", tol=1e-12, max_iter=1000)
        for ref in ("C-1", "C-2", "C-3", "C-4"):
            self.assertAlmostEqual(ours.get(ref, 0.0), theirs[ref], places=6)
        self.assertEqual(sorted(ours, key=lambda ref: -ours[ref])[0], "C-1")

    def test_fusion_is_by_rank_only_and_ties_break_by_reference(self):
        fused = mapping.fuse({"fields": ["C-2", "C-1"], "anchors": ["C-1", "C-2"]}, self.settings)
        self.assertEqual([ref for ref, _, _ in fused], ["C-1", "C-2"])
        self.assertEqual(fused[0][1], fused[1][1])

    def test_signatures_reorder_and_never_propose_alone(self):
        fused = mapping.fuse({"fields": ["C-1"], "signatures": ["C-9", "C-1"]}, self.settings)
        self.assertEqual([ref for ref, _, _ in fused], ["C-1"])


class QuestionsAndValidators(unittest.TestCase):
    def question(self):
        prompt = mapping.load_prompt(run.REFERENCES_DIR, "judge-unit-to-canon")
        passages = [("C-0009", "3.1.1 Floor, paragraph 1", "The probability of default is never taken below 0.03%."),
                    ("C-0008", "3.1, paragraph 1", "The probability of default is estimated from internal ratings and is reviewed every year."),
                    ("C-0099", "9 Other, paragraph 1", "All parcels are weighed at the counter before they are priced.")]
        return mapping.assemble_question("judge-unit-to-canon", "M-0021", [("UNIT (function floor_pd)", "floor_pd <- function(pd, floor = 0.0003) {\n  pmax(pd, floor)\n}")],
                                         passages, prompt, SETTINGS, planted=["C-0099"], more={"target_corner": "canon"})

    def test_letters_come_from_a_hash_not_from_the_score_and_the_question_id_is_the_prompt_hash(self):
        first, second = self.question(), self.question()
        self.assertEqual(first["question_id"], second["question_id"])
        self.assertEqual(first["letters"], second["letters"])
        self.assertEqual(sorted(first["letters"].values()), ["C-0008", "C-0009", "C-0099"])
        self.assertEqual(first["planted"], [letter for letter, ref in first["letters"].items() if ref == "C-0099"])
        self.assertNotIn("C-0009", first["main_prompt"])

    def test_the_bad_answer_corpus(self):
        question = self.question()
        letter = {ref: letter for letter, ref in question["letters"].items()}
        with open(helpers.os.path.join(helpers.TESTS_DIR, "bad_answers", "judge_answers.yaml"), encoding="utf-8") as handle:
            corpus = yaml.safe_load(handle)["answers"]
        self.assertGreaterEqual(len(corpus), 20)
        for case in corpus:
            text = case["text"].replace('"GOOD"', '"%s"' % letter["C-0009"]).replace('"PLANTED"', '"%s"' % letter["C-0099"])
            outcome, answer = mapping.validate_answer(question, text)
            expected = "accepted" if case["expected"] == "accepted" else "rejected: " + shared.REJECTION_REASONS[case["expected"]]
            self.assertEqual(outcome, expected, case["name"])
            self.assertEqual(answer is not None, expected == "accepted", case["name"])

    def test_narrow_answers_are_validated_too(self):
        question = mapping.narrow_question("align-symbols", "M-0001", [("CODE SYMBOLS", "base, rate"), ("EQUATION SYMBOLS", "B, R")], run.REFERENCES_DIR,
                                           SETTINGS, more={"code_symbols": ["base", "rate"], "equation_symbols": ["B", "R"]})
        good = '{"alignment": [{"code": "base", "equation": "B"}, {"code": "rate", "equation": "R"}], "cannot_align": false}'
        twice = '{"alignment": [{"code": "base", "equation": "B"}, {"code": "rate", "equation": "B"}], "cannot_align": false}'
        unseen = '{"alignment": [{"code": "base", "equation": "Z"}], "cannot_align": false}'
        self.assertEqual(mapping.validate_answer(question, good)[0], "accepted")
        self.assertEqual(mapping.validate_answer(question, twice)[0], "rejected: " + shared.REJECTION_REASONS[4])
        self.assertEqual(mapping.validate_answer(question, unseen)[0], "rejected: " + shared.REJECTION_REASONS[1])

    def test_decoys_share_no_anchor_with_the_unit_and_are_chosen_by_hash(self):
        pool = {"C-1": {"text": "x" * 50}, "C-2": {"text": "y" * 50}, "C-3": {"text": "z" * 50}, "C-4": {"text": "short"}}
        anchors = {"M-1": [("number", "0.5")], "C-1": [("number", "0.5")], "C-2": [("number", "9")], "C-3": []}
        first = mapping.choose_decoys("M-1", ["C-9"], set(), pool, anchors, 1)
        self.assertEqual(first, mapping.choose_decoys("M-1", ["C-9"], set(), pool, anchors, 1))
        self.assertIn(first[0], ("C-2", "C-3"))

    def test_text_written_by_the_model_is_filtered_before_it_is_shown(self):
        self.assertEqual(mapping.shown_ai_text("This is a " + "crit" + "ical gap."), shared.AI_WORDING_NOT_SHOWN)
        self.assertEqual(mapping.shown_ai_text("The passage states another rate."), "The passage states another rate.")

    def test_a_rejected_answer_never_becomes_a_link(self):
        paths, settings, _ = helpers.run_sample("A_minimal", chat=lambda SystemPrompt, MainPrompt: {"answer": "I cannot answer in JSON."}, stop_after="08")
        store = run.open_store(paths, settings)
        links = [r for r in store.read("graph_ledger") if r["record_type"] == "edge" and r["kind"] == "corresponds"]
        self.assertEqual(links, [])
        self.assertTrue(store.read("judgement_problems"))


if __name__ == "__main__":
    unittest.main()


class InterpretingTheCode(unittest.TestCase):
    """Step 07a: what each piece of code does, in plain words, for the column LLM Interpretation."""

    @classmethod
    def setUpClass(cls):
        import standin_chat
        cls.paths, cls.settings, cls.outcome = helpers.run_sample("A_minimal", chat=standin_chat.make_chat(misbehave=False), stop_after="07a")
        cls.store = run.open_store(cls.paths, cls.settings)
        cls.units = {u["ref"]: u for u in cls.store.read("model_units")}
        cls.records = cls.store.read("interpretations")
        cls.calls = [c for c in cls.store.read_calls() if c["question_type"] == "interpret-code"]

    def test_every_piece_of_code_is_asked_about_once_and_nothing_else_is(self):
        asked = sorted(r["unit_ref"] for r in self.records)
        code = sorted(ref for ref, u in self.units.items() if u["kind"] in mapping.INTERPRETED_KINDS)
        self.assertEqual(asked, code)
        self.assertEqual(len(asked), len(set(asked)))
        self.assertFalse([r for r in self.records if self.units[r["unit_ref"]]["kind"] in ("Roxygen block", "Help page", "Parameter table")])

    def test_a_statement_is_shown_with_where_it_sits_in_the_whole_package(self):
        statement = next(ref for ref, u in self.units.items() if u["kind"] == "Formula statement" and u["name"] == "price")
        prompt = next(c["main_prompt"] for c in self.calls if c["unit_ref"] == statement)
        piece, about = prompt.split("WHERE IT SITS IN THE PACKAGE")
        self.assertIn("price <- base + rate * cw", piece)
        self.assertIn("one statement inside the function parcel_price", about)
        self.assertIn('base <- zone_rates[zone_rates$zone == zone, "base_rate"]', about, "the whole function it sits in")
        self.assertIn("Base rate plus rate per kilogram times chargeable weight", about, "the package's own documentation")
        self.assertIn("Within this package it calls: volume_discount.", about)
        self.assertIn("It reads the stored data: zone_rates.", about)
        self.assertIn("Package parcelcost 1.2.0: Parcel Pricing", about)
        self.assertIn("R/weights.R: dim_weight(l, w, h, divisor) - Dimensional weight", about, "every file of the package, not only its own")

    def test_a_function_is_told_what_calls_it(self):
        called = next(ref for ref, u in self.units.items() if u["kind"] == "Function" and u["name"] == "volume_discount")
        prompt = next(c["main_prompt"] for c in self.calls if c["unit_ref"] == called)
        self.assertIn("It is called by: parcel_price.", prompt)

    def test_an_answer_that_quotes_code_that_is_not_there_is_refused(self):
        question = {"question_type": "interpret-code", "code_text": "  price <- base + rate * cw", "strip_patterns": []}
        good = '{"interpretation": "It adds the base rate to the rate per kilogram times the weight.", "quote_from_unit": "base + rate * cw"}'
        self.assertEqual(mapping.validate_answer(question, good)[0], "accepted")
        invented = '{"interpretation": "It adds the base rate to the rate per kilogram times the weight.", "quote_from_unit": "price <- base * 2"}'
        self.assertEqual(mapping.validate_answer(question, invented), ("rejected: " + shared.REJECTION_REASONS[2], None))
        empty = '{"interpretation": "", "quote_from_unit": "base + rate * cw"}'
        self.assertEqual(mapping.validate_answer(question, empty)[0], "rejected: " + shared.REJECTION_REASONS[0])
        rambling = '{"interpretation": "%s", "quote_from_unit": "base + rate * cw"}' % ("word " * 200)
        self.assertEqual(mapping.validate_answer(question, rambling)[0], "rejected: " + shared.REJECTION_REASONS[0])

    def test_the_column_shows_the_models_words_as_a_quotation_and_a_refusal_as_a_plain_note(self):
        units = [self.units[r["unit_ref"]] for r in self.records[:2]]
        told = [dict(self.records[0], interpretation='It adds \u201cbase\u201d to the rest.', note=""),
                dict(self.records[1], interpretation="", note="The AI's answer could not be used: it quoted words that are not in the text.")]
        rows = run.rows_model_units(units, told)
        self.assertEqual(rows[0]["llm_interpretation"], '\u201cIt adds "base" to the rest.\u201d')
        self.assertEqual(rows[1]["llm_interpretation"], "The AI's answer could not be used: it quoted words that are not in the text.")
        self.assertEqual(run.rows_model_units(units)[0]["llm_interpretation"], "", "before the step has run the column is empty")

    def test_a_model_that_speaks_of_an_error_in_the_code_does_not_get_its_cell_withheld(self):
        """Code that calls stop() will be described with the very word AIVA never uses of its own
        results. The words are the model's, shown as a quotation, so the wording gate lets them by."""
        row = run.rows_model_units([self.units[self.records[0]["unit_ref"]]],
                                   [dict(self.records[0], interpretation="It stops with an error when the zone is unknown.", note="")])[0]
        self.assertEqual(run.plain_cell(row["llm_interpretation"], False, self.store), row["llm_interpretation"])
        self.assertEqual(run.plain_cell("It stops with an error.", False, self.store), run.CELL_WITHHELD, "AIVA's own words are still held to the rule")

    def test_an_interpretation_is_outside_the_accounting(self):
        """It is an aid to reading: no status, no flagged item, no part in the coverage identity."""
        import standin_chat
        with_it = helpers.run_sample("A_minimal", chat=standin_chat.make_chat(misbehave=False))
        without = helpers.run_sample("A_minimal", chat=standin_chat.make_chat(misbehave=False), settings={"interpret_code": False})
        kept = lambda item: {k: v for k, v in item.items() if k not in ("provenance", "created_at", "item_id")}
        first, second = (run.open_store(p, s) for p, s, _ in (with_it, without))
        self.assertEqual([kept(i) for i in first.read("flagged_items")], [kept(i) for i in second.read("flagged_items")])
        self.assertEqual(helpers.without_times(first.read("coverage")), helpers.without_times(second.read("coverage")))
        self.assertEqual(second.read("interpretations"), [], "switched off, the step asks nothing")
