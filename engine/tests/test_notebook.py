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
        if name not in self.values:                 # as a fresh Databricks notebook does
            raise Exception("No widget named '%s' is defined" % name)
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

    def test_cell_2_makes_every_widget_before_it_needs_one(self):
        """On a freshly opened notebook no widget exists, so nothing can be typed in. Cell 2
        comes first and makes every widget; it needs no installed package, which is what lets
        it run before cell 3 installs anything."""
        cells = [c for c in json.load(open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"),
                                           encoding="utf-8"))["cells"]]
        dbutils = FakeDbutils({})                    # nothing exists yet
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            exec(compile("".join(cells[1]["source"]), "cell 2", "exec"), {"dbutils": dbutils})
        for widget in ("llm_endpoint", "llm_token", "llm_user_id", "model_id", "project", "run",
                       "projects_dir", "jfrog_index_url", "concurrency_limit", "token_cap",
                       "reviewer_id", "reviewer_role", "scratch_dir"):
            self.assertIn(widget, dbutils.widgets.values, "cell 2 did not make the %s widget" % widget)
        self.assertIn("run cell 3", printed.getvalue())
        self.assertNotIn("pip", "".join(cells[1]["source"]), "cell 2 installs nothing, so it can be re-run freely")

    def test_every_cell_imports_the_modules_it_uses(self):
        """Cell 3 restarts Python, which clears every name defined before it. A cell that
        leaned on an import made in an earlier cell then stops with a NameError the moment
        anyone runs the cells in another order. Each cell therefore imports its own."""
        standard = {"os", "sys", "re", "json", "time", "datetime", "shutil", "tempfile",
                    "importlib", "threading", "subprocess", "gzip", "math", "hashlib"}
        notebook = json.load(open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"), encoding="utf-8"))
        for number, cell in enumerate(notebook["cells"], start=1):
            if cell["cell_type"] != "code":
                continue
            tree = ast.parse("".join(cell["source"]))
            imported, named, used = set(), set(), set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update((alias.asname or alias.name).split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.update(alias.asname or alias.name for alias in node.names)
                elif isinstance(node, ast.Name):
                    (named if isinstance(node.ctx, ast.Store) else used).add(node.id)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    named.add(node.name)
            missing = sorted((used & standard) - imported - named)
            self.assertEqual(missing, [], "cell %d uses %s without importing it" % (number, ", ".join(missing)))

    def test_no_package_is_installed_from_an_index_nobody_named(self):
        """Cell 3 installs from the widget cell 2 made. With no URL in it nothing may be
        installed, rather than falling through to pip's own default index in silence."""
        source = "".join(json.load(open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"),
                                        encoding="utf-8"))["cells"][2]["source"])
        self.assertIn("jfrog_index_url", source, "cell 3 installs from the widget cell 2 made")
        self.assertIn("ALLOW_DEFAULT_INDEX", source, "pip's own default index is a decision, never a fallback")
        self.assertIn("returncode", source, "a failed install must not look like a finished one")

    def run_cell_3(self, runtime_starts):
        """Cell 3, executed with pip replaced by a recorder, so that what it WOULD run is seen."""
        from unittest import mock
        cells = ["".join(c["source"]) for c in json.load(open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"),
                                                              encoding="utf-8"))["cells"]]
        ran, restarted = [], []

        class Done:
            def __init__(self, code, stderr=""):
                self.returncode, self.stdout, self.stderr = code, "", stderr

        def fake_run(command, capture_output=True, text=True):
            ran.append(list(command))
            if "-c" in command and "import numpy, pandas, pyarrow" in command:
                return Done(0) if runtime_starts else Done(1, "ImportError: numpy.core.multiarray failed to import")
            return Done(0)

        class Library:
            def restartPython(self):
                restarted.append(True)

        fake = FakeDbutils({"jfrog_index_url": "https://user:SECRET@jfrog.example/simple"})
        fake.library = Library()
        printed, previous = io.StringIO(), os.getcwd()
        os.chdir(helpers.ROOT_DIR)
        try:
            with mock.patch("subprocess.run", fake_run), contextlib.redirect_stdout(printed):
                exec(compile(cells[2], "cell 3", "exec"), {"dbutils": fake})
        finally:
            os.chdir(previous)
        return ran, restarted, printed.getvalue()

    def test_cell_3_pins_every_package_the_runtime_owns_to_the_version_it_has(self):
        """On 21 September 2026 cell 3 crashed a notebook session: the newest xarray, pulled in by
        rdata, wanted a newer pandas and numpy than the runtime had, pip installed numpy 2.5.3 into
        the notebook, and the runtime's own pyarrow - compiled against numpy 1.x - could no longer
        be imported. The kernel imports it to start, so every restart crashed. Every package the
        runtime owns is now pinned to the version it already has."""
        import importlib.metadata
        ran, _, said = self.run_cell_3(runtime_starts=True)
        install = [command for command in ran if "install" in command][0]
        self.assertIn("-c", install, "pip must be constrained to the runtime's own versions")
        with open(install[install.index("-c") + 1], encoding="utf-8") as handle:
            pins = handle.read().split()
        for name in ("numpy", "pandas", "pyarrow", "scipy"):
            try:
                have = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                continue
            self.assertIn("%s==%s" % (name, have), pins, "%s must be kept exactly as the runtime has it" % name)
        self.assertIn("Kept exactly as the runtime has them", said)
        self.assertNotIn("SECRET", said, "the index URL's credential is never printed")

    def test_cell_3_restarts_python_only_when_the_runtime_still_starts(self):
        _, restarted, said = self.run_cell_3(runtime_starts=True)
        self.assertEqual(restarted, [True])
        self.assertNotIn("STOPPED BEFORE RESTARTING", said)

    def test_cell_3_does_not_restart_python_into_a_crash(self):
        """The restart is what crashed the session. If the runtime's own packages no longer import
        together, cell 3 keeps the session alive and says how to undo the install."""
        _, restarted, said = self.run_cell_3(runtime_starts=False)
        self.assertEqual(restarted, [], "restarting now would crash the notebook session")
        self.assertIn("STOPPED BEFORE RESTARTING PYTHON", said)
        self.assertIn("detach this notebook from the cluster and attach it again", said)
        self.assertIn("Do not restart the cluster", said)

    def test_the_sign_off_cell_asks_the_real_model_and_changes_nothing(self):
        """Cell 19 is the one place the reading sign-off bar can be met, so it must use the chat()
        the analyst pasted in cell 6 and never the stand-in, and it must not turn guided reading
        on: the owner does that, after reading the report. It is never executed offline."""
        with open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"), encoding="utf-8") as handle:
            source = "".join(json.load(handle)["cells"][18]["source"])
        self.assertIn("reading_report.run(chat, LIVE", source)
        self.assertNotIn("standin", source.replace("stand-in", ""), "the sign-off is not evidence if it uses the stand-in")
        self.assertNotIn("agentic_reading\"] =", source)
        self.assertNotIn("make_settings", source, "the cell reports; it does not change a setting")

    def test_the_cells_run_from_setup_to_verification_with_the_stand_in(self):
        with open(os.path.join(helpers.ROOT_DIR, "AIVA_Interface.ipynb"), encoding="utf-8") as handle:
            cells = ["".join(c["source"]) for c in json.load(handle)["cells"]]
        self.assertEqual(len(cells), 19)
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
            run_cell(2)                              # the widgets, before anything is installed
            self.assertIn("works", run_cell(4))      # cell 3 installs packages; not run here
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
