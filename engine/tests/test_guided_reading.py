"""test_guided_reading.py - the first phase in which a reading step asks a question.

The claim R3 has to earn is narrow and absolute: guidance may change how a file is SLICED and
may never change what it SAYS. These tests hold that line from four directions.

  1. the corpus    every way an answer can be wrong is refused for the right reason
  2. the property  for ANY valid answer, on random shapes, the content account still closes
  3. the order     the analyst beats the tool beats what code proved beats the model beats a guess
  4. the fallback  a refused, failed or absent answer leaves the built-in reading untouched
"""
import random
import unittest

import yaml

import helpers
import verifier
core = reading = review = runner = verifier   # the engine is one module now
SHAPE = """<?xml version="1.0"?>
<rules>
  <ruleblock idx="1."><blockcaption>Loan periods</blockcaption>
    <statementbody>A standard loan runs for fourteen days.</statementbody>
    <statementbody>A short loan runs for two days.</statementbody></ruleblock>
  <ruleblock idx="2."><blockcaption>Fines</blockcaption>
    <statementbody>The fine is capped at eight units.</statementbody></ruleblock>
</rules>"""


def a_question(text=SHAPE, rules=None):
    settings = runner.make_settings({})
    rules = rules or reading.load_tag_rules()
    root = reading.parse_markup(text, "s.xml", [], False)
    digest = core.markup_digest(root, rules, "s.xml")
    prompt = core.load_prompt("slice-rules")
    return core.slice_rules_question(digest, rules, prompt, settings), root, rules


class TheDigestShowsShapeAndNotTheDocument(unittest.TestCase):
    def test_the_digest_carries_counts_and_places_for_every_tag_in_the_file(self):
        _, root, rules = a_question()
        digest = core.markup_digest(root, rules, "s.xml")
        tags = {row["tag"] for row in digest["tags"]}
        self.assertEqual(tags, {"rules", "ruleblock", "blockcaption", "statementbody"})
        block = [row for row in digest["tags"] if row["tag"] == "blockcaption"][0]
        self.assertEqual(block["count"], 2)
        self.assertEqual(block["first_child"], 2, "a heading opens the block it names")

    def test_no_sample_in_the_digest_runs_past_its_limit(self):
        _, root, rules = a_question()
        for row in core.markup_digest(root, rules, "s.xml")["tags"]:
            self.assertLessEqual(len(row["samples"]), core.DIGEST_SAMPLES)
            for sample in row["samples"]:
                self.assertLessEqual(len(sample), core.DIGEST_SAMPLE_CHARS)

    def test_the_question_id_changes_when_the_prompt_changes(self):
        """The reader's procedure and prohibitions are the first thing in the prompt's system
        half, so a changed contract is a new prompt version and a new question id."""
        settings = runner.make_settings({})
        _, root, rules = a_question()
        digest = core.markup_digest(root, rules, "s.xml")
        prompt = core.load_prompt("slice-rules")
        self.assertIn("THE READER NEVER", prompt["system"], "the contract lives in the prompt now")
        plain = core.slice_rules_question(digest, rules, prompt, settings)
        changed = dict(prompt, system=prompt["system"] + "\n- never lose a word", version="VERSION 99")
        again = core.slice_rules_question(digest, rules, changed, settings)
        self.assertNotEqual(plain["question_id"], again["question_id"])

class TheBadAnswerCorpus(unittest.TestCase):
    def test_every_answer_in_the_corpus_is_handled_as_the_corpus_says(self):
        import verifier as core
        question, _, _ = a_question()
        question["tags_shown"] = ["rules", "ruleblock", "blockcaption", "statementbody"]
        question["holds_other_tags"] = {"rules": True, "ruleblock": True, "blockcaption": False, "statementbody": False}
        with open(helpers.os.path.join(helpers.TESTS_DIR, "bad_answers", "slice_answers.yaml"), encoding="utf-8") as handle:
            corpus = yaml.safe_load(handle)["answers"]
        self.assertGreaterEqual(len(corpus), 20, "the corpus should cover every way an answer can be wrong")
        for case in corpus:
            outcome, answer = review.validate_answer(question, case["text"])
            if case["expected"] == "accepted":
                self.assertEqual(outcome, "accepted", case["name"])
                self.assertIsInstance(answer, dict, case["name"])
            else:
                self.assertEqual(outcome, "rejected: %s" % core.REJECTION_REASONS[case["expected"]], case["name"])
                self.assertIsNone(answer, case["name"])


