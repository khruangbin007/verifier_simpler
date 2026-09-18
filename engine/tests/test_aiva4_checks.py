"""Tests of aiva4_checks: the value rule, formula comparison, tables, rules, statuses and the identity."""
import unittest

import yaml

import helpers
import aiva0_shared as shared
import aiva1_documents as documents
import aiva4_checks as checks
import aiva5_run_report as run

SETTINGS = run.make_settings()
NOTATION = documents.load_notation(run.REFERENCES_DIR)
STOP = set()


def compared(code, stated, defaults=None, bridge=None):
    prepared = checks.prepare_alignment(documents.parse_formula(code, NOTATION), documents.parse_formula(stated, NOTATION), defaults or {}, bridge or {})
    return checks.compare_formulas(prepared, SETTINGS, {}), prepared


class ValueRule(unittest.TestCase):
    def test_the_table_of_the_rule(self):
        number = shared.parse_number
        cases = ((("0.15", ""), ("0.15", ""), True, "agrees"), (("0.035", ""), ("0.03512", ""), True, "agrees at stated precision"),
                 (("0.15", ""), ("0.10", ""), True, "differs"), (("12.5", "%"), ("0.125", ""), True, "agrees"),
                 (("10", "bp"), ("0.001", ""), True, "agrees"), (("0.125", ""), ("0.13", ""), False, "agrees at the coarser precision"),
                 (("0.125", ""), ("0.14", ""), False, "differs"), (("2.5", ""), ("2.45", ""), True, "agrees at stated precision"),
                 (("0.150", ""), ("0.15", ""), True, "agrees"), (("1e-3", ""), ("0.001", ""), True, "agrees"))
        for stated, other, exact, expected in cases:
            self.assertEqual(checks.compare_values(number(*stated), number(*other), exact)[0], expected, (stated, other))

    def test_the_rounding_convention_is_named_only_when_the_two_differ(self):
        outcome, note = checks.compare_values(shared.parse_number("2.5"), shared.parse_number("2.45"), exact=True)
        self.assertEqual((outcome, note), ("agrees at stated precision", "under round-half-up"))
        self.assertEqual(checks.compare_values(shared.parse_number("0.04"), shared.parse_number("0.0351"), exact=True)[1], "")


