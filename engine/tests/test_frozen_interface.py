"""test_frozen_interface.py - the 0.0.2 reading rebuild is allowed to change HOW a file is
sliced. It is not allowed to change the SHAPE of what comes out, and on inputs AIVA already
reads well it must not change the content either.

This test freezes the three unit record kinds that feed Chunks_Canon, Chunks_Doc and
Chunks_Model, plus the parameter tables that hang off the package units, for every sample
project. A snapshot under tests/frozen/ holds what steps 01 to 04 produced before the rebuild
began. Every later phase is measured against it.

Two guarantees, and they are different:

  * SHAPE. The field names of every record are exactly the frozen ones, minus nothing. A field
    may be ADDED (the plan appends `reading_how`), because a new defaulted field breaks no
    reader downstream; a field may never be removed or renamed.
  * CONTENT. On the four samples that existed at 0.0.1 every frozen field holds its frozen
    value. These samples raise no reading doubt, so no question is ever asked about them and
    the guided reading must come out where the built-in rules come out. If a phase moves a
    value here, it has changed a file AIVA already read correctly, and the gold files, the
    harness numbers and the recall figures downstream would all move with it.

Refreshing the snapshot is not a way to make this test pass. It is a deliberate act with its
own reason, recorded in evaluation/history.csv:  python tests/test_frozen_interface.py --freeze
"""
import json
import os
import sys
import unittest

import helpers

FROZEN_DIR = os.path.join(helpers.TESTS_DIR, "frozen")
KINDS = ("chunks_canon", "chunks_doc", "model_units", "parameter_tables")

# The samples that existed at 0.0.1. Later phases add hard samples (G, H, I) whose whole point is
# that the reading CHANGES, so those are measured in evaluation/reading_report.md, not frozen here.
SETTLED_SAMPLES = ("A_minimal", "D_dosing", "F_capital", "F_capital_known")


def units_of_sample(sample):
    """Steps 01 to 04 of one sample, as plain dictionaries, with nothing that varies by runner."""
    import core
    import runner
    import standin_chat

    projects = helpers.scratch()
    helpers.copy_sample(sample, projects, "FROZEN", "2026-09-18")
    settings = runner.make_settings({"require_outline_confirmation": False})
    paths = runner.open_run(projects, "FROZEN", "2026-09-18", scratch_root=helpers.scratch())
    runner.run_pipeline(paths, settings, chat=standin_chat.chat_well_behaved, stop_after="04")
    store = runner.open_store(paths, settings)
    found = {}
    for kind in KINDS:
        rows = [core.to_plain(row) for row in store.read(kind)]
        found[kind] = [helpers.without_times(row) for row in rows]
    return found


def frozen_path(sample):
    return os.path.join(FROZEN_DIR, "%s.json" % sample)


def load_frozen(sample):
    with open(frozen_path(sample), encoding="utf-8") as handle:
        return json.load(handle)


class TheThreeUnitSheetsAreFrozen(unittest.TestCase):
    """What steps 02, 03 and 04 hand to step 05 and to the workbook."""

    @classmethod
    def setUpClass(cls):
        cls.found = {sample: units_of_sample(sample) for sample in SETTLED_SAMPLES}

    def test_a_snapshot_exists_for_every_settled_sample(self):
        for sample in SETTLED_SAMPLES:
            self.assertTrue(os.path.exists(frozen_path(sample)),
                            "no frozen snapshot for %s; run with --freeze once, deliberately" % sample)

    def test_no_field_is_ever_removed_or_renamed(self):
        for sample in SETTLED_SAMPLES:
            frozen = load_frozen(sample)
            for kind in KINDS:
                for position, was in enumerate(frozen[kind]):
                    self.assertLess(position, len(self.found[sample][kind]),
                                    "%s %s: record %d disappeared" % (sample, kind, position))
                    now = self.found[sample][kind][position]
                    missing = sorted(set(was) - set(now))
                    self.assertEqual(missing, [], "%s %s record %d lost field(s)" % (sample, kind, position))

    def test_every_frozen_value_still_holds_on_a_settled_sample(self):
        for sample in SETTLED_SAMPLES:
            frozen = load_frozen(sample)
            for kind in KINDS:
                self.assertEqual(len(self.found[sample][kind]), len(frozen[kind]),
                                 "%s %s: the number of records moved" % (sample, kind))
                for position, was in enumerate(frozen[kind]):
                    now = self.found[sample][kind][position]
                    for field in sorted(was):
                        self.assertEqual(now[field], was[field],
                                         "%s %s record %d field '%s' moved" % (sample, kind, position, field))

    def test_references_are_still_in_reading_order_without_a_gap(self):
        for sample in SETTLED_SAMPLES:
            for kind, prefix in (("chunks_canon", "C"), ("chunks_doc", "D"), ("model_units", "M")):
                refs = [row["ref"] for row in self.found[sample][kind]]
                self.assertEqual(refs, ["%s-%04d" % (prefix, n) for n in range(1, len(refs) + 1)],
                                 "%s %s: references are not a gapless run" % (sample, kind))


def freeze():
    """Write the snapshot. Deliberate, and never a way of making the test pass."""
    os.makedirs(FROZEN_DIR, exist_ok=True)
    for sample in SETTLED_SAMPLES:
        with open(frozen_path(sample), "w", encoding="utf-8") as handle:
            json.dump(units_of_sample(sample), handle, indent=1, sort_keys=True)
        print("froze %s" % sample)


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        freeze()
    else:
        unittest.main()
