"""test_samples_are_reproducible.py - the sample projects are built from source by
tools/build_samples.py, and the same source must give the same bytes.

Until 21 September 2026 it did not. Every sample's tarball and Word file changed on every rebuild,
though not one word in them had: the writer of stored R data stamps each .rda with the time and a
file name, and Word stamps every member of its archive with the moment it was saved. So a rebuild
showed as a change to every sample in the repository, a real change could hide among them, and
the evidence pack's hashes of the inputs were not a fact about the inputs.

Two things are held here. The builder is deterministic: two builds give identical bytes. And the
samples in the repository ARE what the builder gives: nothing has been edited by hand or left
over from an older builder.
"""
import hashlib
import os
import sys
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.ROOT_DIR, "tools"))
import build_samples


def build_into(folder):
    """Every sample, built into a folder of its own, as {path inside it: SHA-256}."""
    was = build_samples.SAMPLES
    build_samples.SAMPLES = folder
    try:
        for build in build_samples.BUILDERS.values():
            build()
    finally:
        build_samples.SAMPLES = was
    return digests(folder)


def digests(folder):
    found = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            with open(path, "rb") as handle:
                found[os.path.relpath(path, folder)] = hashlib.sha256(handle.read()).hexdigest()
    return found


class TheSamplesAreReproducible(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = build_into(helpers.scratch())
        cls.second = build_into(helpers.scratch())

    def test_two_builds_give_the_same_bytes(self):
        self.assertEqual(sorted(self.first), sorted(self.second))
        changed = sorted(path for path in self.first if self.first[path] != self.second[path])
        self.assertEqual(changed, [], "these came out different on a second build of the same source")

    def test_every_archive_and_word_file_is_covered(self):
        kinds = {os.path.splitext(path)[1] for path in self.first} | {".gz" for path in self.first if path.endswith(".tar.gz")}
        for kind in (".gz", ".docx", ".pdf"):
            self.assertIn(kind, kinds, "a build with no %s file proves nothing about %s files" % (kind, kind))

    def test_the_samples_in_the_repository_are_what_the_builder_gives(self):
        committed = digests(build_samples.SAMPLES)
        for path, digest in sorted(self.first.items()):
            self.assertIn(path, committed, "%s is built but not in the repository" % path)
            self.assertEqual(committed[path], digest,
                             "%s in the repository is not what tools/build_samples.py gives; rebuild it" % path)


if __name__ == "__main__":
    unittest.main()