class FormulaComparison(unittest.TestCase):
    def test_the_corpus_no_differing_pair_ever_agrees(self):
        with open(helpers.os.path.join(helpers.TESTS_DIR, "equivalence_corpus.yaml"), encoding="utf-8") as handle:
            pairs = yaml.safe_load(handle)["pairs"]
        self.assertEqual(sum(p["expect"] == "equivalent" for p in pairs), 50)
        self.assertEqual(sum(p["expect"] == "different" for p in pairs), 50)
        not_agreeing = []
        for pair in pairs:
            result, _ = compared(pair["code"], pair["stated"])
            if pair["expect"] == "different":
                self.assertNotEqual(result["outcome"], "agrees", pair["name"])
                if result["outcome"] == "differs":
                    self.assertIsNotNone(result["counterexample"], pair["name"])
            elif result["outcome"] != "agrees":
                not_agreeing.append(pair["name"])
        self.assertEqual(not_agreeing, [], "equivalent pairs that did not end as agreeing")

    def test_differs_always_comes_with_a_counterexample_and_the_same_seed_gives_the_same_one(self):
        first, _ = compared("y = N((N^-1(pd) - sqrt(rho)*N^-1(q))/sqrt(1-rho))", "PDc = N((N^-1(PD) + sqrt(rho)*N^-1(0.999))/sqrt(1-rho))", {"q": "0.999"})
        second, _ = compared("y = N((N^-1(pd) - sqrt(rho)*N^-1(q))/sqrt(1-rho))", "PDc = N((N^-1(PD) + sqrt(rho)*N^-1(0.999))/sqrt(1-rho))", {"q": "0.999"})
        self.assertEqual(first["outcome"], "differs")
        self.assertEqual(first["counterexample"], second["counterexample"])
        self.assertEqual(sorted(first["counterexample"]["inputs"]), ["pd", "rho"])

    def test_alignment_is_fixed_before_comparing_so_swapped_symbols_end_as_differs(self):
        result, prepared = compared("y = b - a", "Y = a - b")
        self.assertEqual([(c, s) for c, s, _ in prepared["pairs"]], [("a", "a"), ("b", "b")])
        self.assertEqual(result["outcome"], "differs")

    def test_a_default_is_put_in_only_where_the_stated_formula_shows_that_number(self):
        result, prepared = compared("y = l*w*h/divisor", "DW = L*W*H/5000", {"divisor": "5000"})
        self.assertEqual((result["outcome"], prepared["substitute"]), ("agrees", {"divisor": "5000"}))
        result, prepared = compared("y = l*w*h/divisor", "DW = L*W*H/6000", {"divisor": "5000"})
        self.assertEqual((result["outcome"], result["undecided_reason"]), (shared.CHECK_UNDECIDED, shared.UNDECIDED_REASONS[2]))

    def test_the_bridge_vocabulary_aligns_symbols_described_by_the_same_words(self):
        bridge = {"rho_a": [{"words": ["asset", "correlation"]}], "R": [{"words": ["asset", "correlation"]}]}
        result, prepared = compared("y = 1 - rho_a", "Y = 1 - R", bridge=bridge)
        self.assertEqual((result["outcome"], prepared["pairs"][0][2]), ("agrees", "vocabulary"))

    def test_symbols_left_over_make_the_check_undecided_never_agreeing(self):
        result, _ = compared("y = a*b + z", "Y = a*b")
        self.assertEqual((result["outcome"], result["undecided_reason"]), (shared.CHECK_UNDECIDED, "symbols could not be aligned"))

    def test_points_outside_a_domain_are_not_counted_and_too_few_valid_points_is_undecided(self):
        tree = documents.parse_formula("y = ln(x)", NOTATION)
        self.assertIsNone(checks.evaluate(tree.args[1], {"x": -1.0}))
        result, _ = compared("y = sqrt(x - 100)", "Y = sqrt(x - 100) + 0")
        self.assertIn(result["outcome"], ("agrees", shared.CHECK_UNDECIDED))
        prepared = checks.prepare_alignment(documents.parse_formula("y = sqrt(x - 100)", NOTATION), documents.parse_formula("Y = sqrt(x - 100.5)", NOTATION), {}, {})
        result = checks.compare_formulas(prepared, SETTINGS, {})
        self.assertEqual((result["outcome"], result["undecided_reason"]), (shared.CHECK_UNDECIDED, "too few valid sample points"))

    def test_stored_values_are_used_row_by_row(self):
        tree = documents.parse_formula("y = rate * 2", NOTATION)
        points = checks.sample_points([tree.args[1]], ["rate"], SETTINGS, {"rate": [0.85, 1.1, 2.75]})
        self.assertEqual({p["rate"] for p in points}, {0.85, 1.1, 2.75})

    def test_an_operation_aiva_cannot_evaluate_is_never_guessed(self):
        tree = shared.Expr("call", name="sum_over", args=(shared.Expr("sym", name="x"),))
        with self.assertRaises(checks.NotEvaluable):
            checks.evaluate(tree, {"x": 1.0})


