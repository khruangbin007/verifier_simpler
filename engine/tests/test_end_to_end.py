"""End-to-end tests on the sample projects: sameness of two runs, the human round trip, the
report, the wording of everything an analyst reads, replay, and verification of a run folder."""
import json
import os
import re
import shutil
import unittest

import helpers
import verifier
core = runner = verifier   # the engine is one module now
import standin_chat

AUDIT_KINDS = ("chunks_canon", "chunks_doc", "model_units", "parameter_tables", "candidates", "search_records", "graph_ledger",
               "math_checks", "value_checks", "rule_checks", "package_doc_checks", "unit_status", "flagged_items", "coverage")


def snapshot(paths, settings):
    store = runner.open_store(paths, settings)
    text = json.dumps(helpers.audit_snapshot(store, AUDIT_KINDS), sort_keys=True)
    return re.sub(r"Run_\d{4}-\d{2}-\d{2}_\d{4}[a-z]?|RI-\d{4}-\d{2}-\d{2}_\d{4}[a-z]?", "RUN", text)


def own_words(text):
    return re.sub(r"\u201c.*?\u201d", "", str(text), flags=re.S)


class TwoRunsAreTheSame(unittest.TestCase):
    def test_same_inputs_give_the_same_audit_records_and_the_same_graph_version(self):
        first_paths, settings, _ = helpers.run_sample("A_minimal", chat=standin_chat.chat)
        second_paths, _, _ = helpers.run_sample("A_minimal", chat=standin_chat.chat)
        self.assertEqual(snapshot(first_paths, settings), snapshot(second_paths, settings))
        ids = [runner.run_identity(runner.open_store(p, settings), p)["graph_version_id"] for p in (first_paths, second_paths)]
        self.assertEqual(ids[0], ids[1])

    def test_replaying_the_recorded_answers_reproduces_graph_statuses_and_items(self):
        paths, settings, _ = helpers.run_sample("F_capital_known", chat=standin_chat.chat)
        calls = runner.open_store(paths, settings).read_calls()
        replayed, _, _ = helpers.run_sample("F_capital_known", chat=runner.replay_chat(calls))
        self.assertEqual(snapshot(paths, settings), snapshot(replayed, settings))


