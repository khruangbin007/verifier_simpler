"""test_run_goes_on.py - R2 says nothing stops a runner. Until 21 September 2026 that held for the
reading steps only: run_step called a step function with nothing around it, so a fault inside ANY
step ended the run with a traceback, no Output.xlsx, and every step that had worked thrown away.

Now a step that cannot finish is written down and the run goes on. Three things are held here,
and the third matters as much as the first: a PAUSE is not a failure. A pause is how a run waits
for a person or for a fresh token, and catching it would turn a run that is waiting into a run
that has silently skipped what it was waiting for.
"""
import glob
import os
import unittest

import helpers
import core
import runner
import standin_chat

BROKEN = "review.build_graph"


def a_run(replace=None):
    """A_minimal run to the end of its automatic steps, with one step function replaced."""
    real = runner.STEP_FUNCTIONS[BROKEN]
    if replace is not None:
        runner.STEP_FUNCTIONS[BROKEN] = replace
    try:
        projects = helpers.scratch()
        helpers.copy_sample("A_minimal", projects, "GOESON", "2026-09-21")
        settings = runner.make_settings({"require_outline_confirmation": False})
        paths = runner.open_run(projects, "GOESON", "2026-09-21", scratch_root=helpers.scratch())
        outcome = runner.run_pipeline(paths, settings, chat=standin_chat.chat_well_behaved)
        return outcome, paths, runner.open_store(paths, settings).read("step_records")
    finally:
        runner.STEP_FUNCTIONS[BROKEN] = real


def fails(context):
    raise KeyError("a key the step expected and did not find")


class AStepThatFailsDoesNotStopTheRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outcome, cls.paths, cls.records = a_run(fails)
        cls.clean_outcome, _, cls.clean_records = a_run()

    def test_the_run_reaches_the_same_end_as_a_run_where_nothing_failed(self):
        self.assertEqual(self.outcome["state"], self.clean_outcome["state"])
        self.assertEqual([record["step_id"] for record in self.records],
                         [record["step_id"] for record in self.clean_records],
                         "every step still runs and is recorded")

    def test_the_step_is_recorded_as_not_finished_and_only_that_step(self):
        unfinished = [record["step_id"] for record in self.records
                      if (record.get("counts") or {}).get("step did not finish")]
        self.assertEqual(unfinished, ["05"])

    def test_the_workbook_is_still_written_with_everything_that_did_work(self):
        books = glob.glob(os.path.join(self.paths.run_dir, "**", "Output.xlsx"), recursive=True)
        self.assertTrue(books, "an analyst must still get a workbook")
        import openpyxl
        sheet = openpyxl.load_workbook(books[0], read_only=True)["Chunks_Canon"]
        self.assertGreater(sheet.max_row, 1, "the reading done before the failure is kept")

    def test_the_analyst_is_told_in_plain_words(self):
        said = [record for record in self.records if record["step_id"] == "05"][0]["messages"][0]
        self.assertIn("Step 05 (build-graph) could not finish", said)
        self.assertIn("The steps after it ran on what there was", said)
        self.assertEqual(core.has_banned_wording(said), "", said)

    def test_the_details_are_kept_for_a_maintainer_and_not_put_in_the_evidence_pack(self):
        kept = glob.glob(os.path.join(self.paths.local_dir, "work", "step_05_did_not_finish.txt"))
        self.assertEqual(len(kept), 1)
        with open(kept[0], encoding="utf-8") as handle:
            self.assertIn("KeyError", handle.read())
        in_pack = glob.glob(os.path.join(self.paths.run_dir, "**", "step_*_did_not_finish.txt"), recursive=True)
        self.assertEqual([path for path in in_pack if not path.startswith(self.paths.local_dir)], [],
                         "a fault of the tool's is not evidence about the model under review")


class APauseIsNotAFailure(unittest.TestCase):
    def test_a_pause_raised_inside_a_step_still_pauses_the_run(self):
        def pauses(context):
            raise runner.RunPaused("Paste a fresh token, then run the cell again; no call will be repeated.")
        outcome, _, records = a_run(pauses)
        self.assertEqual(outcome["state"], "paused")
        self.assertIn("fresh token", outcome["message"])
        self.assertFalse([record for record in records if (record.get("counts") or {}).get("step did not finish")],
                         "a pause must never be written down as a step that did not finish")
        self.assertNotIn("05", [record["step_id"] for record in records], "the paused step is not recorded as done")


if __name__ == "__main__":
    unittest.main()
