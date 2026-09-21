"""reading_report.py - the sign-off bar of the 0.0.2 reading rebuild, as something that runs.

    from tools import reading_report
    print(reading_report.run(chat, LIVE))          # with the real chat()
    python tools/reading_report.py --standin       # offline, how it is tested

It reads every sample project twice, once with `agentic_reading` off and once with it on, and
measures four things per sample:

  phrases     how many of the sample's gold_reading.csv phrases reach a unit
  levels      how many heading depths the gold names are right
  chained     how many units carry a heading chain
  account     whether every content account of the sample closes

THE BAR, and it is the owner's to sign off, not this file's. Changing the default for
`agentic_reading` from "off" to "rules" requires, ON A REAL MODEL:

  1. unaccounted and injected are zero on every file of every sample, in both modes;
  2. on G, H and I, phrases and levels with guidance are >= those without;
  3. on the four settled samples, every field of every unit is identical to the frozen
     snapshot in both modes (test_frozen_interface holds this; it is restated here);
  4. no answer is refused and retried, which would mean the prompt and the validator disagree.

This file reports each of the four and says whether all four held. It does not change the
default and cannot: that is a decision a person makes, on evidence from a real model, and the
stand-in is not evidence about a model. Run offline it says so on its own front page.
"""
import csv
import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "engine"), os.path.join(ROOT, "engine", "tests")]

HARD = ("G_schema", "H_twocolumn", "I_wordtraps")
SETTLED = ("A_minimal", "D_dosing", "F_capital", "F_capital_known")
MODES = ("off", "rules")


