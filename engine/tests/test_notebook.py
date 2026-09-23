"""The notebook's cells are run here, outside Databricks, against a stand-in for dbutils, so that a
change in the engine that would break a cell is seen before an analyst sees it."""
import ast
import contextlib
import io
import json
import os
import re
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
    """The five cells, executed with a fake dbutils and the stand-in chat(), from a bare folder to a
    verified evidence pack. Cell 1's install branch is not run: every package is present here."""

    def cells(self):
        with open(develop_notebook(), encoding="utf-8") as handle:
            return ["".join(cell["source"]) for cell in json.load(handle)["cells"]]

    def test_every_cell_is_valid_python(self):
        for number, source in enumerate(self.cells(), start=1):
            try:
                ast.parse(source)
            except SyntaxError as problem:
                self.fail("cell %d does not parse: %s" % (number, problem))

    def test_the_notebook_holds_no_code_of_its_own_but_the_organisations_chat(self):
        """Every cell is a call into the engine; cell 2 also holds chat(), which is the organisation's."""
        cells = self.cells()
        self.assertEqual([c.strip().split("\n")[-1].split("#")[0].strip() for c in cells],
                         ["verifier.setup(dbutils)", "verifier.check_chat(chat)", "verifier.review()", "verifier.verify()"])
        code = lambda cell: [l for l in cell.split("\n") if l.strip() and not l.strip().startswith("#")]
        self.assertEqual([len(code(cells[0])), len(code(cells[2])), len(code(cells[3]))], [2, 1, 1])

    def test_setup_makes_every_widget_before_it_needs_one(self):
        """On a freshly opened notebook no widget exists. Cell 1 makes each one before reading it, and
        needs no installed package to do so, which is what lets it run on a bare cluster."""
        import inspect
        import verifier as runner
        made = {name for name, _, _ in runner.WIDGETS}
        section = inspect.getsource(runner)[inspect.getsource(runner).index("def live(name):"):]
        read = set(re.findall(r'widgets\.get\("(\w+)"\)', section))
        self.assertTrue(read <= made, "read before made: %s" % sorted(read - made))
        setup = inspect.getsource(runner.setup)
        self.assertLess(setup.index("widgets.text("), setup.index("install("), "widgets come before the install")

    def test_no_package_is_installed_from_an_index_nobody_named(self):
        import inspect
        import verifier as runner
        source = inspect.getsource(runner.install)
        self.assertIn("allow_default_index=False", inspect.getsource(runner.setup))
        self.assertIn("Nothing is installed from an index you did not name", source)
        self.assertIn('"-c", constraints', source, "the runtime's own packages are pinned")
        self.assertIn("import numpy, pandas, pyarrow", source, "the runtime is probed before Python is restarted")
        self.assertIn("Detach this notebook", source, "and the way out of a broken install is spelled out")

    def test_cell_2s_chat_sends_the_user_id_and_the_token_it_reads_at_call_time(self):
        """Cell 2's chat() is the organisation's own. It reads the token and the user id through
        live() when it is called. The widget is reviewer_id; found on review, live("reviewer_id")
        returned nothing because the engine keeps the id as llm_user_id, so every request would
        have gone out with an empty SP_SSO_UID. This sends one request to a recorder."""
        from unittest import mock
        import verifier as runner
        source = self.cells()[1]
        values = {"llm_endpoint": "https://gateway.example/chat", "llm_token": "tok-FIRST", "reviewer_id": "mel_lorenzo",
                  "model_id": "NBCHAT", "project": "2026-01-01"}
        runner.NOTEBOOK.update(dbutils=FakeDbutils(values), projects=helpers.scratch(), live=None, chat=None, paths=None)
        sent = []

        class Reply:
            def raise_for_status(self):
                pass
            def json(self):
                return {"answer": "OK"}

        def post(url, json=None, headers=None, timeout=None):
            sent.append({"url": url, "json": json, "headers": headers})
            return Reply()

        space = {"verifier": runner, "__name__": "notebook"}
        with mock.patch("requests.post", post), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source, "cell 2", "exec"), space)
            runner.NOTEBOOK["dbutils"].widgets.values["llm_token"] = "tok-SECOND"     # pasted while a run works
            self.assertEqual(space["chat"]("system text", "main text"), {"answer": "OK"})
        request = sent[-1]
        self.assertEqual(request["headers"]["SP_SSO_UID"], "mel_lorenzo", "the user id must reach the gateway")
        self.assertEqual(request["headers"]["Authorization"], "Bearer tok-SECOND", "the token is read when chat() is called")
        self.assertEqual(request["json"]["query"], "main text")
        self.assertEqual(request["json"]["optionalParameter"]["DefaultPrompt"], "system text")
        self.assertEqual(request["url"], "https://gateway.example/chat")

    def test_the_four_cells_run_from_setup_to_verification(self):
        cells = self.cells()
        self.assertEqual(len(cells), 4)
        projects = helpers.scratch()
        values = {"model_id": "NBTEST", "llm_token": "tok-SECRET-123", "llm_endpoint": "https://x",
                  "reviewer_id": "analyst.one", "project": "",
                  "jfrog_index_url": "", "concurrency_limit": "4", "token_cap": "40000"}
        space = {"dbutils": FakeDbutils(values), "__name__": "notebook"}

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
            import verifier as runner
            runner.NOTEBOOK.update(dbutils=None, live=None, chat=None, paths=None, result=None)   # a fresh session
            shown = run_cell(1, {"verifier.setup(dbutils)": "verifier.setup(dbutils, home=%r, projects=%r)" % (helpers.ROOT_DIR, projects)})   # projects go to scratch, never the repo
            self.assertIn("engine", shown)
            self.assertNotIn("tok-SECRET-123", shown, "the token is never printed")
            self.assertIn("14 characters", shown)
            # the notebook carries no stand-in; the test puts one in place of the organisation's chat()
            stand_in = "import standin_chat\nverifier.check_chat(standin_chat.chat)"
            self.assertIn("PUT YOUR FILES IN THESE THREE FOLDERS",
                          run_cell(2, {"verifier.check_chat(chat)": stand_in}), "cell 2 names the folders")
            self.assertIn("Run cell 3 first", run_cell(4), "cell 4 before cell 3 says what to do instead of raising")
            self.assertIn("Put the files in", run_cell(3))
            project_dir = os.path.join(projects, "NBTEST", sorted(os.listdir(os.path.join(projects, "NBTEST")))[0])
            shutil.rmtree(os.path.join(project_dir, "Inputs"))
            shutil.copytree(os.path.join(helpers.SAMPLES_DIR, "A_minimal", "Inputs"), os.path.join(project_dir, "Inputs"))
            shown = run_cell(3)
            self.assertIn("What each step did:", shown)
            self.assertIn("link-units", shown, "cell 3 runs the model steps as well as the reading")
            self.assertIn("Run folder:", shown)
            self.assertEqual(runner.NOTEBOOK["result"]["state"], "finished", runner.NOTEBOOK["result"])
            self.assertIn("step 05", run_cell(3), "running cell 3 again shows the steps and repeats none")
            shown = run_cell(4)
            self.assertIn("Verifying the evidence pack", shown)
            self.assertNotIn("differs", shown.lower().split("verifying the evidence pack")[1])
            for line in shown.split("\n"):
                self.assertEqual(helpers.banned_wording(line), "", line)
        finally:
            os.chdir(previous)


def develop_notebook():
    import develop
    return develop.NOTEBOOK


if __name__ == "__main__":
    unittest.main()
