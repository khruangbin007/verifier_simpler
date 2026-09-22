"""recall_at_k.py - measures the search stage alone against the hand-made gold links (plan 4.4).

For every unit in gold_links.csv: is one of its acceptable methodology passages among the top k
proposals? Reported per kind of unit and for an ablation ladder, one signal added at a time, so
that every signal has to earn its place. No chat() is involved: only steps 01 to 06 run.

    python tools/recall_at_k.py F_capital A_minimal D_dosing
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

import runner      # noqa: E402

SAMPLES = os.path.join(ROOT, "engine", "tests", "sample_projects")
LADDER = (("fields only", ["fields"]), ("+ bridge vocabulary", ["fields", "bridge"]), ("+ explicit references", ["fields", "bridge", "references"]),
          ("+ anchors and walk", ["fields", "bridge", "references", "anchors"]),
          ("+ formula signatures", ["fields", "bridge", "references", "anchors", "signatures"]))
KS = (3, 5, 12)


def shortlists(sample, signals):
    projects = tempfile.mkdtemp(prefix="aiva_recall_")
    shutil.copytree(os.path.join(SAMPLES, sample, "Inputs"), os.path.join(projects, "RECALL", "2026-01-01", "Inputs"))
    settings = runner.make_settings({"require_outline_confirmation": False, "signals": signals})
    paths = runner.open_run(projects, "RECALL", "2026-01-01", scratch_root=tempfile.mkdtemp(prefix="aiva_recall_local_"))
    runner.run_pipeline(paths, settings, chat=None, stop_after="06")
    store = runner.open_store(paths, settings)
    found = {}
    for candidate in store.read("candidates"):
        if candidate["target_corner"] == "canon" and candidate["search_pass"] == 1:
            found.setdefault(candidate["unit_ref"], []).append((candidate["rank"], candidate["target_ref"]))
    shutil.rmtree(projects, ignore_errors=True)
    shutil.rmtree(paths.local_dir, ignore_errors=True)
    return {ref: [target for _, target in sorted(ranked)] for ref, ranked in found.items()}


def kind_of(label):
    return label.split(" ")[0] if not label.startswith(("parameter", "documentation")) else " ".join(label.split(" ")[:2]) if label.startswith("parameter") else "documentation"


def main(samples):
    lines = ["# Relatedness report: recall of the search stage", "",
             "Measured on %s against the hand-made gold links of each sample. The samples are small, so these numbers show "
             "whether a signal earns its place here; they do not predict recall on a real model." % datetime.date.today().isoformat(), ""]
    for sample in samples:
        with open(os.path.join(SAMPLES, sample, "gold_links.csv"), encoding="utf-8") as handle:
            gold = [(row["unit_ref"], kind_of(row["unit"]), row["acceptable_methodology_refs"].split(";")) for row in csv.DictReader(handle)]
        lines += ["## %s (%d gold units)" % (sample, len(gold)), "", "| Signals | " + " | ".join("recall@%d" % k for k in KS) + " | units never proposed a gold passage |",
                  "|---|" + "---|" * (len(KS) + 1)]
        per_kind = {}
        for name, signals in LADDER:
            lists = shortlists(sample, signals)
            cells = []
            for k in KS:
                hits = sum(1 for ref, _, acceptable in gold if set(acceptable) & set(lists.get(ref, [])[:k]))
                cells.append("%d of %d" % (hits, len(gold)))
            missed = [ref for ref, _, acceptable in gold if not set(acceptable) & set(lists.get(ref, []))]
            lines.append("| %s | %s | %s |" % (name, " | ".join(cells), ", ".join(missed) or "none"))
            if signals == LADDER[-1][1]:
                for ref, kind, acceptable in gold:
                    hit, total = per_kind.get(kind, (0, 0))
                    per_kind[kind] = (hit + bool(set(acceptable) & set(lists.get(ref, [])[:5])), total + 1)
        lines += ["", "With all signals, recall@5 by kind of unit: " + "; ".join("%s %d of %d" % (kind, hit, total) for kind, (hit, total) in sorted(per_kind.items())) + ".", ""]
    os.makedirs(os.path.join(ROOT, "evaluation"), exist_ok=True)
    target = os.path.join(ROOT, "evaluation", "relatedness_report.md")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1:] or ["A_minimal", "F_capital", "D_dosing"])
