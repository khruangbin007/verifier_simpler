"""live_trial.py - the first live trial of the judge questions with the REAL chat() (plan, Phase 7).

The owner runs this from the notebook after cell 7, with the real chat() and a fresh token:

    import live_trial
    print(live_trial.run_trial(chat, LIVE, samples=("F_capital", "A_minimal"), limit=200))

It builds the fixed judge questions of the samples (the search is deterministic, so they are the
same every time), asks them at concurrency 1 and at the configured limit, and asks them twice.
Measured: answers that could not be read, per attempt; rejections by reason; how often a planted
control passage was accepted; accepted links against the hand-made gold file, and how many gold
links were accepted; the stated confidence against correctness in four bands; second-question
disagreements; seconds per call; whether the two runs accepted the same links. The report is saved
as evaluation/live_trial_<date>.md. Without a real chat() the same code runs with the stand-in,
which is how it is tested offline:   python tools/live_trial.py --standin
"""
import csv
import datetime
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for folder in (os.path.join(ROOT, "engine"), os.path.join(ROOT, "engine", "tests")):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import aiva0_shared as shared       # noqa: E402
import aiva5_run_report as run      # noqa: E402

SAMPLES = os.path.join(ROOT, "engine", "tests", "sample_projects")


def one_run(sample, chat, live, concurrency):
    """Steps 01 to 08 on a fresh copy of the sample. Returns the accepted links, the call records and the seconds used."""
    projects = tempfile.mkdtemp(prefix="aiva_trial_")
    shutil.copytree(os.path.join(SAMPLES, sample, "Inputs"), os.path.join(projects, "TRIAL", "2026-01-01", "Inputs"))
    settings = run.make_settings({"require_outline_confirmation": False, "concurrency_limit": concurrency})
    paths = run.open_run(projects, "TRIAL", "2026-01-01", scratch_root=tempfile.mkdtemp(prefix="aiva_trial_local_"))
    started = datetime.datetime.now()
    run.run_pipeline(paths, settings, chat=chat, live=live, stop_after="08")
    store = run.open_store(paths, settings)
    links = [e for e in store.read("graph_ledger") if e["record_type"] == "edge" and e["kind"] == "corresponds"]
    result = {"links": links, "calls": store.read_calls(), "opinions": store.read("second_opinions"),
              "seconds": (datetime.datetime.now() - started).total_seconds()}
    shutil.rmtree(projects, ignore_errors=True)
    shutil.rmtree(paths.local_dir, ignore_errors=True)
    return result


def measures(sample, result):
    with open(os.path.join(SAMPLES, sample, "gold_links.csv"), encoding="utf-8") as handle:
        gold = {row["unit_ref"]: set(row["acceptable_methodology_refs"].split(";")) for row in csv.DictReader(handle)}
    calls = result["calls"]
    final = [c for c in calls if c["final"]]
    to_canon = [e for e in result["links"] if e["target"].startswith("C-") and e["relation"] in shared.LINKING_RELATIONS and e["source"] in gold]
    correct = [e for e in to_canon if e["target"] in gold[e["source"]]]
    found_gold = {e["source"] for e in correct}
    bands = {}
    for edge in to_canon:
        band = "%d-%d" % (25 * min(3, (edge["confidence"] or 0) // 25), 25 * min(3, (edge["confidence"] or 0) // 25) + 25)
        right, total = bands.get(band, (0, 0))
        bands[band] = (right + (edge in correct), total + 1)
    rejected = {}
    for call in final:
        if call["outcome"].startswith("rejected"):
            rejected[call["outcome"][10:]] = rejected.get(call["outcome"][10:], 0) + 1
    with_planted = [c for c in final if c.get("planted")]
    return {"questions": len(final), "attempts": len(calls),
            "attempts that could not be read": sum(1 for c in calls if c["outcome"] == "rejected: " + shared.REJECTION_REASONS[0]),
            "rejected, by reason": rejected, "questions without any answer": sum(1 for c in final if c["outcome"].startswith("failed")),
            "planted passage accepted": "%d of %d" % (rejected.get(shared.REJECTION_REASONS[3], 0), len(with_planted)),
            "accepted links to the methodology that are in the gold file": "%d of %d" % (len(correct), len(to_canon)),
            "gold units with an accepted gold link": "%d of %d" % (len(found_gold), len(gold)),
            "stated confidence against correctness": {band: "%d of %d right" % pair for band, pair in sorted(bands.items())},
            "second-question disagreements": len(result["opinions"]),
            "median seconds per call": sorted(c["seconds"] for c in calls)[len(calls) // 2] if calls else 0, "seconds for the run": round(result["seconds"], 1),
            "links": sorted((e["source"], e["target"], e["relation"]) for e in result["links"])}


def run_trial(chat, live=None, samples=("F_capital", "A_minimal"), concurrency=4, label="the real chat()"):
    lines = ["# Live trial of the judge questions", "", "Run on %s with %s." % (datetime.date.today().isoformat(), label), ""]
    for sample in samples:
        first = measures(sample, one_run(sample, chat, live, 1))
        second = measures(sample, one_run(sample, chat, live, concurrency))
        same = first.pop("links") == second.pop("links")
        lines += ["## %s" % sample, "", "| Measure | Concurrency 1 | Concurrency %d |" % concurrency, "|---|---|---|"]
        lines += ["| %s | %s | %s |" % (name, first[name], second[name]) for name in first]
        lines += ["", "The two runs accepted the same links: **%s**." % ("yes" if same else "no"), ""]
    os.makedirs(os.path.join(ROOT, "evaluation"), exist_ok=True)
    target = os.path.join(ROOT, "evaluation", "live_trial_%s%s.md" % (datetime.date.today().isoformat(), "_standin" if "stand-in" in label else ""))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return target


if __name__ == "__main__":
    import standin_chat
    if "--standin" not in sys.argv:
        sys.exit("Run this from the notebook with the real chat(), or with --standin to try the tool itself.")
    print(run_trial(standin_chat.chat, samples=("A_minimal",), label="the stand-in chat() (a test double, not a model)"))
