"""test_hard_reading_samples.py - G, H and I exist to be read badly, and to make the badness
measurable. Each stresses one corner of the reader:

  G_schema      an XML schema whose tags are named nothing the rules know, with lists inside
                table cells
  H_twocolumn   a PDF in two columns with a running header and footer on every page, a footnote,
                and an annex whose heading carries no number
  I_wordtraps   a Word file whose headings are bold paragraphs with no style, whose words hide
                in a text box, and which carries an unaccepted insertion and deletion

Each sample's gold_reading.csv names a phrase that a correct reading puts in some unit, where
it sits in the file, and the depth of the heading it belongs under where the file makes that
plain. This is READING gold: it says nothing about links, checks or statuses.

These tests hold two lines at once. The first is a floor that must never fall: what is read
today stays read, and nothing is ever added. The second records, as an expectation that is
allowed to be wrong today, what a correct reading would do - so that when guided reading
arrives in R3 and R4 the improvement is measured rather than asserted.
"""
import csv
import os
import unittest

import helpers

HARD = ("G_schema", "H_twocolumn", "I_wordtraps")

# Where the reader stands today, measured. A phase may raise these; nothing may lower them.
# phrases found, heading depths right out of those the gold states, units carrying a chain.
# G is measured with agentic_reading off, which is the default. What guidance adds to it is
# measured separately, in test_guided_reading.py and evaluation/guided_reading_2026-09-18.md.
TODAY = {
    "G_schema": {"present": 8, "levels_right": 0, "chained": 5},
    # H was 2 until the gold named the file each row is about: the same sentence sits in its
    # methodology, where the section has no title above it, so the PDF was scored against the
    # wrong file. The PDF reader places all three.
    "H_twocolumn": {"present": 7, "levels_right": 3, "chained": 20},
    "I_wordtraps": {"present": 7, "levels_right": 3, "chained": 20},
}


def gold_of(sample):
    path = os.path.join(helpers.SAMPLES_DIR, sample, "gold_reading.csv")
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def reading_of(sample, mode="off"):
    """Steps 01 to 04 of a hard sample: its units, and the content accounts of its files."""
    import aiva0_shared as shared
    import aiva5_run_report as run
    import standin_chat
    projects = helpers.scratch()
    helpers.copy_sample(sample, projects, "HARD", "2026-09-18")
    settings = run.make_settings({"require_outline_confirmation": False, "agentic_reading": mode})
    paths = run.open_run(projects, "HARD", "2026-09-18", scratch_root=helpers.scratch())
    run.run_pipeline(paths, settings, chat=standin_chat.chat_well_behaved, stop_after="04")
    store = run.open_store(paths, settings)
    units = [shared.to_plain(unit) for unit in store.read("chunks_canon")]
    units += [shared.to_plain(unit) for unit in store.read("chunks_doc")]
    return units, store.read("content_accounts"), len(store.read_calls())


def holding(units, phrase, in_file=""):
    """The first unit holding a phrase - in the file the gold names, where it names one."""
    for unit in units:
        if in_file and unit.get("source_file") != in_file:
            continue
        if phrase in (unit.get("text") or "") or phrase in " ".join(unit.get("heading_chain") or ()):
            return unit
    return None


def score(sample, mode="off"):
    units, accounts, calls = reading_of(sample, mode)
    gold = gold_of(sample)
    present = sum(1 for row in gold if holding(units, row["must_appear"], row.get("in_file") or ""))
    wanted = [row for row in gold if row["expected_level"]]
    right = sum(1 for row in wanted
                if holding(units, row["must_appear"], row.get("in_file") or "")
                and str(holding(units, row["must_appear"], row.get("in_file") or "").get("level")) == row["expected_level"])
    chained = sum(1 for unit in units if unit.get("heading_chain"))
    return {"present": present, "levels_right": right, "chained": chained,
            "gold": len(gold), "wanted": len(wanted), "units": len(units),
            "calls": calls, "units_list": units, "accounts": accounts}


class TheFloorNeverFalls(unittest.TestCase):
    """What is read today stays read. A phase may do better; none may do worse."""

    @classmethod
    def setUpClass(cls):
        cls.scores = {sample: score(sample) for sample in HARD}

    def test_no_phrase_the_reader_finds_today_is_ever_lost(self):
        for sample in HARD:
            self.assertGreaterEqual(self.scores[sample]["present"], TODAY[sample]["present"],
                                    "%s reads less of its gold than it did" % sample)

    def test_no_heading_depth_the_reader_gets_right_today_is_ever_lost(self):
        for sample in HARD:
            self.assertGreaterEqual(self.scores[sample]["levels_right"], TODAY[sample]["levels_right"],
                                    "%s places fewer headings than it did" % sample)

    def test_no_unit_loses_the_heading_chain_it_has_today(self):
        for sample in HARD:
            self.assertGreaterEqual(self.scores[sample]["chained"], TODAY[sample]["chained"],
                                    "%s carries a chain onto fewer units than it did" % sample)

    def test_nothing_is_ever_added_to_a_hard_sample(self):
        for sample in HARD:
            for account in self.scores[sample]["accounts"]:
                self.assertEqual(account["injected"], 0,
                                 "%s %s shows words its file does not hold: %s"
                                 % (sample, account["file"], account["what injected"]))

    def test_a_hard_sample_never_stops_a_run(self):
        for sample in HARD:
            self.assertGreater(self.scores[sample]["units"], 0, "%s produced no units at all" % sample)


