# Why the frozen snapshot was refreshed

Refreshing this snapshot is a deliberate act, never a way of making a test pass. Each refresh
is recorded here with what moved and why.

## 18 September 2026 - R2, the deterministic reader faults

**What moved.** One thing, on one sample. `D_dosing`'s methodology is a Word file exported to
the web, and its `<title>` reached no unit at all before R2. It is now read as a heading above
everything in the file, so all nine units of `chunks_canon` gain "Dosing method" at the front of
their heading chain and their level moves from 1 to 2.

**What did not move.** No unit's text. No reference. No record count. No field of any
`chunks_doc`, `model_units` or `parameter_tables` record, on any sample. Every other test in the
suite passed across the change, including the link, check and end-to-end tests, which is the
evidence that nothing downstream depends on the levels that shifted.

**Why it is right.** In a web export the `<title>` is often the only place the document's own
name survives, because the visible heading may be a styled paragraph carrying no heading level.
A methodology whose title is in no unit can be cited by nothing and covered by nothing. The
content account reported it as lost in R1; it is now kept.

## 21 September 2026 - the samples became reproducible

**What moved.** One field, six times: `file_sha256` on the model units that stand for stored R
data (`.rda`) inside the sample tarballs of A_minimal, D_dosing, F_capital and F_capital_known.

**Why.** The writer of stored R data stamped each `.rda` with the time it was written and a file
name, in its gzip header. So every rebuild of the samples gave those files new bytes, and their
SHA-256 moved though not one value in them had. `tools/build_samples.py` now writes them with no
time and no name, and Word files with one fixed time on every member.
`test_samples_are_reproducible.py` holds that two builds give identical bytes and that the
samples in the repository are exactly what the builder gives.

**What did not move.** Every other field of every record, on every sample: no text, no value, no
reference, no record count. Every harness and gold test passed across the change, which is the
evidence that the decoded values are the same.

**Why this is the last refresh of its kind.** The field moved because the bytes were not a fact
about the content. Now they are, so a rebuild can no longer move it.
