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

    def test_cell_1_makes_every_widget_before_it_needs_one(self):
        """On a freshly opened notebook no widget exists. Cell 1 makes each one before reading it, and
        needs no installed package to do so, which is what lets it run on a bare cluster."""
        source = self.cells()[0]
        made = set(re.findall(r'widget\("(\w+)"', source))
        read = set(re.findall(r'w\.get\("(\w+)"\)', source))
        self.assertTrue(read <= made, "read before made: %s" % sorted(read - made))
        self.assertLess(source.index('widget("llm_endpoint"'), source.index("REQUIRED = "), "widgets come before the install")

    def test_no_package_is_installed_from_an_index_nobody_named(self):
        source = self.cells()[0]
        self.assertIn("ALLOW_DEFAULT_INDEX = False", source)
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
        live_values = runner.LiveValues()
        live_values.update("https://gateway.example/chat", "tok-FIRST", "mel_lorenzo")
        sent = []

        class Reply:
            def raise_for_status(self):
                pass
            def json(self):
                return {"answer": "OK"}

        def post(url, json=None, headers=None, timeout=None):
            sent.append({"url": url, "json": json, "headers": headers})
            return Reply()

        space = {"live": live_values.get, "__name__": "notebook"}
        with mock.patch("requests.post", post), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source.replace("USE_STANDIN = False", "USE_STANDIN = False\nACTIVE_CHAT = None"), "cell 2", "exec"), space)
            live_values.update("https://gateway.example/chat", "tok-SECOND", "mel_lorenzo")
            self.assertEqual(space["chat"]("system text", "main text"), {"answer": "OK"})
        request = sent[-1]
        self.assertEqual(request["headers"]["SP_SSO_UID"], "mel_lorenzo", "the user id must reach the gateway")
        self.assertEqual(request["headers"]["Authorization"], "Bearer tok-SECOND", "the token is read when chat() is called")
        self.assertEqual(request["json"]["query"], "main text")
        self.assertEqual(request["json"]["optionalParameter"]["DefaultPrompt"], "system text")
        self.assertEqual(request["url"], "https://gateway.example/chat")

    def test_the_sign_off_appendix_uses_the_real_chat_and_changes_nothing(self):
        source = self.cells()[4]
        self.assertIn("develop.run(ACTIVE_CHAT, LIVE", source)
        self.assertNotIn('agentic_reading"] =', source)

    def test_cell_4_in_the_background_with_an_old_token_runs_to_the_person(self):
        """The default mode, A: the run works in a background thread. Found in use: a token older
        than token_lifetime_minutes made the worker wait, silently, for a fresh one before its first
        call - though the token still worked - so no link, status or flagged item ever appeared.
        Age alone no longer blocks; only a call the gateway refuses does. And an error inside the
        worker is shown by cell 4 instead of dying with the thread."""
        cells = self.cells()
        projects = helpers.scratch()
        values = {"model_id": "NBBG", "projects_dir": projects, "llm_token": "tok-OLD-BUT-GOOD", "llm_endpoint": "https://x",
                  "reviewer_id": "analyst.two", "project": "", "run": "", "jfrog_index_url": "",
                  "concurrency_limit": "4", "token_cap": "40000", "scratch_dir": ""}
        space = {"dbutils": FakeDbutils(values), "__name__": "notebook"}

        def run_cell(number, replace=None):
            source = cells[number - 1]
            for old, new in (replace or {}).items():
                source = source.replace(old, new)
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                exec(compile(source, "cell %d" % number, "exec"), space)
            return printed.getvalue()

        previous = os.getcwd()
        os.chdir(helpers.ROOT_DIR)
        try:
            run_cell(1, {"HOME = notebook_folder()": "HOME = %r" % helpers.ROOT_DIR})
            run_cell(2, {"USE_STANDIN = False": "USE_STANDIN = True"})
            run_cell(3)
            project_dir = os.path.join(projects, "NBBG", sorted(os.listdir(os.path.join(projects, "NBBG")))[0])
            shutil.rmtree(os.path.join(project_dir, "Inputs"))
            shutil.copytree(os.path.join(helpers.SAMPLES_DIR, "A_minimal", "Inputs"), os.path.join(project_dir, "Inputs"))
            run_cell(3)
            space["LIVE"].set_at -= 3600                 # the token was pasted an hour ago, and still works
            run_cell(4)
            space["WORKER"].join(timeout=300)
            self.assertFalse(space["WORKER"].is_alive(), "the background run should finish, not wait for a fresh token")
            self.assertEqual(space["RESULT"].get("state"), "finished", space["RESULT"])
            shown = run_cell(4)
            self.assertIn("not working at the moment", shown)
            self.assertNotIn("WAITING FOR A FRESH TOKEN", shown)
            store = space["verifier"].open_store(space["PATHS"], space["SETTINGS"])
            self.assertTrue(store.read_calls(), "the model steps made their calls")
            self.assertTrue(store.read("graph_ledger"), "the links were recorded")
        finally:
            os.chdir(previous)

    def test_an_error_inside_the_background_run_is_shown_by_cell_4(self):
        source = self.cells()[3]
        self.assertIn('RESULT.update(state="failed"', source)
        self.assertIn("THE RUN STOPPED WITH A PROBLEM", source)

    def test_the_cells_run_from_setup_to_verification_with_the_stand_in(self):
        cells = self.cells()
        self.assertEqual(len(cells), 5)
        projects = helpers.scratch()
        values = {"model_id": "NBTEST", "projects_dir": projects, "llm_token": "tok-SECRET-123", "llm_endpoint": "https://x",
                  "reviewer_id": "analyst.one", "project": "", "run": "",
                  "jfrog_index_url": "", "concurrency_limit": "4", "token_cap": "40000", "scratch_dir": ""}
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
            shown = run_cell(1, {"HOME = notebook_folder()": "HOME = %r" % helpers.ROOT_DIR})
            self.assertIn("engine", shown)
            self.assertNotIn("tok-SECRET-123", shown, "the token is never printed")
            self.assertIn("14 characters", shown)
            self.assertIn("stand-in", run_cell(2, {"USE_STANDIN = False": "USE_STANDIN = True"}))
            self.assertIn("Run cell 3 first", run_cell(4), "cell 4 before cell 3 says what to do instead of raising NameError")
            self.assertIn("Put the files in", run_cell(3))
            project_dir = os.path.join(projects, "NBTEST", sorted(os.listdir(os.path.join(projects, "NBTEST")))[0])
            shutil.rmtree(os.path.join(project_dir, "Inputs"))
            shutil.copytree(os.path.join(helpers.SAMPLES_DIR, "A_minimal", "Inputs"), os.path.join(project_dir, "Inputs"))
            shown = run_cell(3)
            self.assertIn("Outline of the methodology", shown)
            self.assertIn("Final outputs code proposes:", shown)
            self.assertIn("Read as:", shown)
            self.assertIn("Waiting for a person", space["RESULT"]["message"], "cell 3 stops at the outline for a person")
            import openpyxl
            book_path = os.path.join(space["PATHS"].run_dir, "Output.xlsx")
            book = openpyxl.load_workbook(book_path)
            sheet = book["Chunks_Doc"]
            header = [cell.value for cell in sheet[1]]
            book.save(book_path)
            shown = run_cell(4, {'MODE = "A"': 'MODE = "C"'})
            self.assertIn("confirmed by analyst.one", shown)
            self.assertIn("Final outputs:", shown)
            self.assertIn("link-units", run_cell(4, {'MODE = "A"': 'MODE = "C"'}), "a second run of cell 4 shows the status")
            shown = run_cell(5)
            store = space["verifier"].open_store(space["PATHS"], space["SETTINGS"])
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
