"""The one manual, the release manifest and the notebook must agree with the code.

There is one manual, docs/Manual.md, written by hand and checked by develop.manual_problems: every
function, sheet, setting, design rule, step and notebook cell it names must exist, and every
setting and rule must be explained. There is one release manifest, engine/release.json, and a run
records exactly the engine files it used. The notebook is built from develop.py and never edited.
"""
import json
import os
import unittest

import helpers
import verifier
runner = verifier   # the engine is one module now
import develop


class ManualAndCode(unittest.TestCase):
    def test_the_manual_and_the_code_agree(self):
        self.assertTrue(os.path.exists(develop.MANUAL), "docs/Manual.md is the one manual and must exist")
        self.assertEqual(develop.manual_problems(), [])

    def test_the_manual_is_the_only_file_in_docs(self):
        self.assertEqual(sorted(os.listdir(os.path.dirname(develop.MANUAL))), ["Manual.md"])

    def test_a_name_that_does_not_exist_is_reported(self):
        """The check is only worth having if it catches a wrong name."""
        with open(develop.MANUAL, encoding="utf-8") as handle:
            text = handle.read()
        folder = helpers.scratch()
        fake = os.path.join(folder, "Manual.md")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(text + "\nSee `runner.no_such_function` for details.\n")
        real = develop.MANUAL
        develop.MANUAL = fake
        try:
            self.assertTrue(any("runner.no_such_function" in problem for problem in develop.manual_problems()))
        finally:
            develop.MANUAL = real


    def test_a_path_or_test_file_that_does_not_exist_is_reported(self):
        """The check caught function names but not paths, so after the restructure the manual
        named a tools/ folder, a references/ folder and two test files that no longer existed,
        and still passed. It now checks those too."""
        with open(develop.MANUAL, encoding="utf-8") as handle:
            text = handle.read()
        fake = os.path.join(helpers.scratch(), "Manual.md")
        with open(fake, "w", encoding="utf-8") as handle:
            handle.write(text + "\nSee `engine/references/tag_rules.yaml`, `tools/recall_at_k.py` and `test_review.py`.\n")
        real = develop.MANUAL
        develop.MANUAL = fake
        try:
            problems = " ".join(develop.manual_problems())
        finally:
            develop.MANUAL = real
        for named in ("engine/references/tag_rules.yaml", "tools/recall_at_k.py", "test_review.py"):
            self.assertIn(named, problems)


class Notebook(unittest.TestCase):
    def test_the_notebook_is_the_one_develop_builds(self):
        built = develop.build_notebook(os.path.join(helpers.scratch(), "Verifier.ipynb"))
        with open(built, encoding="utf-8") as fresh, open(develop.NOTEBOOK, encoding="utf-8") as committed:
            self.assertEqual(committed.read(), fresh.read(), "run python engine/develop.py notebook")

    def test_four_cells_that_each_parse_and_say_which_they_are(self):
        import ast
        with open(develop.NOTEBOOK, encoding="utf-8") as handle:
            cells = ["".join(cell["source"]) for cell in json.load(handle)["cells"]]
        self.assertEqual(len(cells), 4)
        for number, source in enumerate(cells, start=1):
            ast.parse(source)
            self.assertIn("Cell %d of 4" % number, source.split("\n")[0])


class EngineMap(unittest.TestCase):
    """The engine's own map: read from verifier.py by its syntax tree, so it cannot drift from the code."""

    def test_the_map_holds_every_function_and_reaches_all_but_the_test_helpers(self):
        facts, sections, total_lines = develop.engine_facts()
        tree = develop.engine_tree(facts)
        self.assertGreater(len(facts), 200)
        self.assertTrue(sections and total_lines > len(facts))
        reached = set()
        for _, root in develop.ENGINE_ROOTS:
            reached |= develop.reached_from(facts, root)
        left = sorted(set(facts) - reached)
        self.assertEqual(left, ["find_path", "verify_ledger"], "only what the tests call is outside the flow")
        shown = {row["function"] for row in tree}
        self.assertEqual(shown, reached, "every function the roots reach is a row of the tree")
        for row in tree:
            parent = row["map_id"].rsplit(".", 1)[0]
            self.assertTrue("." not in row["map_id"] or any(other["map_id"] == parent for other in tree))
            self.assertEqual(row["level"], row["map_id"].count("."))

    def test_the_workbook_builds_with_its_five_sheets(self):
        import openpyxl
        import tempfile
        target = os.path.join(tempfile.mkdtemp(prefix="engine_map_"), "Engine_Map.xlsx")
        where, functions, rows = develop.build_engine_map(target)
        book = openpyxl.load_workbook(where, read_only=True)
        self.assertEqual(book.sheetnames, ["Engine_Info", "Functions", "Function_Map", "Sections", "Records"])
        self.assertEqual(book["Functions"].max_row - 1, functions)
        self.assertEqual(book["Function_Map"].max_row - 1, rows)


if __name__ == "__main__":
    unittest.main()
