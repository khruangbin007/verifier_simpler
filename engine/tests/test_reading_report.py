"""test_reading_report.py - the sign-off bar has to be able to FAIL, or it is decoration.

`tools/reading_report.py` says whether guided reading has earned the right to be the default.
Its four tests are what stands between a measurement and a decision, so each is fed a result
that should trip it. A bar that passes everything tells the owner nothing.
"""
import os
import sys
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.ROOT_DIR, "tools"))
import reading_report


def a_result(**changes):
    """A sample's measurement, clean unless a test spoils it on purpose."""
    base = {"phrases": 8, "gold": 8, "levels": 4, "wanted": 4, "chained": 14, "units": 14,
            "calls": 1, "refused": 0, "fell_back": 0, "tokens": 1400, "closed": True, "open_files": [],
            "added": 0, "lost": 0}
    base.update(changes)
    return base


def a_table(spoil=None):
    """Every sample in both modes, clean, with any (sample, mode) replaced."""
    found = {}
    for sample in reading_report.HARD + reading_report.SETTLED:
        for mode in reading_report.MODES:
            found[(sample, mode)] = a_result(calls=0 if mode == "off" else 1)
    found.update(spoil or {})
    return found


def held(found):
    return [ok for ok, _ in reading_report.bar(found, reading_report.HARD + reading_report.SETTLED)]


class TheBarPassesACleanRun(unittest.TestCase):
    def test_a_clean_table_holds_all_four(self):
        self.assertEqual(held(a_table()), [True, True, True, True])


class TheBarCatchesEachThingItClaimsTo(unittest.TestCase):
    def test_it_catches_a_word_lost_anywhere(self):
        found = a_table({("H_twocolumn", "rules"): a_result(lost=2, closed=False, open_files=["a.pdf"])})
        self.assertEqual(held(found)[0], False, "a lost word must trip the first test")

    def test_it_catches_a_word_added_anywhere(self):
        found = a_table({("A_minimal", "off"): a_result(added=1, calls=0)})
        self.assertEqual(held(found)[0], False, "an added word must trip the first test, in either mode")

    def test_it_catches_guidance_reading_fewer_phrases_than_no_guidance(self):
        found = a_table({("G_schema", "rules"): a_result(phrases=6)})
        self.assertEqual(held(found)[1], False)

    def test_it_catches_guidance_placing_fewer_headings(self):
        found = a_table({("G_schema", "rules"): a_result(levels=2)})
        self.assertEqual(held(found)[1], False)

    def test_it_catches_guidance_carrying_a_chain_onto_fewer_units(self):
        found = a_table({("I_wordtraps", "rules"): a_result(chained=9)})
        self.assertEqual(held(found)[1], False)

    def test_it_catches_a_settled_sample_moving(self):
        found = a_table({("F_capital", "rules"): a_result(units=13)})
        self.assertEqual(held(found)[2], False, "a settled sample must not move when guidance is on")

    def test_it_catches_answers_being_refused_and_retried(self):
        found = a_table({("D_dosing", "rules"): a_result(calls=2, refused=1)})
        self.assertEqual(held(found)[3], False, "a refused answer means the prompt and the validator disagree")

    def test_it_catches_guidance_that_silently_never_happened(self):
        """The case a dress rehearsal found the first draft passing: every answer refused, the
        reading fell back to the built-in rules, and every other measure looked perfect."""
        found = a_table({("F_capital", "rules"): a_result(calls=3, refused=3, fell_back=1)})
        tests = reading_report.bar(found, reading_report.HARD + reading_report.SETTLED)
        self.assertEqual(tests[3][0], False)
        self.assertIn("guidance did not happen", tests[3][1])

    def test_many_calls_that_were_all_accepted_are_not_a_failure(self):
        found = a_table({("G_schema", "rules"): a_result(calls=5, refused=0)})
        self.assertEqual(held(found)[3], True, "the bar counts refusals, not calls")


class WhatTheReportSaysOutLoud(unittest.TestCase):
    def test_a_stand_in_run_says_on_its_own_front_page_that_it_is_not_evidence(self):
        lines = reading_report.report_lines(a_table(), reading_report.HARD, "the stand-in")
        front = "\n".join(lines[:14])
        self.assertIn("not evidence", front)
        self.assertIn("not met", front)

    def test_a_live_run_carries_no_such_warning(self):
        lines = reading_report.report_lines(a_table(), reading_report.HARD, "the real model")
        self.assertNotIn("not evidence", "\n".join(lines))

    def test_the_report_names_what_it_does_not_measure(self):
        text = "\n".join(reading_report.report_lines(a_table(), reading_report.HARD, "the real model"))
        self.assertIn("rules_and_spans", text)
        self.assertIn("R4 was not built", text)

    def test_nothing_the_report_writes_uses_banned_wording(self):
        for label in ("the stand-in", "the real model"):
            for line in reading_report.report_lines(a_table(), reading_report.HARD, label):
                self.assertEqual(helpers.banned_wording(line), "", line)


if __name__ == "__main__":
    unittest.main()