class NoAnswerCanChangeWhatAFileSays(unittest.TestCase):
    """The property, over random valid answers. A wrong label is the worst that can happen."""

    def test_any_valid_answer_leaves_the_content_account_closed(self):
        chance = random.Random(20260918)
        tags = ["rules", "ruleblock", "blockcaption", "statementbody"]
        for _ in range(40):
            holds = {"rules": True, "ruleblock": True, "blockcaption": False, "statementbody": False}
            allowed = lambda tag: [f for f in core.SLICE_FAMILIES
                                   if not (holds[tag] and f in ("paragraph", "list_item"))]
            answer = {"families": {tag: chance.choice(allowed(tag)) for tag in tags}, "levels": {}, "why": {}}
            for tag, family in answer["families"].items():
                if family == "heading":
                    answer["levels"][tag] = chance.randint(1, 9)
            chat = lambda system, main, answer=answer: {"answer": helpers.json.dumps(answer)}
            found = helpers.chunks_of("s.xml", SHAPE, chat=chat, settings={"agentic_reading": "rules"})
            account = found[1].records["content_accounts"][0]
            self.assertEqual(account["injected"], 0,
                             "a valid answer added words: %s from %s" % (account["what injected"], answer["families"]))
            self.assertEqual(account["unaccounted"], 0,
                             "a valid answer lost words: %s from %s" % (account["what unaccounted"], answer["families"]))


class TheOrderOfPrecedence(unittest.TestCase):
    def test_the_model_never_overrides_the_analyst(self):
        rules = {"shipped_tags": [], "family_of": {}}
        answer = {"families": {"statementbody": "heading"}}
        families, _, _ = core.overlay_from_answer(answer, rules, {"statementbody"})
        self.assertEqual(families, {}, "what the analyst wrote in Inputs/tag_rules.yaml wins")

    def test_the_model_never_overrides_a_tag_verifier_ships(self):
        rules = {"shipped_tags": ["para"], "family_of": {}}
        families, _, _ = core.overlay_from_answer({"families": {"para": "heading"}}, rules, set())
        self.assertEqual(families, {}, "a schema the tool already knows is read exactly as before")

    def test_the_model_never_overrides_a_table_whose_rows_were_counted(self):
        rules = {"shipped_tags": [], "family_of": {}}
        answer = {"families": {"gridcell": "paragraph", "blockcaption": "heading"}}
        families, _, _ = core.overlay_from_answer(answer, rules, set(), {"gridcell": "cell"})
        self.assertNotIn("gridcell", families, "a family proved by counting is not a guess to overturn")
        self.assertIn("blockcaption", families, "but the model does speak where code only guessed")

    def test_a_level_is_kept_only_for_a_tag_the_answer_called_a_heading(self):
        rules = {"shipped_tags": [], "family_of": {}}
        answer = {"families": {"a": "heading", "b": "paragraph"}, "levels": {"a": 3, "b": 2}}
        _, levels, _ = core.overlay_from_answer(answer, rules, set())
        self.assertEqual(levels, {"a": 3})


class WhenThereIsNoAnswer(unittest.TestCase):
    """R3: the worst case of a guided reading is the reading the tool does without one."""

    def baseline(self):
        return helpers.chunks_of("s.xml", SHAPE)[0]

    def test_a_refused_answer_falls_back_to_the_built_in_reading(self):
        refused = lambda system, main: {"answer": '{"families": {"a-tag-nobody-showed": "heading"}}'}
        found, result = helpers.chunks_of("s.xml", SHAPE, chat=refused, settings={"agentic_reading": "rules"})
        self.assertEqual([unit["text"] for unit in found], [unit["text"] for unit in self.baseline()])
        notes = [row["value"] for row in result.records["info_rows"] if "reading note" in row["item"]]
        self.assertTrue(any("was not available" in note for note in notes),
                        "the analyst is told the built-in rules read it")

    def test_an_absent_model_changes_nothing_at_all(self):
        found, _ = helpers.chunks_of("s.xml", SHAPE, settings={"agentic_reading": "rules"})
        self.assertEqual([unit["text"] for unit in found], [unit["text"] for unit in self.baseline()])

    def test_the_setting_off_spends_no_call_and_reads_as_before(self):
        spent = []
        counting = lambda system, main: spent.append(1) or {"answer": '{"families": {}}'}
        found, _ = helpers.chunks_of("s.xml", SHAPE, chat=counting, settings={"agentic_reading": "off"})
        self.assertEqual(spent, [], "off means off")
        self.assertEqual([unit["text"] for unit in found], [unit["text"] for unit in self.baseline()])


class WhatTheAnalystIsTold(unittest.TestCase):
    def test_a_proposal_that_changes_the_reading_is_named_on_model_package_info(self):
        _, result = helpers.chunks_of("s.xml", SHAPE, chat=helpers.standin(), settings={"agentic_reading": "rules"})
        rows = [row["value"] for row in result.records["info_rows"]
                if "how it was read" in row["item"] or "reading note" in row["item"]]
        self.assertTrue(any("blockcaption" in row and "heading" in row for row in rows), rows)
        for row in rows:
            self.assertEqual(helpers.banned_wording(row), "", row)

    def test_the_shape_shown_to_the_model_is_recorded(self):
        _, result = helpers.chunks_of("s.xml", SHAPE, chat=helpers.standin(), settings={"agentic_reading": "rules"})
        digests = result.records["shape_digests"]
        self.assertEqual(len(digests), 1)
        self.assertEqual(digests[0]["file"], "s.xml")


if __name__ == "__main__":
    unittest.main()