class WhatACorrectReadingWouldDo(unittest.TestCase):
    """The second line: what the gold asks for. These are allowed to be short today, and the
    shortfall is the measured case for guided reading. Each says plainly what is wrong."""

    @classmethod
    def setUpClass(cls):
        cls.scores = {sample: score(sample) for sample in HARD}

    def test_an_unfamiliar_schema_is_still_read_flat(self):
        """G's blocks each carry a heading, and the reader sees none of them: every statement
        comes out at depth 0 with no chain, so a rule stated under 'Fines' cannot be told from
        one stated under 'Renewals'. This is the shortfall R3 exists to close."""
        found = self.scores["G_schema"]
        self.assertEqual(found["present"], found["gold"], "G's words are all read; it is the shape that is lost")
        self.assertLess(found["levels_right"], found["wanted"],
                        "G now places headings correctly with no guidance - raise TODAY and say so in the report")

    def test_guidance_closes_g_s_heading_gap_and_leaves_h_and_i_alone(self):
        """The measured case for guided reading, held as a test. With agentic_reading on, G's
        headings are placed and every unit carries a chain, for one question. H and I raise no
        doubt, so they ask nothing and come out exactly as they do without it."""
        guided = {sample: score(sample, mode="rules") for sample in HARD}
        self.assertEqual(guided["G_schema"]["levels_right"], guided["G_schema"]["wanted"],
                         "guidance should place every heading the gold names in G")
        self.assertEqual(guided["G_schema"]["calls"], 1, "one question about the shape of one file")
        for sample in ("H_twocolumn", "I_wordtraps"):
            self.assertEqual(guided[sample]["calls"], 0, "%s raises no doubt and should ask nothing" % sample)
            self.assertEqual(guided[sample]["levels_right"], self.scores[sample]["levels_right"])
            self.assertEqual(guided[sample]["present"], self.scores[sample]["present"])

    def test_two_list_items_in_one_table_cell_are_run_together(self):
        """G puts two list items inside one table cell. They arrive fused with no separator,
        so 'renewable twice' and 'no fine in the first two days' read as one phrase."""
        units, _, _ = reading_of("G_schema")
        tables = [unit for unit in units if unit.get("kind") == "Table"]
        self.assertTrue(tables, "G should produce a table")
        shown = " ".join(unit.get("text") or "" for unit in tables)
        self.assertIn("renewable twice", shown)
        self.assertIn("no fine in the first two days", shown)

    def test_an_unaccepted_deletion_is_not_what_the_document_says(self):
        """I carries a tracked deletion saying the opposite of the insertion beside it. The
        reader leaves it out, which is right: an unaccepted deletion is not what the document
        says. The account is what has to name it, not the units."""
        units, _, _ = reading_of("I_wordtraps")
        shown = " ".join(unit.get("text") or "" for unit in units)
        self.assertNotIn("zero point two units a kilometre everywhere", shown)
        self.assertIn("zero point four units a kilometre in the outer zone", shown)

    def test_a_text_box_and_a_bold_only_heading_are_already_read(self):
        """Two traps the reader survives, recorded so that a later phase cannot quietly break
        them: a heading made of nothing but bold is placed at depth 1, and the words inside a
        text box reach a unit."""
        units, _, _ = reading_of("I_wordtraps")
        box = holding(units, "rounded up to the nearest quarter of an hour")
        self.assertIsNotNone(box, "the words in a text box should reach a unit")
        heading = holding(units, "base rate of nine units")
        self.assertEqual(str(heading.get("level")), "1", "a bold-only heading should be placed at depth 1")

    def test_the_section_number_of_an_xml_document_now_reaches_every_unit_below_it(self):
        """H and I number their sections in an attribute on the container, while the heading it
        labels is a child of it. R2 lends the container's number to that heading, so the chain
        says "1. Watering windows" and a citation to section 1 can be resolved. Before R2 the
        number reached the block and then nothing, and the account reported it as lost."""
        units, accounts, _ = reading_of("H_twocolumn")
        chains = [" ".join(unit.get("heading_chain") or ()) for unit in units]
        self.assertTrue(any(chain.startswith("1.") for chain in chains),
                        "the number the document wrote should belong to the heading it labels")
        methodology = [one for one in accounts if one["file"].endswith(".xml")][0]
        self.assertTrue(methodology["closed"], methodology["what unaccounted"])

    def test_every_hard_sample_closes_its_content_account(self):
        """After R2 nothing in G, H or I is lost or added: every atom of every file is in a unit,
        in a unit's other fields, read into another form, left out under a named rule, or
        reported as not read."""
        for sample in HARD:
            for account in self.scores[sample]["accounts"]:
                self.assertTrue(account["closed"],
                                "%s %s: %d unplaced (%s), %d added (%s)"
                                % (sample, account["file"], account["unaccounted"],
                                   account["what unaccounted"][:6], account["injected"],
                                   account["what injected"][:6]))


if __name__ == "__main__":
    unittest.main()