class WhatAnAnalystReads(unittest.TestCase):
    """The dynamic wording lint: every cell of Output.xlsx and every paragraph of the Word files."""
    @classmethod
    def setUpClass(cls):
        cls.paths, cls.settings, _ = helpers.run_sample("F_capital_known", chat=standin_chat.chat)

    def problems_in(self, text, where):
        mine = own_words(text)
        found = []
        if core.has_banned_wording(mine):
            found.append("%s: the word '%s'" % (where, core.has_banned_wording(mine)))
        if runner.PYTHON_TRACES.search(mine):
            found.append("%s: a trace of Python in %r" % (where, mine[:80]))
        return found

    def test_every_cell_of_the_workbook_is_in_plain_words(self):
        import openpyxl
        workbook = openpyxl.load_workbook(os.path.join(self.paths.outputs_dir, "Output.xlsx"))
        layout = runner.load_layout()
        input_columns = {(s["name"], c["header"]) for s in layout["sheets"] for c in s["columns"] if c.get("input_text")}
        problems, withheld = [], 0
        for sheet in workbook.worksheets:
            header = [cell.value for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2):
                for name, cell in zip(header, row):
                    if cell.value is None or (sheet.title, name) in input_columns:
                        continue
                    withheld += cell.value == runner.CELL_WITHHELD
                    self.assertFalse(isinstance(cell.value, float) and cell.value == int(cell.value), "%s %s: a whole number shown with a decimal point" % (sheet.title, cell.coordinate))
                    problems += self.problems_in(cell.value, "%s %s" % (sheet.title, cell.coordinate))
        self.assertEqual(problems, [])
        self.assertEqual(withheld, 0, "cells whose text had to be withheld")

    def test_coverage_is_counted_from_the_map_and_from_the_sheets(self):
        """Mapping_Coverage is read off the map: a row per final output and a row per corner. Its numbers
        must be the map's and the Chunks sheets' own, and each corner's covered and not covered must
        account for every unit it counts."""
        import openpyxl
        workbook = openpyxl.load_workbook(os.path.join(self.paths.outputs_dir, "Output.xlsx"))
        read = lambda name: [dict(zip([c.value for c in workbook[name][1]], [c.value for c in row]))
                             for row in workbook[name].iter_rows(min_row=2)]
        coverage, mapped = read("Mapping_Coverage"), read("Model_Implementation_Map")
        store = runner.open_store(self.paths, self.settings)
        missing = runner.not_on_the_map(store, runner.implementation_map(store, self.settings), self.settings)
        branches = {}
        for row in mapped:
            branches.setdefault(str(row["MapID1"]), []).append(row)
        for row in coverage:
            branch = row["What is counted"].split(" ")[0]
            if branch.isdigit():
                steps = branches[branch]
                self.assertEqual(row["In total"], len(steps), branch)
                self.assertEqual(row["Deepest level"], max(step["Level"] for step in steps), branch)
                self.assertEqual(row["Covered"] + row["Not covered"], len(steps), branch)
        corners = {row["What is counted"]: row for row in coverage}
        model = corners["Model units (one row each on Chunks_Model)"]
        self.assertEqual(model["In total"], len(read("Chunks_Model")))
        self.assertEqual(model["Covered"] + model["Not covered"], model["In total"], "every model unit is counted once")
        self.assertEqual(model["Not covered"], len(missing["model_units"]))
        self.assertEqual(corners["Methodology passages"]["Not covered"], len(missing["methodology"]))
        self.assertEqual(corners["Documentation passages"]["Not covered"], len(missing["documentation"]))

    def setUp(self):
        self.paths, self.settings, _ = helpers.run_sample("A_minimal", chat=standin_chat.chat, settings={"reviewer_id": "analyst.one"})
        self.store = runner.open_store(self.paths, self.settings)
        self.items = [i["item_id"] for i in self.store.read("flagged_items")]

    def upload(self, rows, name="Output (1).xlsx", shuffle=False, extra_sheet=False, source=None):
        import openpyxl
        workbook = openpyxl.load_workbook(source or os.path.join(self.paths.outputs_dir, "Output.xlsx"))
        sheet = workbook["Flagged_Items"]
        column = {cell.value: cell.column for cell in sheet[1]}
        by_id = {sheet.cell(row=r, column=column["Item id"]).value: r for r in range(2, sheet.max_row + 1)}
        for item_id, values in rows.items():
            target = by_id.get(item_id) or sheet.max_row + 1
            sheet.cell(row=target, column=column["Item id"], value=item_id)
            for field, value in zip(("Decision", "Reviewer", "Role", "Rationale"), values):
                sheet.cell(row=target, column=column[field]).value = value or None
        if shuffle:                                   # a reviewer sorted the sheet: rows change place, item ids stay with their cells
            body = [[c.value for c in row] for row in sheet.iter_rows(min_row=2)]
            for number, values in enumerate(reversed(body), start=2):
                for position, value in enumerate(values, start=1):
                    sheet.cell(row=number, column=position).value = value      # cell(value=None) would leave the old value
        if extra_sheet:
            workbook.create_sheet("My notes")["A1"] = "typed by the reviewer"
        workbook.save(os.path.join(self.paths.outputs_dir, name))

    def record(self):
        result = runner.run_pipeline(self.paths, self.settings, chat=standin_chat.chat, determinations=True)
        self.assertEqual(sorted(os.listdir(self.paths.run_dir)), ["Output.xlsx", "Validation_Report.docx", "_audit"],
                         "the run folder holds the two deliverables and the record, nothing else")
        self.assertEqual(sorted(os.listdir(self.paths.audit_dir)), ["calls.jsonl.gz", "manifest.json", "records.jsonl"],
                         "the record is exactly three files")
        messages = [m for r in self.store.read("step_records") if r["name"] == "record-determinations" for m in r["messages"]]
        return result, messages

class VerifyingARunFolder(unittest.TestCase):
    def setUp(self):
        self.paths, self.settings, _ = helpers.run_sample("A_minimal", chat=standin_chat.chat)

    def not_confirmed(self):
        return [what for what, verdict, _ in runner.verify_evidence_pack(self.paths, self.settings) if verdict != "Confirmed"]

    def test_an_untouched_run_folder_is_confirmed_on_every_line(self):
        self.assertEqual(self.not_confirmed(), [])

    def test_a_changed_input_byte_is_detected(self):
        manifest = runner.open_store(self.paths, self.settings).read("run_manifest")[0]
        path = os.path.join(self.paths.inputs_dir, manifest["inputs"][0]["file"])
        with open(path, "ab") as handle:
            handle.write(b" ")
        self.assertIn("Input files have the recorded fingerprints", self.not_confirmed())

    def test_a_token_inside_the_audit_workbook_is_found(self):
        """The record of a run is a workbook, which is a ZIP: a token written into it would be invisible
        to a search of the raw bytes. The check looks inside."""
        live = runner.LiveValues()
        live.update("https://x", "tok-PLANTED-SECRET-9x8y7z", "u1")
        def token_line():
            return [verdict for what, verdict, _ in runner.verify_evidence_pack(self.paths, self.settings, live)
                    if what.startswith("No access token")][0]
        self.assertEqual(token_line(), "Confirmed")
        import openpyxl
        path = os.path.join(self.paths.audit_dir, runner.AUDIT_FILE)
        book = openpyxl.load_workbook(path)
        book["Records"].append(["planted", 1, 1, '{"answer": "Bearer tok-PLANTED-SECRET-9x8y7z"}'])
        book.save(path)
        self.assertEqual(token_line(), "Not confirmed")

