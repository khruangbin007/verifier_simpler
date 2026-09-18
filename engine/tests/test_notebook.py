"""The notebook's cells are run here, outside Databricks, against a stand-in for dbutils, so that a
change in the engine that would break a cell is seen before an analyst sees it."""
import ast
import contextlib
import io
import json
import os
import shutil
import unittest

import helpers


class FakeWidgets:
    def __init__(self, values):
        self.values = dict(values)

    def text(self, name, default, label=""):
        self.values.setdefault(name, default)

    def dropdown(self, name, default, choices, label=""):
        if self.values.get(name) not in choices:
            self.values[name] = default

    def get(self, name):
        return self.values[name]


class FakeDbutils:
    def __init__(self, values):
        self.widgets = FakeWidgets(values)


class NotebookCells(unittest.TestCase):
    def test_every_code_cell_is_valid_python(self):
        """The cells are written as text by build_notebook.py, where a mis-escaped backslash
        can put a real line break inside a string. An analyst would meet that as a syntax
        problem in the notebook, so it is caught here instead."""
        notebook = json.load(open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"), encoding="utf-8"))
        for number, cell in enumerate(notebook["cells"], start=1):
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                try:
                    ast.parse(source)
                except SyntaxError as problem:
                    self.fail("cell %d does not parse: %s" % (number, problem))

    def test_no_package_is_installed_from_an_index_nobody_named(self):
        """Cell 2 runs before cell 3 makes the widgets, so on a fresh notebook the index URL
        is not there yet. It must not fall through to pip's own default index in silence."""
        source = "".join(json.load(open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"),
                                        encoding="utf-8"))["cells"][1]["source"])
        self.assertIn('dbutils.widgets.text("jfrog_index_url"', source,
                      "cell 2 makes the widget itself, because cell 3 cannot run before the packages are in")
        self.assertIn("ALLOW_DEFAULT_INDEX", source, "pip's own default index is a decision, never a fallback")
        self.assertIn("returncode", source, "a failed install must not look like a finished one")

    def test_the_cells_run_from_setup_to_verification_with_the_stand_in(self):
        with open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"), encoding="utf-8") as handle:
            cells = ["".join(c["source"]) for c in json.load(handle)["cells"]]
        self.assertEqual(len(cells), 18)
        projects = helpers.scratch()
        space = {"dbutils": FakeDbutils({"model_id": "NBTEST", "projects_dir": projects, "llm_token": "tok-SECRET-123", "llm_endpoint": "https://x", "llm_user_id": "u1",
                                         "reviewer_id": "analyst.one", "reviewer_role": "Validator"})}
        def run_cell(number, replace=None):
            source = cells[number - 1]
            for old, new in (replace or {}).items():
                self.assertIn(old, source)
                source = source.replace(old, new)
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                exec(compile(source, "cell %d" % number, "exec"), space)
            return printed.getvalue()
        previous = os.getcwd()
        os.chdir(helpers.ROOT_DIR)
        try:
            run_cell(3)
            self.assertIn("works", run_cell(4))
            shown = run_cell(5)
            self.assertNotIn("tok-SECRET-123", shown)
            self.assertIn("14 characters", shown)
            self.assertIn("stand-in", run_cell(7, {"USE_STANDIN = False": "USE_STANDIN = True"}))
            self.assertIn("still empty", run_cell(8))
            project_dir = os.path.join(projects, "NBTEST", sorted(os.listdir(os.path.join(projects, "NBTEST")))[0])
            shutil.rmtree(os.path.join(project_dir, "Inputs"))
            shutil.copytree(os.path.join(helpers.SAMPLES_DIR, "A_minimal", "Inputs"), os.path.join(project_dir, "Inputs"))
            self.assertIn("All three Inputs folders", run_cell(8))
            self.assertIn("Outline of the methodology", run_cell(9))
            self.assertIn("Stopped after step 06", space["RESULT"]["message"])
            self.assertIn("confirmed by analyst.one", run_cell(10))
            self.assertIn("judge-unit-to-canon", run_cell(11))
            self.assertIn("Waiting for a person", run_cell(12, {'MODE = "A"': 'MODE = "C"'}))
            self.assertIn("account-coverage", run_cell(13))
            self.assertIn("Determinations recorded this time: 0", run_cell(14))
            verdicts = run_cell(15)
            self.assertNotIn("Not confirmed", verdicts)
            self.assertIn("Confirmed", verdicts)
            self.assertIn("Output.xlsx", run_cell(17))
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
