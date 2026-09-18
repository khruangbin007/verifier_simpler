"""The manual, the skills and the release manifest must agree with the code (plan, Phases 11 and 12)."""
import os
import unittest

import helpers
import build_manual
import check_docs
import make_release_manifest


class ManualAndCode(unittest.TestCase):
    def test_check_docs_reports_nothing(self):
        self.assertEqual(check_docs.problems(), [])

    def test_the_built_manual_is_the_one_the_sources_give(self):
        with open(os.path.join(helpers.ROOT_DIR, "docs", "AIVA_User_Manual.md"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), build_manual.assemble(), "run python tools/build_manual.py")
        self.assertTrue(os.path.exists(os.path.join(helpers.ROOT_DIR, "docs", "AIVA_User_Manual.docx")))

    def test_a_name_that_does_not_exist_is_reported(self):
        engine, tests = check_docs.engine_names(), check_docs.test_names()
        self.assertIs(check_docs.reference_exists("aiva3_mapping.judge_links", engine, tests, set()), True)
        self.assertIs(check_docs.reference_exists("aiva3_mapping.no_such_function", engine, tests, set()), False)
        self.assertIs(check_docs.reference_exists("cell 19", engine, tests, set()), False)
        self.assertIs(check_docs.reference_exists("test_aiva4_checks.ValueRule.test_the_table_of_the_rule", engine, tests, set()), True)
        self.assertIsNone(check_docs.reference_exists("rho_a", engine, tests, set()))


class Release(unittest.TestCase):
    def test_the_release_manifest_matches_the_files(self):
        self.assertEqual(make_release_manifest.main(["--check"]), 0, "run python tools/make_release_manifest.py as the last step of a change")


    def test_every_run_names_exactly_the_engine_files_that_produced_it(self):
        import json
        import aiva5_run_report as run
        paths, settings, _ = helpers.run_sample("A_minimal", stop_after="01")
        recorded = run.open_store(paths, settings).read("run_manifest")[0]["engine_files"]
        with open(os.path.join(helpers.ROOT_DIR, "docs", "release_manifest.json"), encoding="utf-8") as handle:
            released = {name: digest for name, digest in json.load(handle)["files"].items() if name.startswith("engine/")}
        self.assertEqual(recorded, released)


if __name__ == "__main__":
    unittest.main()
