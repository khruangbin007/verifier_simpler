"""test_package_plan.py - R5. A tarball laid out in a way the built-in tests do not expect loses
content quietly: a file with no reader becomes two thousand characters of running text and the
rest of it reaches nothing, while the account still says every line lies inside a unit.

The question asked here picks WHICH EXISTING READER takes such a member. It never reaches the R
tokenizer, the parser, the expression trees or the decoder of stored data, because a model's
reading of code is an assertion about the code and not a parse of it. And there is no reader
that means skip: a member the tool cannot make sense of becomes a unit that says so.
"""
import os
import unittest

import yaml

import helpers
import core
import reading
import review
import runner
import fixture_package
def read(mode, chat=None):
    folder = helpers.scratch()
    path = os.path.join(folder, "oddly_0.1.0.tar.gz")
    with open(path, "wb") as handle:
        handle.write(fixture_package.tarball())
    asking = helpers.asker(chat or helpers.standin()) if mode != "off" else None
    context = helpers.context_for({"package": [path]},
                                  settings=helpers.made_settings({"agentic_reading": mode}), ask=asking)
    result = reading.read_package(context)
    units = [core.to_plain(unit) for unit in result.records["model_units"]]
    return units, result


def a_question():
    folder = helpers.scratch()
    path = os.path.join(folder, "oddly_0.1.0.tar.gz")
    with open(path, "wb") as handle:
        handle.write(fixture_package.tarball())
    files, _ = reading.unpack_package(path, 200 * 1024 * 1024)
    files = reading.strip_top_folder(files)
    placed = {member: reading.built_in_reader(member, files[member]) for member in files}
    digest = core.manifest_digest(files, placed, reading.safe_text, "oddly")
    prompt = core.load_prompt("package-plan")
    return core.package_plan_question(digest, prompt, runner.make_settings({}))


class TheManifestShowsWhereFilesLieAndNothingElse(unittest.TestCase):
    def test_a_member_the_tests_place_is_shown_as_placed_and_carries_no_sample(self):
        question = a_question()
        self.assertIn("R/main.R", question["main_prompt"])
        self.assertNotIn("hours * 9", question["main_prompt"], "a placed member: its content is not shown")

    def test_only_the_unplaced_members_are_asked_about(self):
        question = a_question()
        self.assertEqual(sorted(question["unplaced"]), sorted(fixture_package.UNPLACED))

    def test_an_unplaced_member_is_shown_by_its_first_few_lines_only(self):
        question = a_question()
        self.assertIn("night_premium <- function", question["main_prompt"], "its first lines are what tell it apart")
        self.assertNotIn("total_pay <- function", question["main_prompt"], "and only its first lines")


class TheBadAnswerCorpus(unittest.TestCase):
    def test_every_answer_in_the_corpus_is_handled_as_the_corpus_says(self):
        question = a_question()
        question["unplaced"] = ["tools/calculations.R", "tools/build.notes"]
        with open(os.path.join(helpers.TESTS_DIR, "bad_answers", "package_answers.yaml"), encoding="utf-8") as handle:
            corpus = yaml.safe_load(handle)["answers"]
        self.assertGreaterEqual(len(corpus), 15)
        for case in corpus:
            outcome, answer = review.validate_answer(question, case["text"])
            if case["expected"] == "accepted":
                self.assertEqual(outcome, "accepted", case["name"])
            else:
                self.assertEqual(outcome, "rejected: %s" % core.REJECTION_REASONS[case["expected"]], case["name"])


class NoAnswerCanLeaveAMemberUnread(unittest.TestCase):
    def test_there_is_no_reader_that_means_skip(self):
        self.assertNotIn("skip", core.PACKAGE_READERS)
        self.assertNotIn("ignore", core.PACKAGE_READERS)

    def test_an_answer_that_leaves_a_member_out_is_refused(self):
        question = a_question()
        question["unplaced"] = ["tools/calculations.R", "tools/build.notes"]
        outcome, _ = review.validate_answer(question, '{"readers": {"tools/calculations.R": "r-source"}}')
        self.assertEqual(outcome, "rejected: %s" % core.REJECTION_REASONS[4])

    def test_a_member_sent_to_the_wrong_reader_becomes_a_unit_saying_so(self):
        """The answer is allowed to be wrong. What it may never do is make a file disappear."""
        wrong = lambda system, main: {"answer": helpers.json.dumps(
            {"readers": {path: "help-page" for path in fixture_package.UNPLACED}})}
        units, _ = read("rules", chat=wrong)
        for path in fixture_package.UNPLACED:
            self.assertTrue([unit for unit in units if unit["file"] == path], "%s reached no unit at all" % path)

    def test_the_account_of_the_package_closes_whatever_the_answer_says(self):
        for chat in (helpers.standin(),
                     lambda system, main: {"answer": '{"readers": {"tools/calculations.R": "prose", '
                                                     '"tools/build.notes": "r-source", '
                                                     '"inst/doc/round_up_quarter.Rd": "vignette"}}'}):
            _, result = read("rules", chat=chat)
            account = result.records["content_accounts"][0]
            self.assertTrue(account["closed"], account["where unaccounted"][:6])


