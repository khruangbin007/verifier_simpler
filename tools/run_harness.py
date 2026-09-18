"""run_harness.py - the seeded-difference harness (plan 4.3).

Plants one known difference at a time in a clean sample, runs AIVA with the stand-in chat(),
and records whether the seeded unit ends flagged. Three outcomes per mutant:
    flagged as expected   an item names the seeded unit and has an expected category
    flagged otherwise     the seeded unit is not clean, but for another reason
    not flagged           the seeded unit ended clean (every one of these is inspected by hand)
Also measured: the false-flag rate, the share of units in gold_clean_units.csv that end
flagged on the unseeded baseline. Inside the harness only, unchanged prompts are answered
from the answers already given in this harness session.

    python tools/run_harness.py F_capital [--limit 20] [--misbehave] [--operator "flip a sign"]
"""
import csv
import datetime
import hashlib
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for folder in (os.path.join(ROOT, "engine"), os.path.join(ROOT, "engine", "tests"), os.path.join(ROOT, "tools")):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import aiva5_run_report as run      # noqa: E402
import seed_differences             # noqa: E402
import standin_chat                 # noqa: E402

SAMPLES = os.path.join(ROOT, "engine", "tests", "sample_projects")


def cached(chat):
    """Answer an unchanged prompt from the answers already given in this harness session."""
    answers = {}
    def ask(system_prompt, main_prompt, *args, **kwargs):
        key = hashlib.sha256((system_prompt + "\n" + main_prompt).encode("utf-8")).hexdigest()
        if key not in answers:
            answers[key] = chat(system_prompt, main_prompt, *args, **kwargs)
        return answers[key]
    return ask


def run_once(sample, replaced, chat):
    """Run the pipeline on a copy of the sample's inputs with some input files replaced."""
    projects = tempfile.mkdtemp(prefix="aiva_harness_")
    inputs = os.path.join(projects, "HARNESS", "2026-01-01", "Inputs")
    shutil.copytree(os.path.join(SAMPLES, sample, "Inputs"), inputs)
    for relative, data in replaced.items():
        with open(os.path.join(inputs, relative), "wb") as handle:
            handle.write(data)
    settings = run.make_settings({"require_outline_confirmation": False})
    paths = run.open_run(projects, "HARNESS", "2026-01-01", scratch_root=tempfile.mkdtemp(prefix="aiva_harness_local_"))
    run.run_pipeline(paths, settings, chat=chat)
    store = run.open_store(paths, settings)
    result = {kind: store.read(kind) for kind in ("unit_status", "flagged_items", "model_units", "chunks_doc")}
    shutil.rmtree(projects, ignore_errors=True)
    shutil.rmtree(paths.local_dir, ignore_errors=True)
    return result


def seeded_units(mutant, result):
    """The units the planted difference sits in: by file and line, by data file, or by the new value."""
    if mutant["file"].lower().endswith((".docx", ".pdf")):
        return [c["ref"] for c in result["chunks_doc"] if mutant.get("new_value") and mutant["new_value"] in c["text"]]
    units = [u for u in result["model_units"] if u["file"] == mutant["file"]]
    if mutant["line"] is None:
        return [u["ref"] for u in units]
    return [u["ref"] for u in units if u.get("lines") and u["lines"][0] <= mutant["line"] <= u["lines"][1]]


def outcome_of(mutant, result):
    seeded = set(seeded_units(mutant, result))
    clean = {s["unit_ref"]: s["clean"] for s in result["unit_status"]}
    naming = [i for i in result["flagged_items"] if seeded & set(i["unit_refs"])]
    if any(i["category"] in mutant["expected"] for i in naming):
        return "flagged as expected", sorted({i["category"] for i in naming})
    if any(not clean.get(ref, True) for ref in seeded):
        return "flagged otherwise", sorted({i["category"] for i in naming})
    return "not flagged", []


def main(arguments):
    sample = arguments[0] if arguments and not arguments[0].startswith("--") else "F_capital"
    limit = int(arguments[arguments.index("--limit") + 1]) if "--limit" in arguments else 0
    only = arguments[arguments.index("--operator") + 1] if "--operator" in arguments else ""
    chat = cached(standin_chat.make_chat(misbehave="--misbehave" in arguments))
    baseline = run_once(sample, {}, chat)
    with open(os.path.join(SAMPLES, sample, "gold_clean_units.csv"), encoding="utf-8") as handle:
        gold_clean = [row["unit_ref"] for row in csv.DictReader(handle)]
    clean = {s["unit_ref"]: s["clean"] for s in baseline["unit_status"]}
    falsely = [ref for ref in gold_clean if not clean.get(ref, False)]
    mutants = [m for m in seed_differences.mutants_of(os.path.join(SAMPLES, sample, "Inputs")) if not only or m["operator"] == only]
    mutants = mutants[:limit] if limit else mutants
    rows = []
    for mutant in mutants:
        outcome, categories = outcome_of(mutant, run_once(sample, mutant["inputs"], chat))
        rows.append((mutant["id"], mutant["operator"], mutant["file"], mutant["line"] or "", mutant["what"], outcome, "; ".join(categories)))
        print(*rows[-1], sep=" | ", flush=True)
    today = datetime.date.today().isoformat()
    os.makedirs(os.path.join(ROOT, "evaluation"), exist_ok=True)
    report = os.path.join(ROOT, "evaluation", "harness_%s.md" % sample)
    operators = sorted({row[1] for row in rows})
    with open(report, "w", encoding="utf-8") as handle:
        handle.write("# Seeded-difference harness: %s\n\nRun on %s with the stand-in chat() (%s). Counts, not only percentages: with 30 mutants of a type, "
                     "30 of 30 supports a claim of about 90 percent, not 100.\n\n" % (sample, today, "misbehaving" if "--misbehave" in arguments else "well-behaved"))
        handle.write("False-flag rate on the clean baseline: %d of %d units listed in gold_clean_units.csv ended flagged%s.\n\n"
                     % (len(falsely), len(gold_clean), " (%s)" % ", ".join(falsely) if falsely else ""))
        handle.write("| Operator | Mutants | Flagged as expected | Flagged otherwise | Not flagged |\n|---|---|---|---|---|\n")
        for operator in operators:
            mine = [row for row in rows if row[1] == operator]
            handle.write("| %s | %d | %d | %d | %d |\n" % (operator, len(mine), sum(r[5] == "flagged as expected" for r in mine),
                                                         sum(r[5] == "flagged otherwise" for r in mine), sum(r[5] == "not flagged" for r in mine)))
        handle.write("\n## Every mutant\n\n| Id | Operator | File | Line | What changed | Outcome | Categories raised |\n|---|---|---|---|---|---|---|\n")
        for row in rows:
            handle.write("| " + " | ".join(str(cell) for cell in row) + " |\n")
        handle.write("\nEvery mutant that ended *not flagged* has to be inspected by hand and labelled *equivalent* or *missed*.\n")
    history = os.path.join(ROOT, "evaluation", "history.csv")
    new_file = not os.path.exists(history)
    with open(history, "a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(("date", "sample", "chat", "mutants", "flagged_as_expected", "flagged_otherwise", "not_flagged", "false_flags", "gold_clean_units"))
        writer.writerow((today, sample, "stand-in", len(rows), sum(r[5] == "flagged as expected" for r in rows),
                         sum(r[5] == "flagged otherwise" for r in rows), sum(r[5] == "not flagged" for r in rows), len(falsely), len(gold_clean)))
    print("written:", report)


if __name__ == "__main__":
    main(sys.argv[1:])
