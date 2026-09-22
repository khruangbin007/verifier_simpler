"""Tests of core.py: contracts, canonical JSON, hashes, numbers, symbols, the expression tree."""
import unittest
import helpers  # noqa: F401  (sets the import path)
from core import Expr


class CanonicalJsonAndHashes(unittest.TestCase):
    def test_canonical_json_is_stable_under_key_order(self):
        self.assertEqual(core.canonical_json({"b": 1, "a": (1, 2)}), core.canonical_json({"a": [1, 2], "b": 1}))

    def test_content_hash_ignores_white_space_and_line_endings_and_nothing_else(self):
        base = core.content_hash("The floor is 0.03.\nIt applies to all segments.")
        self.assertEqual(base, core.content_hash("The  floor is 0.03.\r\n\tIt applies to all   segments. "))
        self.assertNotEqual(base, core.content_hash("The floor is 0.04.\nIt applies to all segments."))
        self.assertNotEqual(base, core.content_hash("the floor is 0.03.\nIt applies to all segments."))

    def test_swhid_equals_the_git_blob_hash(self):
        self.assertEqual(core.swhid_content(b"hello\n"), "swh:1:cnt:ce013625030ba8dba906f756967f9e9ca394464a")

    def test_refs(self):
        self.assertEqual(core.make_ref("C", 9), "C-0009")
        self.assertEqual(core.make_ref("M", 42), "M-0042")

    def test_chain_detects_edited_removed_and_reordered_records(self):
        records = core.chain_records(core.GENESIS_HASH, [{"n": 1}, {"n": 2}, {"n": 3}])
        self.assertTrue(core.verify_chain(records)[0])
        edited = [dict(r) for r in records]; edited[1]["n"] = 99
        self.assertEqual(core.verify_chain(edited)[:2], (False, 1))
        self.assertFalse(core.verify_chain([records[0], records[2]])[0])
        self.assertFalse(core.verify_chain([records[1], records[0], records[2]])[0])

    def test_chain_leaves_out_time_stamps_so_the_same_content_gives_the_same_head(self):
        one = core.chain_records(core.GENESIS_HASH, [{"n": 1, "provenance": {"created_at": "10:00", "run_id": "a"}}], ("created_at", "run_id"))
        two = core.chain_records(core.GENESIS_HASH, [{"n": 1, "provenance": {"created_at": "11:30", "run_id": "b"}}], ("created_at", "run_id"))
        self.assertEqual(core.chain_head(one), core.chain_head(two))

    def test_dataclasses_are_frozen_and_serialise(self):
        chunk = core.Chunk("C-0001", "canon", "m.xml", "Paragraph", 1, ("A",), "1", 1, "text", "/p[1]", core.content_hash("text"))
        with self.assertRaises(Exception):
            chunk.text = "other"
        self.assertIn('"ref":"C-0001"', core.canonical_json(chunk))


class Numbers(unittest.TestCase):
    def test_percent_basis_points_and_scientific_notation_become_the_same_value(self):
        values = {core.parse_number("0.1", "%")["value"], core.parse_number("10", " basis points")["value"],
                  core.parse_number("1e-3")["value"]}
        self.assertEqual(values, {"0.001"})

    def test_percentile_also_yields_the_fraction(self):
        parsed = core.parse_number("99.9", "th percentile")
        self.assertEqual((parsed["value"], parsed["decimals"], parsed["as_written"]), ("0.999", 3, "99.9th percentile"))

    def test_form_as_written_and_decimals_are_kept(self):
        parsed = core.parse_number("0.150")
        self.assertEqual((parsed["value"], parsed["decimals"], parsed["as_written"]), ("0.15", 3, "0.150"))
        self.assertEqual(core.parse_number("5")["decimals"], 0)

    def test_labels_years_and_numbering_are_not_numbers_of_the_text(self):
        text = "3.1 Floors. See Table 3 and section 4.2: since 2024 the floor of 0.03 applies."
        self.assertEqual([n["as_written"] for n in core.find_numbers(text)], ["0.03"])

    def test_whole_numbers_are_shown_as_whole_numbers(self):
        self.assertEqual(core.plain_number(5.0), "5")
        self.assertEqual(core.plain_number(0.1 + 0.2), "0.3")
        self.assertEqual(core.plain_number(1e-7), "0.0000001")


class Symbols(unittest.TestCase):
    def test_greek_by_name_character_and_latex(self):
        self.assertEqual({core.normalise_symbol(s) for s in ("\u03c1", "rho", "\\rho")}, {"rho"})

    def test_subscripts(self):
        self.assertEqual({core.normalise_symbol(s) for s in ("PD_i", "PD[i]", "PD_{i}", "PD\u1d62")}, {"pd_i"})

    def test_case_kept_for_single_letters_folded_for_words(self):
        self.assertEqual(core.normalise_symbol("K"), "K")
        self.assertEqual(core.normalise_symbol("LGD"), "lgd")


class ExpressionTree(unittest.TestCase):
    def test_linear_notation_uses_brackets_only_where_needed(self):
        tree = Expr("mul", args=(Expr("sym", "a"), Expr("sub", args=(Expr("num", value="1"), Expr("sym", "b")))))
        self.assertEqual(core.expr_to_text(tree), "a * (1 - b)")
        power = Expr("pow", args=(Expr("neg", args=(Expr("sym", "x"),)), Expr("num", value="2")))
        self.assertEqual(core.expr_to_text(power), "(-x)^2")

    def test_round_trip_through_json(self):
        tree = Expr("call", "normal_cdf", args=(Expr("sym", "x"),), span=(3, 4))
        self.assertEqual(core.expr_from_dict(core.to_plain(tree)), tree)
        self.assertEqual(core.expr_symbols(tree), ("x",))


class Wording(unittest.TestCase):
    def test_banned_wording_is_found_as_whole_words_only(self):
        for text in ("a Finding", "two errors", "Severity", "low priority", "impact: high"):
            self.assertTrue(core.has_banned_wording(text), text)
        for text in ("ValueError", "terrors", "a path finder", "a high value", "minority"):
            self.assertFalse(core.has_banned_wording(text), text)

    def test_no_category_or_status_rates_seriousness(self):
        for wording in core.CATEGORIES + core.CLEAN_STATUSES + core.NOT_CLEAN_STATUSES:
            self.assertFalse(core.has_banned_wording(wording), wording)


class NumbersAsProseWritesThem(unittest.TestCase):
    """A thousands grouping with commas is one number. Found on review: "1,000" was read as the
    two numbers 1 and 0, so every grouped value in a methodology table compared wrongly and
    put spurious numbers into the search."""

    def test_comma_grouped_thousands_are_one_number(self):
        from core import find_numbers
        self.assertEqual([n["value"] for n in find_numbers("a limit of 1,000 units and 250,000.5 in all")], ["1000", "250000.5"])
        self.assertEqual([n["value"] for n in find_numbers("-1,250 and 1,000,000")], ["-1250", "1000000"])

    def test_a_comma_between_other_digit_counts_is_not_a_grouping(self):
        """"1,5" is a decimal comma in some writing; guessing which would be guessing."""
        from core import find_numbers
        self.assertEqual([n["value"] for n in find_numbers("1,5")], ["1", "5"])
        self.assertEqual([n["value"] for n in find_numbers("table 3, 100 rows")], ["100"])

    def test_one_value_written_twice_in_a_cell_is_one_number(self):
        import review
        self.assertEqual(review.number_of("0.15 (15%)")["value"], "0.15")
        self.assertIsNone(review.number_of("0.15 or 0.20"))


if __name__ == "__main__":
    unittest.main()