class WhatThePlanRecovers(unittest.TestCase):
    def test_r_code_in_a_folder_the_tests_do_not_reach_is_parsed(self):
        """tools/ is in no list the built-in tests use, so its R code arrives as one unit of
        running text cut at two thousand characters. With a plan it is parsed, which is what
        lets it be linked, checked and covered."""
        without, _ = read("off")
        with_plan, _ = read("rules")
        loose = lambda units: [unit for unit in units if unit["file"] == "tools/calculations.R"]
        self.assertEqual([unit["kind"] for unit in loose(without)], ["Other file"])
        kinds = [unit["kind"] for unit in loose(with_plan)]
        self.assertIn("Function", kinds)
        self.assertGreaterEqual(kinds.count("Function"), 3, "all three functions should be parsed")

    def test_a_help_page_outside_its_usual_folder_is_read_as_one(self):
        with_plan, _ = read("rules")
        page = [unit for unit in with_plan if unit["file"] == "inst/doc/round_up_quarter.Rd"]
        self.assertEqual([unit["kind"] for unit in page], ["Help page"])

    def test_a_member_of_no_known_kind_is_still_a_unit(self):
        for mode in ("off", "rules"):
            units, _ = read(mode)
            self.assertTrue([unit for unit in units if unit["file"] == "tools/build.notes"],
                            "a file the tool cannot make sense of is named, never dropped (%s)" % mode)

    def test_nothing_is_asked_when_every_member_is_placed(self):
        spent = []
        counting = lambda system, main: spent.append(1) or {"answer": '{"readers": {}}'}
        members = {path: text for path, text in fixture_package.MEMBERS.items() if path not in fixture_package.UNPLACED}
        folder = helpers.scratch()
        path = os.path.join(folder, "tidy_0.1.0.tar.gz")
        with open(path, "wb") as handle:
            handle.write(fixture_package.tarball(members))
        context = helpers.context_for({"package": [path]},
                                      settings=helpers.made_settings({"agentic_reading": "rules"}),
                                      ask=helpers.asker(counting))
        reading.read_package(context)
        self.assertEqual(spent, [], "a package the tests place entirely costs no call")


class WhenThereIsNoAnswer(unittest.TestCase):
    def test_a_refused_answer_leaves_the_built_in_reading_untouched(self):
        refused = lambda system, main: {"answer": '{"readers": {"R/invented.R": "r-source"}}'}
        with_refusal, result = read("rules", chat=refused)
        without, _ = read("off")
        self.assertEqual([unit["kind"] for unit in with_refusal], [unit["kind"] for unit in without])
        notes = [row["value"] for row in result.records["package_info"][0]["rows"] if row["item"] == "how it was read"]
        self.assertTrue(any("was not available" in note for note in notes), notes)

    def test_the_setting_off_spends_no_call(self):
        spent = []
        counting = lambda system, main: spent.append(1) or {"answer": '{"readers": {}}'}
        units, _ = read("off", chat=counting)
        self.assertEqual(spent, [])


class WhatTheAnalystIsTold(unittest.TestCase):
    def test_every_member_the_plan_placed_is_named_with_its_reader(self):
        _, result = read("rules")
        notes = [row["value"] for row in result.records["package_info"][0]["rows"] if row["item"] == "how it was read"]
        self.assertTrue(any("tools/calculations.R" in note and "r-source" in note for note in notes), notes)
        for note in notes:
            self.assertEqual(helpers.banned_wording(note), "", note)

    def test_the_manifest_shown_to_the_model_is_recorded(self):
        _, result = read("rules")
        digests = result.records["shape_digests"]
        self.assertEqual(len(digests), 1)
        self.assertEqual(digests[0]["kind"], "package")


if __name__ == "__main__":
    unittest.main()
