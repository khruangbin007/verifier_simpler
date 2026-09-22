"""End-to-end tests on the sample projects: sameness of two runs, the human round trip, the
report, the wording of everything an analyst reads, replay, and verification of a run folder."""
import json
import os
import re
import shutil
import unittest

import helpers
import core
import runner
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

    def test_every_assessment_cell_shows_content_not_applicable_or_not_run_yet(self):
        import openpyxl
        workbook = openpyxl.load_workbook(os.path.join(self.paths.outputs_dir, "Output.xlsx"))
        layout = {s["name"]: s for s in runner.load_layout()["sheets"]}
        # the review's own cells, which the two mapping sheets used to hold: on a unit's row each shows
        # content, "Not applicable" or "Not run yet". A sheet's own columns (a reading note, say) may be blank,
        # and so may a row of the map, where a row is a step and not a unit.
        cells = {key for record in runner.open_store(self.paths, self.settings).read("unit_status") for key in (record.get("cells") or {})}
        for name in ("Chunks_Doc", "Chunks_Model"):
            sheet = workbook[name]
            wanted = [i for i, c in enumerate(layout[name]["columns"]) if c["field"] in cells | {"status", "item_ids"}]
            self.assertTrue(wanted, name)
            for row in sheet.iter_rows(min_row=2, values_only=True):
                self.assertTrue(all(row[i] not in (None, "") for i in wanted), "%s row %s" % (name, row[0]))

    def test_the_word_files_are_in_plain_words_and_the_report_holds_every_item_once(self):
        import docx
        items = runner.open_store(self.paths, self.settings).read("flagged_items")
        report = docx.Document(os.path.join(self.paths.outputs_dir, "Validation_Report.docx"))
        problems = []
        for document, label in ((report, "report"),):
            texts = [p.text for p in document.paragraphs] + [c.text for t in document.tables for r in t.rows for c in r.cells]
            for text in texts:
                problems += self.problems_in(text, label)
        self.assertEqual(problems, [])
        headings = [p.text for p in report.paragraphs if p.style.name == "Heading 3"]
        self.assertEqual(sorted(h.split(" - ")[0] for h in headings), sorted(i["item_id"] for i in items))
        self.assertIn("%d of %d flagged items are still open." % (len(items), len(items)), [p.text for p in report.paragraphs])

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

    def test_a_renamed_sorted_workbook_with_an_added_sheet_is_read_by_item_id(self):
        self.upload({self.items[0]: ("requires ACTION", "A. Reviewer", "Validator", "To be corrected."),
                     self.items[1]: ("No action needed", "A. Reviewer", "Validator", "Seen and accepted.")}, shuffle=True, extra_sheet=True)
        self.record()
        recorded = {d["item_id"]: d for d in self.store.read("determinations")}
        self.assertEqual(recorded[self.items[0]]["decision"], "Requires action")
        self.assertEqual(recorded[self.items[0]]["recorded_by"], "analyst.one")
        self.assertEqual(len(recorded), 2)
        manifest = self.store.read("run_manifest")[0]
        self.assertEqual(len(manifest.get("last_workbook_sha256", "")), 64,
                         "the returned workbook is recorded by its fingerprint; its bytes are not copied")
        self.assertTrue(core.verify_chain(self.store.read("determinations"))[0])

    def test_a_person_may_use_the_words_that_verifier_itself_never_uses(self):
        """Rating and classifying are for people: what a reviewer types is kept and shown exactly as typed."""
        import openpyxl
        rationale = "This is a " + "maj" + "or " + "find" + "ing under our policy; to be corrected."
        self.upload({self.items[0]: ("Requires action", "A. Reviewer", "Validator", rationale)})
        self.record()
        self.assertEqual(self.store.read("determinations")[0]["rationale"], rationale)
        sheet = openpyxl.load_workbook(os.path.join(self.paths.outputs_dir, "Output.xlsx"))["Flagged_Items"]
        column = [c.value for c in sheet[1]].index("Rationale")
        shown = [row[column] for row in sheet.iter_rows(min_row=2, values_only=True) if row[0] == self.items[0]]
        self.assertEqual(shown, [rationale])

    def test_incomplete_unknown_and_duplicated_rows_are_reported_and_not_recorded(self):
        self.upload({self.items[0]: ("No action needed", "", "", ""), "RI-0000-99999": ("Requires action", "X", "Y", "Z")})
        _, messages = self.record()
        self.assertEqual(self.store.read("determinations"), [])
        self.assertTrue(any("needs a reviewer, a role and a rationale" in m for m in messages))
        self.assertTrue(any("belongs to no flagged item" in m for m in messages))

    def test_a_changed_decision_appends_and_a_cleared_one_is_recorded_as_withdrawn(self):
        self.upload({self.items[0]: ("Requires action", "A. Reviewer", "Validator", "First view.")})
        self.record()
        self.upload({self.items[0]: ("No action needed", "A. Reviewer", "Validator", "Second view.")})
        self.record()
        self.upload({self.items[0]: ("", "", "", "")})
        self.record()
        decisions = [d["decision"] for d in self.store.read("determinations")]
        self.assertEqual(decisions, ["Requires action", "No action needed", core.DECISION_WITHDRAWN])
        rows = {r["item_id"]: r for r in runner.rows_flagged(self.store)}
        self.assertEqual(rows[self.items[0]]["status"], core.ITEM_OPEN)
        tampered = self.store.read("determinations")
        tampered[1]["rationale"] = "changed afterwards"
        self.assertEqual(core.verify_chain(tampered)[:2], (False, 1))

    def test_a_workbook_of_another_run_and_an_xls_file_are_refused_in_plain_words(self):
        other, _, _ = helpers.run_sample("D_dosing", chat=standin_chat.chat)
        shutil.copy(os.path.join(other.outputs_dir, "Output.xlsx"), os.path.join(self.paths.outputs_dir, "From elsewhere.xlsx"))
        with open(os.path.join(self.paths.outputs_dir, "Old.xls"), "wb") as handle:
            handle.write(b"\xd0\xcf\x11\xe0 old format")
        result = runner.run_pipeline(self.paths, self.settings, chat=standin_chat.chat, determinations=True)
        messages = [m for r in self.store.read("step_records") if r["name"] == "record-determinations" for m in r["messages"]]
        self.assertTrue(any("belongs to another run" in m for m in messages))
        self.assertTrue(any(".xls format" in m for m in messages))
        self.assertEqual(self.store.read("determinations"), [])

    def test_an_edited_workbook_is_never_overwritten_before_it_has_been_read_in(self):
        self.upload({self.items[0]: ("Requires action", "A. Reviewer", "Validator", "Work in progress.")}, name="Output.xlsx")
        edited = runner.file_sha256(os.path.join(self.paths.outputs_dir, "Output.xlsx"))
        self.assertFalse(runner.rebuild_outputs(self.store, self.paths, self.settings, ""))
        self.assertEqual(runner.file_sha256(os.path.join(self.paths.outputs_dir, "Output.xlsx")), edited)
        self.record()
        self.assertEqual(len(self.store.read("determinations")), 1)
        self.assertNotEqual(runner.file_sha256(os.path.join(self.paths.outputs_dir, "Output.xlsx")), edited)