def gold_of(sample):
    path = os.path.join(ROOT, "engine", "tests", "sample_projects", sample, "gold_reading.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def one_run(sample, mode, chat, live):
    """Steps 01 to 04 of one sample in one mode, measured."""
    import helpers
    import aiva0_shared as shared
    import aiva5_run_report as run
    projects = helpers.scratch()
    helpers.copy_sample(sample, projects, "R6", "2026-09-18")
    settings = run.make_settings({"require_outline_confirmation": False, "agentic_reading": mode})
    paths = run.open_run(projects, "R6", "2026-09-18", scratch_root=helpers.scratch())
    run.run_pipeline(paths, settings, chat=chat, live=live, stop_after="04")
    store = run.open_store(paths, settings)
    units = [shared.to_plain(unit) for unit in store.read("chunks_canon")]
    units += [shared.to_plain(unit) for unit in store.read("chunks_doc")]
    accounts = store.read("content_accounts")
    calls = store.read_calls()
    gold = gold_of(sample)

    def holding(phrase, in_file=""):
        for unit in units:
            if in_file and unit.get("source_file") != in_file:
                continue
            if phrase in (unit.get("text") or "") or phrase in " ".join(unit.get("heading_chain") or ()):
                return unit
        return None

    wanted = [row for row in gold if row["expected_level"]]
    return {"phrases": sum(1 for row in gold if holding(row["must_appear"], row.get("in_file") or "")), "gold": len(gold),
            "levels": sum(1 for row in wanted if holding(row["must_appear"], row.get("in_file") or "")
                          and str(holding(row["must_appear"], row.get("in_file") or "")["level"]) == row["expected_level"]),
            "wanted": len(wanted),
            "chained": sum(1 for unit in units if unit.get("heading_chain")), "units": len(units),
            "calls": len(calls), "tokens": sum(call.get("estimated_tokens") or 0 for call in calls if call.get("final")),
            "closed": all(account["closed"] for account in accounts),
            "open_files": [account["file"] for account in accounts if not account["closed"]],
            "added": sum(account["injected"] for account in accounts),
            "lost": sum(account["unaccounted"] for account in accounts)}


def run(chat, live=None, samples=HARD + SETTLED, label="the real model"):
    found = {(sample, mode): one_run(sample, mode, chat, live) for sample in samples for mode in MODES}
    lines = report_lines(found, samples, label)
    os.makedirs(os.path.join(ROOT, "evaluation"), exist_ok=True)
    stamp = datetime.date.today().isoformat()
    target = os.path.join(ROOT, "evaluation", "reading_report_%s%s.md"
                          % (stamp, "_standin" if "stand-in" in label else ""))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    append_history(found, samples, label, stamp)
    return "\n".join(lines)


def bar(found, samples):
    """The four tests of the sign-off bar, each as (held, what it says)."""
    hard = [sample for sample in samples if sample in HARD]
    settled = [sample for sample in samples if sample in SETTLED]
    nothing_lost = [(sample, mode) for (sample, mode), one in found.items() if one["lost"] or one["added"]]
    worse = [sample for sample in hard
             if found[(sample, "rules")]["phrases"] < found[(sample, "off")]["phrases"]
             or found[(sample, "rules")]["levels"] < found[(sample, "off")]["levels"]
             or found[(sample, "rules")]["chained"] < found[(sample, "off")]["chained"]]
    measured = ("phrases", "levels", "chained", "units")
    moved = [sample for sample in settled
             if any(found[(sample, "rules")][key] != found[(sample, "off")][key] for key in measured)]
    # A call may only be spent on a file whose shape the rules are unsure of, and at most one
    # each. More than one call per unit of reading means the answer was refused and retried,
    # which is a cost the bar should see rather than hide.
    files_read = {sample: max(1, found[(sample, "off")]["units"] // 40 + 1) for sample in samples}
    chatty = [sample for sample in samples if found[(sample, "rules")]["calls"] > files_read[sample] + 1]
    return [
        (not nothing_lost, "Nothing is lost and nothing is added, on every file of every sample, in both modes"
                           + ("" if not nothing_lost else ": open on %s" % ", ".join("%s (%s)" % pair for pair in nothing_lost))),
        (not worse, "On the hard samples, guidance is never worse than no guidance"
                    + ("" if not worse else ": worse on %s" % ", ".join(worse))),
        (not moved, "On the settled samples, every measure is the same in both modes"
                    + ("" if not moved else ": moved on %s" % ", ".join(moved))),
        (not chatty, "No sample spends a call that was refused and retried"
                     + ("" if not chatty else ": %s" % ", ".join("%s %d calls" % (sample, found[(sample, "rules")]["calls"]) for sample in chatty))),
    ]

def report_lines(found, samples, label):
    stamp = datetime.date.today().isoformat()
    standin = "stand-in" in label
    lines = ["# Reading report: does guided reading earn its place?", "",
             "**Measured %s, engine 0.0.2, phase R6, with %s.**" % (stamp, label), ""]
    if standin:
        lines += ["> **This run used the stand-in, not a model.** The stand-in reads the digest and applies",
                  "> the rule the prompt describes. It shows the machinery is sound and the vocabularies are",
                  "> safe. It is not evidence about how a model reads an unfamiliar schema, and the sign-off",
                  "> bar below is therefore reported but **not met**. Re-run this file with a real chat() on",
                  "> Databricks to meet it.", ""]
    lines += ["## Per sample, off against rules", "",
              "| Sample | Mode | Phrases | Levels | Chained | Calls | Tokens | Account |",
              "|---|---|---|---|---|---|---|---|"]
    for sample in samples:
        for mode in MODES:
            one = found[(sample, mode)]
            lines.append("| %s | %s | %s | %s | %d/%d | %d | %d | %s |"
                         % (sample, mode,
                            "%d/%d" % (one["phrases"], one["gold"]) if one["gold"] else "-",
                            "%d/%d" % (one["levels"], one["wanted"]) if one["wanted"] else "-",
                            one["chained"], one["units"], one["calls"], one["tokens"],
                            "closed" if one["closed"] else "OPEN: " + ", ".join(one["open_files"])))
    lines += ["", "## The sign-off bar", "",
              "Changing the default for `agentic_reading` from `off` to `rules` requires all four, on a real model.", ""]
    tests = bar(found, samples)
    for held, says in tests:
        lines.append("- **%s** %s" % ("HELD" if held else "NOT HELD", says))
    everything = all(held for held, _ in tests)
    lines += ["", "**All four held: %s.**" % ("yes" if everything else "no")]
    if everything and standin:
        lines += ["", "All four held against the stand-in, which is necessary and not sufficient. The default",
                  "stays `off` until they hold against a real model."]
    lines += ["", "## What is not measured here", "",
              "- `rules_and_spans` does not appear, because R4 was not built. Nothing in G, H or I needs a",
              "  decision block by block that a rule could not settle, and building the machinery because the",
              "  plan listed it would have been the wrong reason. The setting accepts the value and the mode",
              "  does nothing.",
              "- Whether a unit is USEFUL. The content account measures whether words reach a unit, not whether",
              "  the unit can be linked or checked. R5 found the one place where those differ: a package member",
              "  with no reader is fully accounted for and still unusable.",
              "- Any file that is not markup or a tarball. A .docx or PDF whose structure is in doubt raises no",
              "  digest, because R2 showed those readers were not the problem."]
    return lines


def append_history(found, samples, label, stamp):
    """One row per sample and mode, in a file of its own: the columns of history.csv are about
    the judge's answers and do not fit a reading measurement."""
    path = os.path.join(ROOT, "evaluation", "reading_history.csv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(("date", "sample", "chat", "mode", "phrases", "gold", "levels", "wanted",
                             "chained", "units", "calls", "tokens", "lost", "added"))
        for sample in samples:
            for mode in MODES:
                one = found[(sample, mode)]
                writer.writerow((stamp, sample, "stand-in" if "stand-in" in label else "live", mode,
                                 one["phrases"], one["gold"], one["levels"], one["wanted"],
                                 one["chained"], one["units"], one["calls"], one["tokens"],
                                 one["lost"], one["added"]))


if __name__ == "__main__":
    import standin_chat
    print(run(standin_chat.chat_well_behaved, label="the stand-in"))
