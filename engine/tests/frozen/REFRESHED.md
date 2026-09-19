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