class VerifyingARunFolder(unittest.TestCase):
    def setUp(self):
        self.paths, self.settings, _ = helpers.run_sample("A_minimal", chat=standin_chat.chat)

    def not_confirmed(self):
        return [what for what, verdict, _ in runner.verify_evidence_pack(self.paths, self.settings) if verdict != "Confirmed"]

    def rewrite(self, kind, change):
        """Tamper with the records of one kind inside the pack's single records file."""
        path = os.path.join(self.paths.audit_dir, runner.RECORDS_FILE)
        with open(path, encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        mine = [line["record"] for line in lines if line["kind"] == kind]
        changed = iter(change(mine))
        kept = []
        for line in lines:
            if line["kind"] != kind:
                kept.append(line)
        kept += [{"kind": kind, "record": record} for record in changed]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("".join(json.dumps(line, sort_keys=True) + "\n" for line in kept))

    def test_an_untouched_run_folder_is_confirmed_on_every_line(self):
        self.assertEqual(self.not_confirmed(), [])

    def test_a_changed_input_byte_is_detected(self):
        manifest = runner.open_store(self.paths, self.settings).read("run_manifest")[0]
        path = os.path.join(self.paths.inputs_dir, manifest["inputs"][0]["file"])
        with open(path, "ab") as handle:
            handle.write(b" ")
        self.assertIn("Input files have the recorded fingerprints", self.not_confirmed())

    def test_a_token_inside_a_compressed_file_is_found(self):
        """The call log is gzip and the workbook is a ZIP. A token written into either would be
        invisible to a search of the raw bytes; the check looks inside."""
        import gzip
        live = runner.LiveValues()
        live.update("https://x", "tok-PLANTED-SECRET-9x8y7z", "u1")
        def token_line():
            return [verdict for what, verdict, _ in runner.verify_evidence_pack(self.paths, self.settings, live=live)
                    if what.startswith("No access token")][0]
        self.assertEqual(token_line(), "Confirmed")
        path = os.path.join(self.paths.audit_dir, runner.CALLS_FILE)
        with open(path, "ab") as raw, gzip.GzipFile(fileobj=raw, mode="ab", mtime=0) as packed:
            packed.write(b'{"answer": "Bearer tok-PLANTED-SECRET-9x8y7z"}\n')
        self.assertEqual(token_line(), "Not confirmed")

    def test_a_changed_chunk_a_broken_chain_and_a_deleted_status_are_each_detected(self):
        self.rewrite("chunks_canon", lambda records: [dict(records[0], content_hash="0" * 64)] + records[1:])
        self.assertIn("Re-reading the inputs gives the recorded content hashes (chunks_canon)", self.not_confirmed())
        self.rewrite("graph_ledger", lambda records: records[:5] + records[6:])
        self.assertIn("The graph ledger chain verifies", self.not_confirmed())
        self.rewrite("unit_status", lambda records: records[1:])
        self.assertIn("Every unit has one status; units that are not clean and flagged items match", self.not_confirmed())


if __name__ == "__main__":
    unittest.main()
