# Reading report: does guided reading earn its place?

**Measured 2026-09-19, engine 0.0.2, phase R6, with the stand-in.**

> **This run used the stand-in, not a model.** The stand-in reads the digest and applies
> the rule the prompt describes. It shows the machinery is sound and the vocabularies are
> safe. It is not evidence about how a model reads an unfamiliar schema, and the sign-off
> bar below is therefore reported but **not met**. Re-run this file with a real chat() on
> Databricks to meet it.

## Per sample, off against rules

| Sample | Mode | Phrases | Levels | Chained | Calls | Tokens | Account |
|---|---|---|---|---|---|---|---|
| G_schema | off | 8/8 | 0/4 | 5/17 | 0 | 0 | closed |
| G_schema | rules | 8/8 | 4/4 | 14/14 | 1 | 1399 | closed |
| H_twocolumn | off | 7/7 | 2/3 | 20/21 | 0 | 0 | closed |
| H_twocolumn | rules | 7/7 | 2/3 | 20/21 | 0 | 0 | closed |
| I_wordtraps | off | 7/8 | 3/3 | 20/20 | 0 | 0 | closed |
| I_wordtraps | rules | 7/8 | 3/3 | 20/20 | 0 | 0 | closed |
| A_minimal | off | - | - | 41/41 | 0 | 0 | closed |
| A_minimal | rules | - | - | 41/41 | 0 | 0 | closed |
| D_dosing | off | - | - | 14/14 | 0 | 0 | closed |
| D_dosing | rules | - | - | 14/14 | 1 | 1603 | closed |
| F_capital | off | - | - | 46/46 | 0 | 0 | closed |
| F_capital | rules | - | - | 46/46 | 1 | 1906 | closed |
| F_capital_known | off | - | - | 46/46 | 0 | 0 | closed |
| F_capital_known | rules | - | - | 46/46 | 1 | 1906 | closed |

## The sign-off bar

Changing the default for `agentic_reading` from `off` to `rules` requires all four, on a real model.

- **HELD** Nothing is lost and nothing is added, on every file of every sample, in both modes
- **HELD** On the hard samples, guidance is never worse than no guidance
- **HELD** On the settled samples, every measure is the same in both modes
- **HELD** No sample spends a call that was refused and retried

**All four held: yes.**

All four held against the stand-in, which is necessary and not sufficient. The default
stays `off` until they hold against a real model.

## What is not measured here

- `rules_and_spans` does not appear, because R4 was not built. Nothing in G, H or I needs a
  decision block by block that a rule could not settle, and building the machinery because the
  plan listed it would have been the wrong reason. The setting accepts the value and the mode
  does nothing.
- Whether a unit is USEFUL. The content account measures whether words reach a unit, not whether
  the unit can be linked or checked. R5 found the one place where those differ: a package member
  with no reader is fully accounted for and still unusable.
- Any file that is not markup or a tarball. A .docx or PDF whose structure is in doubt raises no
  digest, because R2 showed those readers were not the problem.