class TablesRulesAndProse(unittest.TestCase):
    OURS = {"header": ["segment", "lgd_floor"], "rows": [["Retail", "0.1"], ["Corporate", "0.25"], ["Bank", "0.45"]], "row_key": ["segment"], "column_types": ["text", "number"]}
    THEIRS = {"header": ["Segment", "LGD floor"], "rows": [["Retail", "0.15"], ["Corporate", "0.25"], ["Insurer", "0.40"]], "row_key": ["Segment"]}

    def test_cells_are_compared_by_key_and_rows_on_one_side_only_are_listed(self):
        result = checks.reconcile(self.OURS, self.THEIRS, STOP, exact=True)
        self.assertEqual(result["outcome"], "differs")
        self.assertEqual([(c["row"], c["outcome"]) for c in result["cells"]], [("Corporate", "agrees"), ("Retail", "differs")])
        self.assertEqual((result["only_in_package"], result["only_in_other"]), (["Bank"], ["Insurer"]))

    def test_columns_without_usable_headers_are_matched_by_their_values(self):
        theirs = {"header": ["Class", "Value in force"], "rows": [["Retail", "0.10"], ["Corporate", "0.25"], ["Bank", "0.45"]], "row_key": ["Class"]}
        ours = dict(self.OURS, header=["segment", "lgd_floor"])
        result = checks.reconcile(ours, dict(theirs, header=["segment", "Value in force"]), STOP, exact=True)
        self.assertEqual(result["outcome"], "agrees")
        self.assertIn("by values", [p[2] for p in result["column_map"]])

    def test_a_percent_header_converts_the_stated_values(self):
        theirs = {"header": ["Segment", "LGD floor (%)"], "rows": [["Retail", "10"], ["Corporate", "25"], ["Bank", "45"]], "row_key": ["Segment"]}
        self.assertEqual(checks.reconcile(self.OURS, theirs, STOP, exact=True)["outcome"], "agrees")

    def test_a_table_in_long_form_is_laid_over_a_printed_grid(self):
        long_form = {"header": ["zone", "band", "rate"], "column_types": ["text", "text", "number"], "row_key": ["zone"],
                     "rows": [["North", "Light", "1.5"], ["North", "Heavy", "2.5"], ["South", "Light", "1.75"], ["South", "Heavy", "3"]]}
        grid = {"header": ["Zone", "Light", "Heavy"], "rows": [["North", "1.50", "2.50"], ["South", "1.75", "3.10"]], "row_key": ["Zone"]}
        result = checks.reconcile(long_form, grid, STOP, exact=True)
        self.assertEqual([(c["row"], c["column"], c["outcome"]) for c in result["cells"] if c["outcome"] == "differs"], [("South", "Heavy", "differs")])

    def test_rules_are_recognised_by_generic_phrases(self):
        chunk = {"text": "The rate is never taken below 0.03%. The discount is 1% per parcel, capped at 20%. Nothing else applies."}
        self.assertEqual([(kind, number["as_written"]) for kind, number, _ in checks.stated_rules(chunk)], [("floor", "0.03%"), ("cap", "20%")])

    def test_a_floor_held_as_the_default_of_an_argument_is_found_by_code_inspection(self):
        units, _ = helpers.units_of({"R/a.R": "floor_pd <- function(pd, floor = 0.0003) {\n  pmax(pd, floor)\n}\n"})
        members = [u for u in units if u["kind"] in (shared.KIND_FUNCTION, shared.KIND_FORMULA)]
        number = shared.find_numbers("never below 0.03%")[0]
        self.assertIn("maximum with 0.03%", checks.rule_in_trees("floor", number, members))
        self.assertEqual(checks.rule_in_trees("cap", number, members), "")

    def test_prose_numbers_are_compared_only_with_a_stated_number_that_found_no_equal(self):
        stated = [("C-0011", "The conditional probability is evaluated at the 99.9th percentile of the systematic factor.")]
        lines, differs = checks.prose_value_lines("cond_pd evaluates the conditional probability at the 99.5th percentile of the systematic factor.", stated, STOP, set(), "documentation")
        self.assertTrue(differs)
        stated = [("C-0003", "The dose rate (R) is 15 milligrams per kilogram.")]
        lines, differs = checks.prose_value_lines("It uses the dose rate of 15 milligrams per kilogram and never returns more than 4000 milligrams.", stated, STOP, set(), "documentation")
        self.assertFalse(differs)
        self.assertTrue(any("not compared" in line for line in lines))


