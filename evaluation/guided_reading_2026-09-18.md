# Guided reading: what one question about a file's shape is worth

**Measured 18 September 2026, engine 0.0.2, phase R3, with the stand-in model. First phase in which a reading step asks anything.**

R1 found that the reader could not prove it kept what it read. R2 fixed the faults that proof exposed. The hard samples then narrowed what was left to one thing: **an XML schema whose tags AIVA does not know is read flat.** Every word of G reaches a unit and not one of its heading depths is right, so a rule stated under "Fines" cannot be told from one stated under "Renewals".

This phase asks the model one question about such a file, and measures what that buys.

## The result

| Sample | Mode | Gold phrases | Heading depths | Units chained | Calls | Tokens | Account |
|---|---|---|---|---|---|---|---|
| **G_schema** | off | 8/8 | **0/4** | **5/17** | 0 | 0 | closed |
| **G_schema** | **rules** | 8/8 | **4/4** | **14/14** | **1** | 1,399 | closed |
| H_twocolumn | off | 7/7 | 2/3 | 20/21 | 0 | 0 | closed |
| H_twocolumn | rules | 7/7 | 2/3 | 20/21 | **0** | 0 | closed |
| I_wordtraps | off | 7/8 | 3/3 | 20/20 | 0 | 0 | closed |
| I_wordtraps | rules | 7/8 | 3/3 | 20/20 | **0** | 0 | closed |
| A_minimal | rules | — | — | 41/41 unchanged | **0** | 0 | closed |
| D_dosing | rules | — | — | 14/14 unchanged | 1 | 1,603 | closed |
| F_capital | rules | — | — | 46/46 unchanged | 1 | 1,906 | closed |
| F_capital_known | rules | — | — | 46/46 unchanged | 1 | 1,906 | closed |

**G's gap closes completely for one question and about 1,400 tokens.** Against the hundreds of calls `judge-links` spends on the same project, that is a rounding error.

**H and I ask nothing.** They raise no doubt, so no digest is built and no call is spent. This is the design working: the question fires only where the built-in rules themselves say they are unsure.

**The settled samples do not move.** D_dosing, F_capital and F_capital_known each spend one call, and **every field of every unit is identical to the frozen snapshot**. The proposal agrees with what discovery already worked out, so nothing changes. A_minimal raises no doubt at all.

## What the model is shown, and what it may say back

It is shown a **digest**: one line per tag with how often it occurs, how deep it sits, what it sits inside and holds, how often it carries text of its own and how long that runs, its attributes, how often it opens the block around it, and up to three samples cut to 120 characters. It never sees the file.

It answers with **choices, never text**: a tag it was shown, and one of five families. There is no field through which a word can enter or leave a document. The precedence, which is the whole safeguard:

> what the **analyst** wrote in `Inputs/tag_rules.yaml` beats what AIVA **ships**, which beats what discovery **proved** by counting rows, which beats what the **model** proposes, which beats what discovery **guessed** with its fallback net.

The model speaks where code guessed, and nowhere else. On G that is eight tags; the table's own structure — proved by counting row widths — is not its business, and the digest marks those as settled so it does not try.

## What the property test forced the design to become

The claim R3 had to earn was "no answer can lose a word or add one". A property test over random valid answers proved it **false three times**, and each failure narrowed the design. This is worth recording plainly, because none of it was reasoned out in advance.

1. **A proposal could call a container a paragraph.** That pulls the whole subtree's text into one unit *and* reads the same text again below it, so the document says twice what it says once. Now refused, using code's own count of what each tag holds.

2. **`inline` was unsafe by position rather than by kind.** An inline mark keeps its words only when it sits inside something that has running text; the identical answer was safe in one place and lossy in another. A family whose safety depends on where a tag sits is not a family a proposal may give, so `inline` was removed. Five families remain: heading, container, paragraph, list_container, list_item.

3. **A heading with nothing below it lost its words entirely.** A heading carries its text to the units beneath it; where it is popped off the chain having never had one, that text reached nothing. This is the *"should a heading be a unit?"* question flagged back at the ledger stage, arriving as a correctness requirement rather than a matter of taste. Such a heading now becomes a unit of its own.

Point 3 is the one to watch. It changes what the reader produces in a case no sample previously reached, and the frozen snapshot confirms no existing unit moved — but it is a structural change made under pressure from a property test, and it deserves a second pair of eyes.

## Cost

About 1,400 to 1,900 estimated tokens per file that raises a doubt, one call each, all at the front of the run. Two consequences:

- The first calls of a run now happen at step 02 rather than step 07a. A stale token shows itself in the first minute instead of the fortieth. `confirm-outline`'s description, which said no call had yet been spent, is corrected.
- The skill's own Procedure, Quality rules and Never sections are prepended to the system prompt (682 estimated tokens for `read-methodology`) and folded into the question id, so a changed contract asks a new question. The skill text is no longer read only by people.

## Limitations

- **Measured with the stand-in, not a real model.** The stand-in reads the digest and applies the rule the prompt describes. It shows the machinery works and the vocabulary is safe; it does not show that a real model reads an unfamiliar schema well. That needs a live run.
- **One sample.** G is the only input in the repository that the guidance improves. Three would be better; one is what the evidence justified building.
- **The default stays `off`.** The sign-off bar in R6 has not been met and this report does not claim it has. What is shown here is that the mechanism is safe, cheap and effective on the one case it was built for.
- The digest covers markup only. A `.docx` or PDF whose structure is in doubt raises no digest, because R2 showed those readers were not the problem.