class SeededSample(unittest.TestCase):
    """The acceptance test of Phase 8 and the identity of Phase 9, on F_capital_known."""
    @classmethod
    def setUpClass(cls):
        cls.paths, cls.settings, cls.result = helpers.run_sample("F_capital_known")
        cls.store = run.open_store(cls.paths, cls.settings)
        cls.units = {u["ref"]: u for u in cls.store.read("model_units")}
        cls.status = {s["unit_ref"]: s for s in cls.store.read("unit_status")}
        cls.items = cls.store.read("flagged_items")

    def ref_of(self, kind, name):
        return next(ref for ref, u in self.units.items() if u["kind"] == kind and u["name"] == name and not u["inside"])

    def test_the_flipped_sign_in_cond_pd_is_caught_with_a_counterexample(self):
        ref = self.ref_of(shared.KIND_FUNCTION, "cond_pd")
        self.assertEqual(self.status[ref]["status"], shared.ST_DIFFERS)
        self.assertTrue(self.status[ref]["cells"]["math_check"].split(": ", 1)[1].startswith("Numerical check: differs. With pd = "))
        self.assertIn("the code gives", self.status[ref]["cells"]["math_check"])
        self.assertTrue([i for i in self.items if ref in i["unit_refs"] and i["category"] == shared.CAT_CODE_DIFFERS])

    def test_all_six_seeded_differences_are_flagged_in_an_expected_category(self):
        expected = ((shared.KIND_FUNCTION, "cond_pd", shared.CAT_CODE_DIFFERS), (shared.KIND_FUNCTION, "asset_correlation", shared.CAT_CODE_DIFFERS),
                    (shared.KIND_FUNCTION, "floor_pd", shared.CAT_CODE_DIFFERS), (shared.KIND_TABLE, "lgd_floors", shared.CAT_VALUE_DIFFERS),
                    (shared.KIND_ROXYGEN, "cond_pd", shared.CAT_PKGDOC_VS_CODE))
        for kind, name, category in expected:
            ref = self.ref_of(kind, name)
            self.assertTrue([i for i in self.items if ref in i["unit_refs"] and i["category"] == category], (kind, name, category))
        stale = [i for i in self.items if i["category"] == shared.CAT_DOC_VS_CANON and "99.5th percentile" in i["observed"]]
        self.assertEqual(len(stale), 1)

    def test_an_equation_given_as_an_image_is_never_skipped(self):
        image = next(c for c in self.store.read("chunks_canon") if c["kind"] == "Equation" and not c["equation"]["readable"])
        self.assertTrue([i for i in self.items if image["ref"] in i["unit_refs"] and i["category"] == shared.CAT_NOT_READ])
        tree, source, reason = checks.stated_formula(image, {})
        self.assertEqual((tree, reason), (None, "the equation is an image"))

    def test_the_identity_not_clean_if_and_only_if_an_item_names_the_unit(self):
        named = {ref for item in self.items for ref in item["unit_refs"]}
        for ref, status in self.status.items():
            self.assertEqual(not status["clean"], ref in named, ref)
            self.assertEqual(status["clean"], status["status"] in shared.CLEAN_STATUSES)
        self.assertEqual(len(self.status), len(self.units) + len(self.store.read("chunks_doc")))
        self.assertEqual(len({i["item_id"] for i in self.items}), len(self.items))
        self.assertEqual(len({(i["unit_refs"][0], i["category"]) for i in self.items}), len(self.items))

    def test_a_broken_identity_stops_the_run_and_names_the_part(self):
        units, doc = self.store.read("model_units"), self.store.read("chunks_doc")
        statuses = self.store.read("unit_status")
        items = [shared.FlaggedItem(i["item_id"], i["category"], i["concerns"], tuple(i["unit_refs"]), i["item"], i["observed"]) for i in self.items]
        world = {"by_ref": {r["ref"]: r for r in units + doc + self.store.read("chunks_canon")}}
        info = self.store.read("package_info")
        checks.check_identity(units, doc, statuses, items, world, info)
        with self.assertRaisesRegex(checks.AivaDefect, "Part 1"):
            checks.check_identity(units, doc, statuses[1:], items, world, info)
        with self.assertRaisesRegex(checks.AivaDefect, "Part 2"):
            table = self.ref_of(shared.KIND_TABLE, "lgd_floors")
            checks.check_identity(units, doc, statuses, [i for i in items if table not in i.unit_refs], world, info)
        with self.assertRaisesRegex(checks.AivaDefect, "Part 3"):
            checks.check_identity([u for u in units if u["file"] != "R/utils.R"], doc, [s for s in statuses if self.units.get(s["unit_ref"], {}).get("file") != "R/utils.R"], items, world, info)

    def test_items_carry_a_path_side_by_side_texts_and_a_neutral_next_step(self):
        item = next(i for i in self.items if i["category"] == shared.CAT_VALUE_DIFFERS)
        self.assertIn("Supporting path:", item["observed"])
        self.assertIn("row Retail", item["observed"])
        self.assertTrue(item["methodology_says"].startswith("\u201c"))
        self.assertFalse(shared.has_banned_wording(item["suggested_next_step"]))


class CleanSamples(unittest.TestCase):
    def test_the_clean_baseline_flags_none_of_the_units_listed_as_clean(self):
        import csv
        for sample in ("A_minimal", "F_capital", "D_dosing"):
            paths, settings, _ = helpers.run_sample(sample)
            clean = {s["unit_ref"]: s["clean"] for s in run.open_store(paths, settings).read("unit_status")}
            with open(helpers.os.path.join(helpers.SAMPLES_DIR, sample, "gold_clean_units.csv"), encoding="utf-8") as handle:
                listed = [row["unit_ref"] for row in csv.DictReader(handle)]
            self.assertEqual([ref for ref in listed if not clean[ref]], [], sample)


if __name__ == "__main__":
    unittest.main()
