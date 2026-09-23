"""
Verifier 0.0.3 - develop.py - everything that is about the tool rather than about a run: how it
is measured, checked against its own manual, and how the notebook is built.
For whoever maintains the tool.

WHAT THIS FILE DOES
  Measurement. Seeded differences (mutants of a sample package, its data and its documentation)
  recall of the candidate search against gold links; a live
  trial that compares two runs at different concurrency; an environment probe for a new
  cluster; and the sign-off bar for guided reading. Each returns its report as text and records
  its numbers in one history file, engine/tests/history.csv. No report file is written.
  a run's manifest is compared with it, so a run can prove which code produced it.
  Checks on the code itself. Line budgets, and that the one manual names only things that
  exist and explains every setting and every design rule.
  The notebook. Built from this file, five cells, so that what the notebook does is in code
  that is tested and not in cells that are edited by hand.

WHAT IT TAKES IN AND PRODUCES
  In: the sample projects, a chat() where a measurement needs one, the manual.
  Out: report text; rows in engine/tests/history.csv; the notebook.

WHICH SHEETS SHOW ITS RESULTS
  None: nothing here is part of a run. What it measures is described in the manual.

DESIGN RULES ENFORCED HERE
  R10 the check on the manual keeps every word of it true of the code.
  R11 line budgets; the notebook is generated, never edited by hand.

HOW TO SANITY-CHECK IT
  python engine/develop.py budgets      python engine/develop.py release
  python engine/develop.py check-docs   python engine/develop.py notebook
  python engine/develop.py harness A_minimal --limit 10
"""

import ast
import csv
import datetime
import glob
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import tokenize
import warnings
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = ROOT if os.path.basename(ROOT) == "engine" else os.path.join(ROOT, "engine")
TESTS = os.path.join(ENGINE, "tests")
SAMPLES = os.path.join(TESTS, "sample_projects")
HISTORY = os.path.join(TESTS, "history.csv")
MANUAL = os.path.join(os.path.dirname(ENGINE), "docs", "Manual.md")
NOTEBOOK = os.path.join(os.path.dirname(ENGINE), "Verifier.ipynb")
for folder in (ENGINE, TESTS):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import verifier    # noqa: E402
core = reading = review = runner = verifier   # the engine is one module now


def remember(measure, date, sample, chat, **numbers):
    """One row in the shared history: which measurement, when, on what, with what, and its numbers
    as key=value pairs, so that measurements with different columns share one file."""
    new = not os.path.exists(HISTORY)
    with open(HISTORY, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new:
            writer.writerow(("measure", "date", "sample", "chat", "numbers"))
        writer.writerow((measure, date, sample, chat, " ".join("%s=%s" % item for item in sorted(numbers.items()))))

# ================================================================================================
# ---------------------------------------------------------------- from tools/seed_differences.py
TRIVIAL = ("0", "1", "2", "10", "100")
CODE_CATEGORIES = ("Code differs from methodology", "Hard-coded number not traced", "Package documentation differs from code")
DATA_CATEGORIES = ("Value differs from methodology", "Documentation differs from code")
ROXYGEN_CATEGORIES = ("Package documentation differs from code", "Package documentation differs from methodology")
DOC_CATEGORIES = ("Documentation differs from methodology", "Documentation differs from code")


def read_tarball(path):
    files, top = {}, ""
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            if member.isfile():
                top, name = member.name.split("/", 1)
                files[name] = archive.extractfile(member).read()
    return top, files


def write_tarball(top, files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(files):
            member = tarfile.TarInfo("%s/%s" % (top, path))
            member.size, member.mtime, member.mode = len(files[path]), 1767225600, 0o644
            archive.addfile(member, io.BytesIO(files[path]))
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as handle:
        handle.write(raw.getvalue())
    return packed.getvalue()


def changed_number(text, way):
    """A constant changed in one of three ways: a tenth more, last digit plus one, halved."""
    decimals = len(text.split(".")[1]) if "." in text else 0
    value = float(text)
    if way == "a tenth more":
        new = value * 1.1
    elif way == "last digit plus one":
        new = value + 10 ** (-decimals)
    else:
        new = value / 2.0
    shown = ("%%.%df" % (decimals + (1 if way != "last digit plus one" else 0))) % new
    return shown if float(shown) != value else str(value + 1)


def code_mutants(path, text):
    """(operator, line number, description, new text) for one R file."""
    mutants, lines = [], text.split("\n")
    def put(number, new_line, operator, what):
        changed = list(lines)
        changed[number] = new_line
        mutants.append({"operator": operator, "file": path, "line": number + 1, "what": what, "text": "\n".join(changed), "expected": CODE_CATEGORIES})
    for number, line in enumerate(lines):
        code = line.split("#")[0]
        if not code.strip() or line.lstrip().startswith("#") or "function(" in code or "stop(" in code or "library(" in code:
            continue
        for sign, other in ((" + ", " - "), (" - ", " + ")):
            if sign in code:
                put(number, line.replace(sign, other, 1), "flip a sign", "'%s' became '%s'" % (sign.strip(), other.strip()))
                break
        for sign, other in ((" * ", " / "), (" / ", " * ")):
            if sign in code:
                put(number, line.replace(sign, other, 1), "swap an operator", "'%s' became '%s'" % (sign.strip(), other.strip()))
                break
        for sign, other in ((" > ", " < "), (" < ", " > "), (" >= ", " <= "), (" <= ", " >= ")):
            if sign in code and "<-" not in code.replace(" <- ", ""):
                put(number, line.replace(sign, other, 1), "change a comparison", "'%s' became '%s'" % (sign.strip(), other.strip()))
                break
        guard = re.search(r"\bp(max|min)\(([^(),]+), ([^(),]+)\)", code)
        if guard:
            put(number, line.replace(guard.group(0), guard.group(2), 1), "remove a floor or cap", "'%s' became '%s'" % (guard.group(0), guard.group(2)))
        for found in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", code):
            if found.group(0) in TRIVIAL or re.search(r"lines?\s*$", code[:found.start()]):
                continue
            for way in ("a tenth more", "last digit plus one", "halved"):
                new_line = line[:found.start()] + changed_number(found.group(0), way) + line[found.end():]
                put(number, new_line, "change a constant", "%s became %s (%s)" % (found.group(0), changed_number(found.group(0), way), way))
            break
    return mutants


def roxygen_mutants(path, text):
    mutants, lines = [], text.split("\n")
    def put(number, new_line, operator, what):
        changed = list(lines)
        if new_line is None:
            del changed[number]
        else:
            changed[number] = new_line
        line = number if new_line is None else number + 1        # after a deletion the block ends one line earlier
        mutants.append({"operator": operator, "file": path, "line": line, "what": what, "text": "\n".join(changed), "expected": ROXYGEN_CATEGORIES})
    for number, line in enumerate(lines):
        if not line.startswith("#'"):
            continue
        param = re.match(r"#' @param (\w+) ", line)
        if param:
            put(number, line.replace("@param %s " % param.group(1), "@param %s_x " % param.group(1), 1), "rename a parameter", "@param %s became %s_x" % (param.group(1), param.group(1)))
        stated = re.search(r"defaults to (\d+(?:\.\d+)?)", line)
        if stated:
            put(number, line.replace(stated.group(1), changed_number(stated.group(1), "halved"), 1), "change a stated default", "default %s became %s" % (stated.group(1), changed_number(stated.group(1), "halved")))
        value = re.search(r"(?<![\w.{])\d+\.\d+(?![\w.])", line)
        if value and not param and "deqn" not in line and "@" not in line:
            put(number, line.replace(value.group(0), changed_number(value.group(0), "a tenth more"), 1), "change a stated value", "%s became %s" % (value.group(0), changed_number(value.group(0), "a tenth more")))
        if line.strip() == "#' @export":
            put(number, None, "drop the export tag", "@export removed")
    return mutants


def data_mutants(path, data):
    import rdata
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = rdata.conversion.convert(rdata.parser.parse_data(data))
    single = not isinstance(parsed, dict)
    frame = parsed if single else list(parsed.values())[0]
    name = None if single else list(parsed.keys())[0]
    numeric = [c for c in frame.columns if str(frame[c].dtype).lower().startswith(("float", "int"))]
    if not numeric or len(frame) < 2:
        return []
    def written(new_frame):
        target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_seed.bin")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rdata.write_rds(target, new_frame) if single else rdata.write_rda(target, {name: new_frame})
        with open(target, "rb") as handle:
            result = handle.read()
        os.remove(target)
        return result
    column, mutants = numeric[0], []
    cell = frame.copy()
    cell.loc[cell.index[0], column] = float(cell.loc[cell.index[0], column]) * 1.5
    mutants.append(("change a cell", "first row of %s times 1.5" % column, cell))
    mutants.append(("drop a row", "last row removed", frame.iloc[:-1].copy()))
    swapped = frame.copy()
    first, second = swapped.loc[swapped.index[0], column], swapped.loc[swapped.index[1], column]
    swapped.loc[swapped.index[0], column], swapped.loc[swapped.index[1], column] = second, first
    mutants.append(("swap two values", "first two values of %s swapped" % column, swapped))
    return [{"operator": operator, "file": path, "line": None, "what": what, "bytes": written(new), "expected": DATA_CATEGORIES} for operator, what, new in mutants]


def docx_mutants(name, data):
    """Change a value: the first decimal number or percentage in each paragraph of a .docx."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {item.filename: archive.read(item.filename) for item in archive.infolist()}
    document = parts["word/document.xml"].decode("utf-8")
    mutants, candidates = [], []
    for paragraph in re.finditer(r"<w:p[ >].*?</w:p>", document, re.S):            # headings and their numbering are left alone
        if "<w:pStyle w:val=\"Heading" in paragraph.group(0) or "<m:oMath" in paragraph.group(0):
            continue
        inner = re.search(r"(<w:t[^>]*>[^<]*?)(\d+\.\d+)(%?)", paragraph.group(0))
        if inner:
            candidates.append((paragraph.start() + inner.start(2), paragraph.start() + inner.end(2), inner.group(2), inner.group(3)))
    for start, end, old_value, percent in candidates[:6]:
        found = type("Found", (), {"start": lambda self, g: start, "end": lambda self, g: end, "group": lambda self, g: old_value if g == 2 else percent})()
        new_value = changed_number(found.group(2), "a tenth more")
        changed = document[:found.start(2)] + new_value + document[found.end(2):]
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as target:
            for filename in parts:
                target.writestr(filename, changed.encode("utf-8") if filename == "word/document.xml" else parts[filename])
        mutants.append({"operator": "change a value in the documentation", "file": name, "line": None, "new_value": new_value + found.group(3),
                        "what": "%s became %s" % (found.group(2), new_value), "bytes": packed.getvalue(), "expected": DOC_CATEGORIES})
    return mutants




# ================================================================================================
# ---------------------------------------------------------------- from tools/run_harness.py
for folder in (os.path.join(ROOT, "engine"), os.path.join(ROOT, "engine", "tests"), os.path.join(ROOT, "tools")):
    if folder not in sys.path:
        sys.path.insert(0, folder)





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
    projects = tempfile.mkdtemp(prefix="verifier_harness_")
    inputs = os.path.join(projects, "HARNESS", "2026-01-01", "Inputs")
    shutil.copytree(os.path.join(SAMPLES, sample, "Inputs"), inputs)
    for relative, data in replaced.items():
        with open(os.path.join(inputs, relative), "wb") as handle:
            handle.write(data)
    settings = runner.make_settings({})
    paths = runner.open_run(projects, "HARNESS", "2026-01-01", scratch_root=tempfile.mkdtemp(prefix="verifier_harness_local_"))
    runner.run_pipeline(paths, settings, chat=chat)
    store = runner.open_store(paths, settings)
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




# ================================================================================================
# ---------------------------------------------------------------- from tools/recall_at_k.py

LADDER = (("fields only", ["fields"]), ("+ bridge vocabulary", ["fields", "bridge"]), ("+ explicit references", ["fields", "bridge", "references"]),
          ("+ anchors and walk", ["fields", "bridge", "references", "anchors"]),
          ("+ formula signatures", ["fields", "bridge", "references", "anchors", "signatures"]))
KS = (3, 5, 12)


def shortlists(sample, signals):
    projects = tempfile.mkdtemp(prefix="verifier_recall_")
    shutil.copytree(os.path.join(SAMPLES, sample, "Inputs"), os.path.join(projects, "RECALL", "2026-01-01", "Inputs"))
    settings = runner.make_settings({"signals": signals})
    paths = runner.open_run(projects, "RECALL", "2026-01-01", scratch_root=tempfile.mkdtemp(prefix="verifier_recall_local_"))
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


def recall(samples):
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
    print("\n".join(lines))
    return "\n".join(lines)


# ================================================================================================
# ---------------------------------------------------------------- from tools/live_trial.py

def trial_run(sample, chat, live, concurrency):
    """Steps 01 to 08 on a fresh copy of the sample. Returns the accepted links, the call records and the seconds used."""
    projects = tempfile.mkdtemp(prefix="verifier_trial_")
    shutil.copytree(os.path.join(SAMPLES, sample, "Inputs"), os.path.join(projects, "TRIAL", "2026-01-01", "Inputs"))
    settings = runner.make_settings({"concurrency_limit": concurrency})
    paths = runner.open_run(projects, "TRIAL", "2026-01-01", scratch_root=tempfile.mkdtemp(prefix="verifier_trial_local_"))
    started = datetime.datetime.now()
    runner.run_pipeline(paths, settings, chat=chat, live=live, stop_after="08")
    store = runner.open_store(paths, settings)
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
    to_canon = [e for e in result["links"] if e["target"].startswith("C-") and e["relation"] in core.LINKING_RELATIONS and e["source"] in gold]
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
            "attempts that could not be read": sum(1 for c in calls if c["outcome"] == "rejected: " + core.REJECTION_REASONS[0]),
            "rejected, by reason": rejected, "questions without any answer": sum(1 for c in final if c["outcome"].startswith("failed")),
            "planted passage accepted": "%d of %d" % (rejected.get(core.REJECTION_REASONS[3], 0), len(with_planted)),
            "accepted links to the methodology that are in the gold file": "%d of %d" % (len(correct), len(to_canon)),
            "gold units with an accepted gold link": "%d of %d" % (len(found_gold), len(gold)),
            "stated confidence against correctness": {band: "%d of %d right" % pair for band, pair in sorted(bands.items())},
            "second-question disagreements": len(result["opinions"]),
            "median seconds per call": sorted(c["seconds"] for c in calls)[len(calls) // 2] if calls else 0, "seconds for the run": round(result["seconds"], 1),
            "links": sorted((e["source"], e["target"], e["relation"]) for e in result["links"])}


def run_trial(chat, live=None, samples=("F_capital", "A_minimal"), concurrency=4, label="the real chat()"):
    lines = ["# Live trial of the judge questions", "", "Run on %s with %s." % (datetime.date.today().isoformat(), label), ""]
    for sample in samples:
        first = measures(sample, trial_run(sample, chat, live, 1))
        second = measures(sample, trial_run(sample, chat, live, concurrency))
        same = first.pop("links") == second.pop("links")
        lines += ["## %s" % sample, "", "| Measure | Concurrency 1 | Concurrency %d |" % concurrency, "|---|---|---|"]
        lines += ["| %s | %s | %s |" % (name, first[name], second[name]) for name in first]
        lines += ["", "The two runs accepted the same links: **%s**." % ("yes" if same else "no"), ""]
    return "\n".join(lines)


# ================================================================================================
# ---------------------------------------------------------------- from tools/environment_probe.py
if os.path.join(ROOT, "engine") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "engine"))


def timed(action):
    started = time.time()
    try:
        detail = action()
        return True, time.time() - started, detail or ""
    except Exception as problem:                      # a probe reports what it met; it never stops the others
        return False, time.time() - started, "%s: %s" % (type(problem).__name__, problem)


def probe_append(folder, sizes_mb):
    lines = []
    for size in sizes_mb:
        path = os.path.join(folder, "probe_append_%s.jsonl" % str(size).replace(".", "_"))
        with open(path, "wb") as handle:
            handle.write(b"x" * int(size * 1024 * 1024))
        def append():
            for number in range(20):
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"n": number, "text": "y" * 900}) + "\n")
        works, seconds, detail = timed(append)
        lines.append("file of %s MB: %s, %.4f seconds per append %s" % (size, "works" if works else "does not work", seconds / 20, detail))
        os.remove(path)
    return lines


def probe_office_files(folder):
    import docx
    import openpyxl
    def build(target_folder):
        workbook = openpyxl.Workbook()
        for row in range(2000):
            workbook.active.append(["cell %d" % row, row, "some longer text " * 5])
        workbook.save(os.path.join(target_folder, "probe.xlsx"))
        document = docx.Document()
        for number in range(300):
            document.add_paragraph("Paragraph %d of the probe document." % number)
        document.save(os.path.join(target_folder, "probe.docx"))
    direct = timed(lambda: build(folder))
    local = tempfile.mkdtemp(prefix="verifier_probe_")
    def build_then_copy():
        build(local)
        for name in ("probe.xlsx", "probe.docx"):
            shutil.copyfile(os.path.join(local, name), os.path.join(folder, "copied_" + name))
    copied = timed(build_then_copy)
    return ["written directly: %s in %.2f seconds %s" % ("works" if direct[0] else "does not work", direct[1], direct[2]),
            "built locally, then copied: %s in %.2f seconds %s" % ("works" if copied[0] else "does not work", copied[1], copied[2])]


def probe_many_files(folder):
    many = os.path.join(folder, "probe_many")
    os.makedirs(many, exist_ok=True)
    def small_files():
        for number in range(200):
            with open(os.path.join(many, "record_%03d.json" % number), "w", encoding="utf-8") as handle:
                handle.write(json.dumps({"n": number, "text": "z" * 500}))
    def one_file():
        with open(os.path.join(folder, "probe_one.jsonl"), "w", encoding="utf-8") as handle:
            for number in range(200):
                handle.write(json.dumps({"n": number, "text": "z" * 500}) + "\n")
    first, second = timed(small_files), timed(one_file)
    return ["200 small files: %.2f seconds %s" % (first[1], first[2]), "one JSON Lines file with 200 records: %.2f seconds %s" % (second[1], second[2])]


def probe_large_copy(folder, size_mb):
    local = os.path.join(tempfile.mkdtemp(prefix="verifier_probe_"), "large.bin")
    with open(local, "wb") as handle:
        handle.write(os.urandom(1024 * 1024) * int(size_mb))
    works, seconds, detail = timed(lambda: shutil.copyfile(local, os.path.join(folder, "probe_large.bin")) and None)
    return ["whole-file copy of %d MB: %s in %.2f seconds %s" % (size_mb, "works" if works else "does not work", seconds, detail)]


def probe_replace(folder):
    target, fresh = os.path.join(folder, "probe_replace.txt"), os.path.join(folder, "probe_replace_new.txt")
    for path, text in ((target, "old"), (fresh, "new")):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    works, _, detail = timed(lambda: os.replace(fresh, target))
    with open(target, encoding="utf-8") as handle:
        content = handle.read()
    return ["replace onto an existing file: %s %s" % ("works" if works and content == "new" else "does not work", detail)]


def probe_chat(chat, live):
    live = live or runner.LiveValues()
    kept = dict(live.values)
    live.update(kept.get("llm_endpoint", ""), "", kept.get("llm_user_id", ""))
    answer, failure, seen = runner.call_chat(chat, "You answer with one word.", "Say yes.", live)
    live.update(kept.get("llm_endpoint", ""), kept.get("llm_token", ""), kept.get("llm_user_id", ""))
    return ["with an empty token chat() gave: %s" % (("an answer: %r" % answer[:60]) if answer else "no answer"),
            "the wrapper read this as: %s" % (failure or "a normal answer"), "what was seen (tokens removed): %s" % (seen[:300] or "nothing unusual")]


def run_probe(folder, chat=None, live=None, quick=False):
    """Run the probes in `folder`. Returns the report as text; nothing is written beside the code."""
    work = os.path.join(folder, "_verifier_probe")
    os.makedirs(work, exist_ok=True)
    sections = [("P-1 Appending to a file, by file size", probe_append(work, (0.1, 1) if quick else (1, 5, 20))),
                ("P-2 Writing .xlsx and .docx directly against build-locally-then-copy", probe_office_files(work)),
                ("P-3 200 small files against one JSON Lines file", probe_many_files(work)),
                ("P-4 Whole-file copy of a large file", probe_large_copy(work, 6 if quick else 60)),
                ("P-5 Replace onto an existing file", probe_replace(work))]
    visible = os.path.join(folder, "verifier_probe_visible.txt")
    with open(visible, "w", encoding="utf-8") as handle:
        handle.write("Written at %s. If you can see this file in the Workspace browser right away, tick P-6.\n" % datetime.datetime.now().isoformat(timespec="seconds"))
    download = os.path.join(work, "copied_probe.xlsx")
    digest = hashlib.sha256(open(download, "rb").read()).hexdigest() if os.path.exists(download) else "the probe workbook could not be written"
    sections += [
        ("P-6 Does a file written by the notebook show at once in the Workspace browser?", ["Look for verifier_probe_visible.txt in the Projects folder. Seen at once: [ ] yes  [ ] no"]),
        ("P-7 Download and upload", ["Download _verifier_probe/copied_probe.xlsx and upload it unchanged into the same folder.", "Its SHA-256 before download: %s" % digest,
                                     "Same SHA-256 after upload: [ ] yes [ ] no. Name the upload got: ________. Was the .xlsx unpacked like a .zip: [ ] yes [ ] no"]),
        ("P-8 Does the token widget accept a string as long as a real token?", ["Paste a real token into the widget, run cell 1, and compare the length it reports with the token's length: [ ] same [ ] cut"]),
        ("P-9 Mode A: does changing the token widget re-run cell 1 by itself while a background run works?", ["Start cell 4 in mode A with the stand-in, paste another token, run cell 4 again: token age went back to zero by itself: [ ] yes [ ] no"]),
        ("P-10 Mode B: the same with cell 1 run by hand", ["Token age went back to zero after running cell 1 by hand: [ ] yes [ ] no"]),
        ("P-11 For information: widgets seen from inside a running loop", ["dbutils.widgets.get inside a foreground loop saw a changed value: [ ] yes [ ] no"]),
        ("P-12 Optional: does a trivial Spark action from the background thread keep the cluster alive?", ["Cluster stayed up past its auto-termination time during a background run: [ ] yes [ ] no [ ] not tried"]),
        ("P-13 What chat() returns or raises with an empty token", probe_chat(chat, live) if chat else ["chat() was not given to the probe; run it from the notebook after cell 2."]),
        ("P-14 Which folder on the driver the tool may build a run in", probe_scratch())]
    handle = io.StringIO()
    handle.write("# Environment probe\n\nFolder probed: `%s`. Python %s. Run at %s%s.\n\n" % (
        folder, sys.version.split()[0], datetime.datetime.now().isoformat(timespec="seconds"), " (quick sizes)" if quick else ""))
    for title, lines in sections:
        handle.write("## %s\n\n%s\n\n" % (title, "\n".join("- " + line for line in lines)))
    shutil.rmtree(work, ignore_errors=True)
    return handle.getvalue()

def probe_scratch():
    """Where the driver lets this user write. A cluster is shared, so a scratch folder made by
    one user can refuse another; this says which folder the tool settled on before a run needs it."""
    try:
        return ["the tool would build runs in: %s" % runner.pick_scratch_root()]
    except PermissionError as problem:
        return ["No folder on the driver allowed it. %s" % problem]


# ================================================================================================
# ---------------------------------------------------------------- from tools/reading_report.py
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
    projects = helpers.scratch()
    helpers.copy_sample(sample, projects, "R6", "2026-09-18")
    settings = runner.make_settings({"agentic_reading": mode})
    paths = runner.open_run(projects, "R6", "2026-09-18", scratch_root=helpers.scratch())
    runner.run_pipeline(paths, settings, chat=chat, live=live, stop_after="04")
    store = runner.open_store(paths, settings)
    units = [core.to_plain(unit) for unit in store.read("chunks_canon")]
    units += [core.to_plain(unit) for unit in store.read("chunks_doc")]
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
            "refused": sum(1 for call in calls if str(call.get("outcome") or "").startswith("rejected")),
            "fell_back": sum(1 for call in calls if call.get("final") and str(call.get("outcome") or "").startswith("rejected")),
            "closed": all(account["closed"] for account in accounts),
            "open_files": [account["file"] for account in accounts if not account["closed"]],
            "added": sum(account["injected"] for account in accounts),
            "lost": sum(account["unaccounted"] for account in accounts)}


def run(chat, live=None, samples=HARD + SETTLED, label="the real model"):
    found = {(sample, mode): one_run(sample, mode, chat, live) for sample in samples for mode in MODES}
    lines = report_lines(found, samples, label)
    stamp = datetime.date.today().isoformat()
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
    # Counted from the call records, not inferred. An earlier draft guessed an allowance of calls
    # from the size of a sample, and a dress rehearsal against a misbehaving model passed it: every
    # answer about F_capital's shape was refused, the guided reading silently never happened, and
    # this test said HELD. A refused answer means the prompt and the validator disagree with that
    # model; a question whose last answer was refused means guidance did not happen at all.
    refused = [sample for sample in samples if found[(sample, "rules")]["refused"]]
    return [
        (not nothing_lost, "Nothing is lost and nothing is added, on every file of every sample, in both modes"
                           + ("" if not nothing_lost else ": open on %s" % ", ".join("%s (%s)" % pair for pair in nothing_lost))),
        (not worse, "On the hard samples, guidance is never worse than no guidance"
                    + ("" if not worse else ": worse on %s" % ", ".join(worse))),
        (not moved, "On the settled samples, every measure is the same in both modes"
                    + ("" if not moved else ": moved on %s" % ", ".join(moved))),
        (not refused, "Every question about a file's shape was answered and accepted the first time"
                      + ("" if not refused else ": %s" % ", ".join(
                          "%s %d refused%s" % (sample, found[(sample, "rules")]["refused"],
                                               ", and guidance did not happen on %d file(s)" % found[(sample, "rules")]["fell_back"]
                                               if found[(sample, "rules")]["fell_back"] else "")
                          for sample in refused))),
    ]

def report_lines(found, samples, label):
    stamp = datetime.date.today().isoformat()
    standin = "stand-in" in label
    lines = ["# Reading report: does guided reading earn its place?", "",
             "**Measured %s, engine %s, with %s.**" % (stamp, core.ENGINE_VERSION, label), ""]
    if standin:
        lines += ["> **This run used the stand-in, not a model.** The stand-in reads the digest and applies",
                  "> the rule the prompt describes. It shows the machinery is sound and the vocabularies are",
                  "> safe. It is not evidence about how a model reads an unfamiliar schema, and the sign-off",
                  "> bar below is therefore reported but **not met**. Re-run this file with a real chat() on",
                  "> Databricks to meet it.", ""]
    lines += ["## Per sample, off against rules", "",
              "| Sample | Mode | Phrases | Levels | Chained | Calls | Refused | Tokens | Account |",
              "|---|---|---|---|---|---|---|---|---|"]
    for sample in samples:
        for mode in MODES:
            one = found[(sample, mode)]
            lines.append("| %s | %s | %s | %s | %d/%d | %d | %d | %d | %s |"
                         % (sample, mode,
                            "%d/%d" % (one["phrases"], one["gold"]) if one["gold"] else "-",
                            "%d/%d" % (one["levels"], one["wanted"]) if one["wanted"] else "-",
                            one["chained"], one["units"], one["calls"], one["refused"], one["tokens"],
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
    """One row per sample and mode in the shared history file."""
    for sample in samples:
        for mode in MODES:
            one = found[(sample, mode)]
            remember("reading", stamp, sample, "stand-in" if "stand-in" in label else "live", mode=mode,
                     phrases=one["phrases"], gold=one["gold"], levels=one["levels"], wanted=one["wanted"],
                     chained=one["chained"], units=one["units"], calls=one["calls"], tokens=one["tokens"],
                     lost=one["lost"], added=one["added"])


# ================================================================================================
# ---------------------------------------------------------------- from tools/count_lines.py
# A budget keeps a module reviewable. core.py and runner.py also hold data that was once in
# engine/references: the prompts (about 250 lines) and the workbook layout (about 140), so their
# budgets are raised by that much and no more. reading.py rose by 100 for the SVG reader (text in any
# nesting, HTML in foreignObject, pictures inside SVGs, charts read in place where the XML refers to them),
# and by 350 for the data flow of a package, the implementation map's backbone.
# review.py rose by 350 for concepts: extracting them, joining their forms, the two questions about
# them and the search signal that puts them first.
# runner.py rose by 100 for the implementation map's sheet and the final outputs a person decides there,
# and by 250 more for the map itself: the tree, its IDs and groups, and its three branches.
# review.py rose by 300 more for the skill map-implementation: the Tracer's tools, turns and validator, and the Namer.
BUDGETS = {"verifier.py": 9000}
MINIMUM_EXPLANATION_SHARE = 0.30


def explanation_lines(source):
    """Line numbers that hold a docstring or a comment."""
    lines = set()
    previous = None
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            lines.add(token.start[0])
        if token.type == tokenize.STRING and (previous is None or previous.type in (
                tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.DEDENT, tokenize.ENCODING)):
            lines.update(range(token.start[0], token.end[0] + 1))
        if token.type not in (tokenize.NL, tokenize.COMMENT):
            previous = token
    return lines


def count(path):
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    total = source.count("\n") + (0 if source.endswith("\n") else 1)
    blank = sum(1 for line in source.split("\n") if not line.strip())
    explained = len(explanation_lines(source))
    return {"total": total, "explained": explained, "share": explained / max(1, total - blank), "blank": blank}


def report():
    rows, within = [], True
    for name, budget in BUDGETS.items():
        result = count(os.path.join(ENGINE, name))
        result.update(name=name, budget=budget, ok=result["total"] <= budget)
        within = within and result["ok"]
        rows.append(result)
    return rows, within


# ================================================================================================
# ---------------------------------------------------------------- from tools/make_release_manifest.py
if os.path.join(ROOT, "engine") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "engine"))

PATTERNS = ("engine/*.py", "engine/pipeline.yaml", "engine/requirements.txt", "Verifier.ipynb")


def current():
    files = {}
    for pattern in PATTERNS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern), recursive=True)):
            if os.path.isfile(path) and "__pycache__" not in path:
                with open(path, "rb") as handle:
                    files[os.path.relpath(path, ROOT).replace(os.sep, "/")] = hashlib.sha256(handle.read()).hexdigest()
    with open(os.path.join(ROOT, "engine", "requirements.txt"), encoding="utf-8") as handle:
        requirements = [line.strip() for line in handle if line.strip() and not line.startswith("#")]
    return {"engine_version": core.ENGINE_VERSION, "files": files, "requirements": requirements}




# ================================================================================================
# ---------------------------------------------------------------- the implementation map: what the reader recovers
def map_measure(sample="J_pipeline", record=True, chat=None):
    """How much of a sample's answer key (gold_map.yaml) the traced data flow holds, part by part. A value's
    sources are read through the calls that compute it: base_score comes from the three columns weighted_score
    is given. Raw inputs are the leaves of the walk down from each final output. What the map says of the
    documents is read from its branches 91 and 92, on a whole run with the stand-in. Returns {part: (found, total)}."""
    import helpers
    import verifier
    import yaml
    with open(os.path.join(SAMPLES, sample, "gold_map.yaml"), encoding="utf-8") as handle:
        gold = yaml.safe_load(handle)
    import standin_chat
    paths, settings, _ = helpers.run_sample(sample, chat=chat or standin_chat.chat_well_behaved)   # the whole run: the map's branches need links
    store = runner.open_store(paths, settings)
    flow, mapped = store.read("dataflow"), runner.implementation_map(store, settings)
    canon = {c["ref"]: c for c in store.read("chunks_canon")}
    doc = {c["ref"]: c for c in store.read("chunks_doc")}
    missing = runner.not_on_the_map(store, mapped, settings)
    nodes = {r["node"]: r for r in flow if r["record_type"] == "node"}
    roots = next(r for r in flow if r["record_type"] == "roots")
    calls = {(r["function"], r["callee"]) for r in nodes.values() if r["kind"] == "call"}
    def direct(node_id):
        """The names a value is computed from, through the calls that compute it."""
        names = set()
        for source in nodes.get(node_id, {}).get("from", []):
            inner = nodes.get(source, {})
            if inner.get("kind") == "call":
                names |= {nodes.get(s, {}).get("name", s) for s in inner["from"] if s != "%s:return" % inner["callee"]}
            else:
                names.add(inner.get("name", source))
        return names
    leaves = set()
    for output in gold["final_outputs"]:
        leaves |= reading.walk_dataflow(flow, output)[0]
    leaf_names = {kind: {nodes[leaf]["name"] for leaf in leaves if leaf in nodes and nodes[leaf]["kind"] == kind}
                  for kind in ("argument", "column", "stored data", "file", "number")}
    gaps = [r for r in flow if r["record_type"] == "gap"]
    raw = gold["raw_inputs"]
    found = {
        "final outputs and not-reached functions among the candidates code finds":
            (len(set(roots["proposed"]) & set(gold["final_outputs"])) + len(set(roots["not_reached"]) & set(gold["not_reached"])),
             len(gold["final_outputs"]) + len(gold["not_reached"])),
        "calls between package functions": (sum((caller, callee) in calls for caller, callees in gold["calls"].items() for callee in callees),
                                            sum(len(callees) for callees in gold["calls"].values())),
        "values within a function, with what each is computed from":
            (sum(source in direct("%s:%s" % (f, v)) for f, flows in gold["flows"].items() for v, sources in flows.items() for source in sources),
             sum(len(sources) for flows in gold["flows"].values() for sources in flows.values())),
        "columns a dplyr verb creates, with what each is computed from":
            (sum(source in direct("column:%s" % column) for column, sources in gold["columns"].items() for source in sources),
             sum(len(sources) for sources in gold["columns"].values())),
        "raw inputs: arguments of a final output": (len(set(raw["argument"]) & leaf_names["argument"]), len(raw["argument"])),
        "raw inputs: columns of an argument": (len(set(raw["column_of_an_argument"]) & leaf_names["column"]), len(raw["column_of_an_argument"])),
        "raw inputs: stored data": (len(set(raw["stored_data"]) & leaf_names["stored data"]), len(raw["stored_data"])),
        "raw inputs: files": (len(set(raw["file"]) & leaf_names["file"]), len(raw["file"])),
        "raw inputs: hard-coded numbers": (len(set(raw["hard_coded_number"]) & leaf_names["number"]), len(raw["hard_coded_number"])),
        "gaps named, for the agents": (sum(any(g["function"] == gap["function"] and gap["code"] in g["code"] for g in gaps) for gap in gold["gaps"]),
                                       len(gold["gaps"])),
        "methodology no step implements": (sum(any(heading in " > ".join(canon[ref]["heading_chain"]) for ref in missing["methodology"])
                                               for heading in gold["methodology_not_implemented"]), len(gold["methodology_not_implemented"])),
        "documentation describing nothing in the map": (sum(any(words in doc[ref]["text"] for ref in missing["documentation"])
                                                            for words in gold["documentation_describing_nothing"]),
                                                        len(gold["documentation_describing_nothing"])),
        "gaps on the path traced by the agents": (sum(1 for t in store.read("map_traces") if t["status"].startswith("traced")),
                                                  len(store.read("map_traces"))),
        "no more in those two counts than the answer key": (int(len(missing["methodology"]) + len(missing["documentation"]) <=
                                                                 len(gold["methodology_not_implemented"]) + len(gold["documentation_describing_nothing"])), 1)}
    if record:
        remember("map-measure", datetime.date.today().isoformat(), sample, "no model",
                 **{re.sub(r"\W+", "_", part.split(",")[0])[:40]: "%d/%d" % pair for part, pair in found.items()})
    return found


def map_baseline_text(found):
    width = max(len(part) for part in found)
    return "\n".join("%-*s %2d of %2d" % (width, part, got, total) for part, (got, total) in found.items())


# ================================================================================================
# ---------------------------------------------------------------- the sign-off bar of the map's agents
MAP_BAR_SAMPLES = ("J_pipeline", "F_capital")

def map_run(sample, chat, live=None, settings=None):
    """One run of a sample to the end of the map's agents, with what the bar measures: the traces, the
    names, the questions refused, any link whose quote is not in the code, and the shape of the tree."""
    import helpers
    projects = helpers.scratch()
    helpers.copy_sample(sample, projects, "BAR", "2026-01-01")
    run_settings = runner.make_settings(dict({}, **(settings or {})))
    paths = runner.open_run(projects, "BAR", "2026-01-01", scratch_root=helpers.scratch())
    runner.run_pipeline(paths, run_settings, chat=chat, live=live, stop_after="07d")
    store = runner.open_store(paths, run_settings)
    text = {u["ref"]: u["text"] for u in store.read("model_units")}
    traces = store.read("map_traces")
    unquoted = [(t["gap"]["function"], edge["value"]) for t in traces for edge in t["edges"]
                if edge["quote"] not in text.get(t["gap"]["function_ref"], "")]
    asked = [call for call in store.read_calls() if call["question_type"] == "trace-gap"]
    rows = runner.implementation_map(store, run_settings)
    return {"traces": traces, "steps": len(rows),
            "questions": len({call["question_id"] for call in asked}),
            "refused": len({call["question_id"] for call in asked if call["final"] and call["outcome"] != "accepted"}),
            "unquoted": unquoted,
            "open": [(t["gap"]["function"], t["status"]) for t in traces if not t["status"].startswith(("traced", "the code cannot tell"))],
            "shape": [(row["map_id"], row["role"], row["output_variable"], row["ov_ref"], row["function_name"]) for row in rows]}

def map_bar(found, measured):
    """The four tests of the map's sign-off bar, each as (held, what it says)."""
    unquoted = [(sample, pair) for sample, one in found.items() for pair in one["unquoted"]]
    moved = [sample for sample, one in found.items() if one["shape"] != one["shape_without_a_model"]]
    refused = [(sample, one["refused"], one["questions"]) for sample, one in found.items() if one["refused"]]
    open_gaps = [(sample, gap) for sample, one in found.items() for gap in one["open"]]
    missing = ["%s: %s of %s" % (part, got, total) for part, (got, total) in measured.items() if got != total]
    return [
        (not missing, "The map holds every part of J_pipeline's answer key" + ("" if not missing else ": %s" % "; ".join(missing))),
        (not unquoted, "Every link the AI declared quotes the code word for word"
                       + ("" if not unquoted else ": %s" % "; ".join("%s %s" % pair for pair in unquoted))),
        (not moved, "The shape of the map is the same as with no model at all: code decides it"
                    + ("" if not moved else ": moved on %s" % ", ".join(moved))),
        (not refused and not open_gaps,
         "Every question the agents asked was answered and accepted the first time, and every gap on the path ends traced or "
         "with a reason" + ("" if not refused and not open_gaps else ": %s" % "; ".join(
             ["%s %d of %d questions refused" % triple for triple in refused] + ["%s %s" % pair for sample, pair in open_gaps])))]

def map_report(chat, live=None, samples=MAP_BAR_SAMPLES, label="the real model"):
    """The sign-off bar of the map's agents, run against a chat(). The map is built by code; the agents
    only close the gaps code names, and every link they declare quotes the code. This says whether that holds with the model you use. Returns the report as text."""
    import standin_chat
    found = {}
    for sample in samples:
        one = map_run(sample, chat, live)
        one["shape_without_a_model"] = map_run(sample, standin_chat.chat_well_behaved, settings={"map_with_ai": False})["shape"]
        found[sample] = one
    measured = map_measure("J_pipeline", record=False, chat=chat)
    stamp, standin = datetime.date.today().isoformat(), "stand-in" in label
    lines = ["# The Model Implementation Map: do its agents earn their place?", "",
             "**Measured %s, engine %s, with %s.**" % (stamp, core.ENGINE_VERSION, label), ""]
    if standin:
        lines += ["> **This run used the stand-in, not a model.** It shows the machinery is sound: the actions are",
                  "> refused unless they quote the code, the shape of the map comes from code, and a run replays. It is",
                  "> not evidence about how a model traces a gap it has never seen, and the bar below is therefore",
                  "> reported but **not met**. Run it again from cell 5 with APPENDIX = \"map-sign-off\" on Databricks.", ""]
    lines += ["## Per sample", "", "| Sample | Rows of the map | Questions | Refused | Gaps open | Links not quoted |",
              "|---|---|---|---|---|---|"]
    for sample, one in found.items():
        lines.append("| %s | %d | %d | %d | %d | %d |" % (sample, one["steps"], one["questions"], one["refused"],
                                                          len(one["open"]), len(one["unquoted"])))
    lines += ["", "## The answer key", "", "| Part | Found |", "|---|---|"]
    lines += ["| %s | %d of %d |" % (part, got, total) for part, (got, total) in measured.items()]
    lines += ["", "## The bar", ""]
    held = map_bar(found, measured)
    lines += ["- **%s** %s" % ("HELD" if ok else "NOT HELD", says) for ok, says in held]
    lines += ["", "**The bar is %s.**" % ("met" if all(ok for ok, _ in held) and not standin else
                                          "reported but NOT met: it was run with the stand-in, not a model" if standin else "NOT met")]
    remember("map-bar", stamp, ", ".join(samples), "stand-in" if standin else "the real model",
             held=sum(ok for ok, _ in held), of=len(held), refused=sum(one["refused"] for one in found.values()),
             gaps_open=sum(len(one["open"]) for one in found.values()), steps=sum(one["steps"] for one in found.values()))
    return "\n".join(lines)


# ================================================================================================
# ---------------------------------------------------------------- the manual against the code
def manual_problems():
    """Every way the one manual can drift from the code, as plain sentences. The manual may name
    a function (`module.name`), a sheet, a test, a setting or a design rule; each must exist, and
    every setting and every design rule must be explained. An empty list means they agree."""
    import verifier
    text = open(MANUAL, encoding="utf-8").read()
    found = []
    import verifier
    modules = {"core": core, "reading": reading, "review": review, "runner": runner, "develop": sys.modules[__name__]}
    for module, name in sorted(set(re.findall(r"`(core|reading|review|runner|develop)\.([A-Za-z_]\w*)`", text))):
        if name == "py":
            continue                                 # `verifier.py` names the file, not a function
        if not hasattr(modules[module], name):
            found.append("the manual names `%s.%s`, which does not exist" % (module, name))
    sheets = {sheet["name"] for sheet in runner.load_layout()["sheets"]}
    for sheet in sorted(set(re.findall(r"`([A-Z][A-Za-z_]+)`", text))):
        if sheet.endswith("_") or sheet in sheets or not re.match(r"^[A-Z][a-z]+_[A-Z]", sheet):
            continue
        found.append("the manual names a sheet `%s` that Output.xlsx does not have" % sheet)
    for setting in sorted(runner.DEFAULT_SETTINGS):
        if setting not in text:
            found.append("setting '%s' is not explained in the manual" % setting)
    for rule in ("R%d" % n for n in range(1, 15)):
        if not re.search(r"\| %s \|" % rule, text):
            found.append("design rule %s has no row in the manual" % rule)
    for step in runner.load_pipeline()["steps"]:
        if step["name"] not in text:
            found.append("step '%s' is not mentioned in the manual" % step["name"])
    for message in ("cell 1", "cell 2", "cell 3", "cell 4", "cell 5"):
        if message not in text.lower():
            found.append("the manual never mentions %s of the notebook" % message)
    # a file the manual names by its path in the repository, or a test file by its name, must exist:
    # a restructure that moves or renames a file otherwise leaves the manual pointing at nothing
    for path in sorted(set(re.findall(r"`((?:engine|docs|tools|evaluation)/[\w./*-]+)`", text))):
        if not glob.glob(os.path.join(os.path.dirname(ENGINE), path)):
            found.append("the manual names `%s`, which is not in the repository" % path)
    for name in sorted(set(re.findall(r"`(test_\w+\.py)`", text))):
        if not os.path.exists(os.path.join(TESTS, name)):
            found.append("the manual names the test file `%s`, which does not exist" % name)
    banned = core.has_banned_wording(text)
    if banned:
        found.append("the manual uses the banned word '%s'" % banned)
    return found


def check_docs():
    problems = manual_problems()
    print("\n".join(problems) if problems else "check-docs: the manual and the code agree.")
    return 1 if problems else 0


# ================================================================================================
# ---------------------------------------------------------------- the notebook, five cells
CELL_1 = r'''# ===== Cell 1 of 4 - set up: widgets, packages, the engine =====
# Run this first, and run it again after anything restarts Python. It is safe to run any number of times.
import importlib, importlib.metadata, importlib.util, os, re, subprocess, sys, tempfile

def notebook_folder():
    try:
        path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        return os.path.dirname(path if path.startswith("/Workspace") else "/Workspace" + path)
    except Exception:
        return os.getcwd()

HOME = notebook_folder()
ALLOW_DEFAULT_INDEX = False        # True only on a cluster meant to install from pip's own default index

# --- widgets: made before anything is installed, so this cell can run on a bare cluster
w = dbutils.widgets
def widget(name, default, label):
    try:
        return w.get(name)
    except Exception:
        w.text(name, default, label)
        return default
widget("llm_endpoint", "", "01 LLM endpoint"); widget("llm_token", "", "02 LLM token")
widget("reviewer_id", "", "03 Your user id (reviewer id, and the id sent to the LLM)")
widget("model_id", "", "04 Model ID"); widget("project", "", "05 Project date (empty = new project today)"); widget("run", "", "06 Run (empty = new run)")
widget("projects_dir", os.path.join(HOME, "Projects"), "07 Projects folder"); widget("jfrog_index_url", "", "08 Package index URL")
widget("concurrency_limit", "4", "09 Concurrency limit"); widget("token_cap", "40000", "10 Token cap")
widget("scratch_dir", "", "11 Scratch folder (usually empty)")
widget("concept_subject", "", "12 Subject of the documents, for concepts (e.g. financial)")
widget("flowr_archive", "", "13 flowR archive (empty = the pinned release from GitHub)")
for old_widget in ("llm_user_id", "reviewer_role"):      # widgets of an earlier notebook, no longer used
    try:
        w.remove(old_widget)
    except Exception:
        pass

# --- packages: installed only if one is missing, pinned to what the runtime already has, and Python
# is restarted only if the runtime's own packages still import together afterwards
REQUIRED = ("yaml", "openpyxl", "numpy", "rdata")   # what the engine imports; docx, scipy and sympy went with the checks
missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
if missing:
    index_url = w.get("jfrog_index_url").strip()
    requirements = os.path.join(HOME, "engine", "requirements.txt")
    if not index_url and not ALLOW_DEFAULT_INDEX:
        print("Packages missing:", ", ".join(missing), "- paste the package index URL into widget 08 and run this cell again.")
        print("Nothing is installed from an index you did not name. To use pip's default index, set ALLOW_DEFAULT_INDEX = True above.")
    else:
        pins = []
        for name in ("numpy", "pandas", "pyarrow", "scipy"):
            try:
                pins.append("%s==%s" % (name, importlib.metadata.version(name)))
            except importlib.metadata.PackageNotFoundError:
                pass
        constraints = os.path.join(tempfile.mkdtemp(prefix="verifier_"), "constraints.txt")
        open(constraints, "w").write("\n".join(pins) + "\n")
        hide = lambda text: re.sub(r"//[^/@\s]+@", "//...@", text or "")
        command = [sys.executable, "-m", "pip", "install", "-r", requirements, "-c", constraints] + (["--index-url", index_url] if index_url else [])
        print("Installing", ", ".join(missing), "| kept as the runtime has them:", ", ".join(pins) or "none found")
        done = subprocess.run(command, capture_output=True, text=True)
        if done.returncode:
            print("The install did not finish. What pip said:\n" + hide(done.stderr)[-1500:])
            print("If pip found no versions that fit, the index lacks an older version that works with this runtime's own packages. Nothing the runtime depends on was changed.")
        else:
            wanted = open(requirements, encoding="utf-8").read().split("# --- optional ---")
            if len(wanted) > 1:
                spare = os.path.join(tempfile.gettempdir(), "optional.txt")
                open(spare, "w", encoding="utf-8").write(wanted[1])
                extra = subprocess.run(command[:4] + ["-r", spare] + command[6:], capture_output=True, text=True)
                print("Optional packages (words inside pictures):", "installed." if not extra.returncode else "not installed; pictures of text will say so.")
            probe = subprocess.run([sys.executable, "-c", "import numpy, pandas, pyarrow"], capture_output=True, text=True)
            if probe.returncode:
                print("STOPPED BEFORE RESTARTING PYTHON: the runtime's own packages no longer import together (%s)." % hide((probe.stderr or "").strip().splitlines()[-1]))
                print("Restarting now would crash this notebook session. Detach this notebook from the cluster and attach it again to undo the install. Do not restart the cluster.")
            else:
                still = subprocess.run([sys.executable, "-c", "import " + ", ".join(missing)],
                                       capture_output=True, text=True)
                if still.returncode:
                    print("STOPPED BEFORE RESTARTING PYTHON: %s is still missing after the install, so restarting "
                          "would only bring this cell back here." % ", ".join(missing))
                    print("What Python said:\n" + hide(still.stderr)[-600:])
                    print("Check that engine/requirements.txt names it, and that the index in widget 08 carries it.")
                else:
                    print("Installed. Restarting Python; then run this cell once more.")
                    dbutils.library.restartPython()
else:
    # --- the engine
    for folder in (os.path.join(HOME, "engine"), os.path.join(HOME, "engine", "tests")):
        if folder not in sys.path:
            sys.path.insert(0, folder)
    import verifier
    if "LIVE" not in globals():
        LIVE = verifier.LiveValues()
    LIVE.update(w.get("llm_endpoint"), w.get("llm_token"), w.get("reviewer_id"))
    def live(name):
        """Read an endpoint, token or user id at the moment chat() is CALLED, so a fresh token pasted mid-run is used."""
        return LIVE.get(name)

    def current_settings():
        return verifier.make_settings({"concurrency_limit": int(w.get("concurrency_limit") or 4), "token_cap": int(w.get("token_cap") or 40000),
                                     "reviewer_id": w.get("reviewer_id"), "concept_subject": w.get("concept_subject").strip(),
                                     "flowr_archive": w.get("flowr_archive").strip()})

    def open_current():
        """The run the widgets name, opened; or None with a message when the project has no inputs yet. Used
        by cells 3, 4 and 5, so that a cell run before cell 3 - or after Python restarted - says what to do."""
        _, missing = verifier.setup_project(w.get("projects_dir"), w.get("model_id"), w.get("project"))
        if missing:
            print("\n".join(missing)); print("Put the files in, then run cell 3.")
            return None
        if globals().get("PATHS") is not None and PATHS.model_id == w.get("model_id") and (not w.get("project") or PATHS.project_date == w.get("project")) and (not w.get("run") or PATHS.run_id == w.get("run")):
            return PATHS                               # keep working on the run this session opened
        return verifier.open_run(w.get("projects_dir"), w.get("model_id"), w.get("project"), w.get("run"), scratch_root=w.get("scratch_dir"))
    print("Folder:", HOME, "| Python", sys.version.split()[0], "| engine", verifier.ENGINE_VERSION)
    for name in REQUIRED + ("pdfplumber", "pypdf"):
        try:
            print("  %-11s %s" % (name, getattr(importlib.import_module(name), "__version__", "installed")))
        except Exception:
            print("  %-11s not installed%s" % (name, "" if name in ("pdfplumber", "pypdf") else " - run this cell again"))
    token = LIVE.get("llm_token")
    print("Endpoint set:", bool(LIVE.get("llm_endpoint")), "| token:", ("%d characters, pasted %.1f minutes ago" % (len(token), LIVE.token_age_minutes())) if token else "none pasted yet")
    try:                                            # flowR reads the R code: fetched once, checked against its pinned SHA-256
        print("flowR %s ready in %s" % (verifier.FLOWR_VERSION, verifier.flowr_ready(w.get("flowr_archive").strip())))
    except Exception as problem:
        print("flowR IS NOT READY (%s). Without internet, download %s on an approved machine, put it in a Volume,"
              " and give its path in widget 13." % (problem, verifier.FLOWR_URL.format(verifier.FLOWR_VERSION)))
    print("")
    print("THE ENGINE IS READY. What happens next:")
    print("  Cell 2  paste your organisation's chat(), check it answers, and see where to put your files.")
    print("  Cell 3  read the inputs and run the review; it prints what each step did.")
    print("  Cell 4  check the finished run folder against its own record.")
    print("Widgets 01 to 03 carry the endpoint, the token and your user id; widget 04 the model id, 05 the")
    print("project date, 07 the projects folder. Paste a fresh token into widget 02 at any time - it is read")
    print("at the moment each call is made, so a run already working picks it up.")
    print("Next: cell 2.")
'''

CELL_2 = r'''# ===== Cell 2 of 4 - your chat(), and where your files go =====
# Paste your organisation's chat() below. It must return {"answer": "<the model's reply>"}. Read the endpoint,
# token and user id with live("...") INSIDE the function, so that a fresh token pasted into the widget is
# used mid-run. This cell asks it one question, then makes the project's Inputs folders and names them.
import requests

def chat(SystemPrompt, MainPrompt, history=[]):
    payload = {
        "app": "sparkair",
        "enable_streaming": False,
        "flow_name": "general_chat",
        "history": history,
        "optionalParameter": {
            "maxtoken": 250000,
            "contextlength": 250000,
            "Temperature": 0.01,           # low: the same question gives the same answer
            "Top_k": 1,
            "Penalty": 1.1,
            "DefaultPrompt": SystemPrompt,
        },
        "query": MainPrompt,
        "select_all": False,
    }
    headers = {
        "Authorization": f'Bearer {live("llm_token")}',
        "SP_SSO_UID": live("reviewer_id"),
        "Content-Type": "application/json",
    }
    response = requests.post(live("llm_endpoint"), json=payload, headers=headers, timeout=180)
    response.raise_for_status()
    return response.json()          # the engine reads the reply from "answer", or from an OpenAI-shaped "choices"

ACTIVE_CHAT = chat
try:
    reply = ACTIVE_CHAT("Reply with the single word OK.", "Reply with the single word OK.")["answer"]
    print("chat() answered:", str(reply)[:60])
except Exception as problem:
    print("chat() did not answer (%s: %s). Check widgets 01, 02 and 03, then run this cell again."
          % (type(problem).__name__, problem))
else:
    project_dir, missing = verifier.setup_project(w.get("projects_dir"), w.get("model_id"), w.get("project"))
    print("\nPUT YOUR FILES IN THESE THREE FOLDERS, then run cell 3:")
    for _, folder, note in verifier.INPUT_FOLDERS:
        print("  %s" % os.path.join(project_dir, "Inputs", folder))
        print("      %s" % note)
    print("\nOne methodology file, the model package as it ships (.tar.gz, .zip or the unpacked folder), and the")
    print("model documentation. A folder with nothing in it stops the run and says so, rather than reading around it.")
    if missing:
        print("\nStill empty: " + "; ".join(missing))
    else:
        print("\nAll three folders have files in them. Next: cell 3.")
'''

CELL_3 = r'''# ===== Cell 3 of 4 - read the inputs and run the review =====
# Reads every input file, maps how the model computes what it returns, then asks your model to interpret the
# code, name the concepts, close the gaps code could not follow, and judge every link. It runs here, in this
# cell, and prints what each step did. A step that has already finished is never repeated: run the cell again
# after a token expires or a cluster restarts and it carries on where it stopped.
FOREGROUND_MINUTES = 600      # how long this cell may work before it stops by itself and asks you to run it again

PATHS = open_current()
if PATHS is not None:
    SETTINGS = dict(current_settings(), foreground_minutes=float(FOREGROUND_MINUTES))
    STATE = verifier.AskState()
    RESULT = verifier.run_pipeline(PATHS, SETTINGS, chat=ACTIVE_CHAT, live=LIVE, state=STATE)
    print(RESULT["message"])
    store = verifier.open_store(PATHS, SETTINGS)
    print("\nWhat each step did:")
    for record in store.read("step_records"):
        print("  step %s %-14s %s" % (record["step_id"], record["name"],
                                      ", ".join("%s: %s" % item for item in sorted((record["counts"] or {}).items()))))
        for message in record["messages"]:
            print("      " + message)
    for label, value in verifier.call_statistics(store):
        print("  %-52s %s" % (label, value))
    if STATE.waiting_for_token:
        print("\nWAITING FOR A FRESH TOKEN: the gateway refused the last call. Paste a new token into widget 02 and")
        print("run this cell again; the steps already finished are not repeated.")
    print("\nRun folder:", PATHS.run_dir)
    print("Open Output.xlsx there: the three Chunks sheets show everything that was read, Concepts the model's own")
    print("names, Model_Implementation_Map how it computes what it returns, and Mapping_Coverage what is covered.")
    print("Then run cell 4 to check the run folder against its own record.")
'''

CELL_4 = r'''# ===== Cell 4 of 4 - check the run folder against its own record =====
# The inputs are the files that were read, the engine is the one that produced the run, re-reading the inputs
# gives the same content, the graph chain verifies, and no access token was written anywhere in the folder.
if "PATHS" not in globals() or PATHS is None:
    print("Cell 3 has not read the inputs yet. Run cell 3 first.")
else:
    SETTINGS = current_settings()
    print("Verifying the evidence pack:")
    for what, verdict, detail in verifier.verify_evidence_pack(PATHS, SETTINGS, live=LIVE):
        print("  %-62s %-16s %s" % (what, verdict, detail))
    print("\nRun folder:", PATHS.run_dir, "- Output.xlsx is the deliverable; _audit/Audit_Log.xlsx is the record")
    print("of the run: every step, every record, and every exchange with the model.")
'''



# ====================================================================================
# ---------------------------------------------------------------- the engine's own map
# The tool mapped the model it reviews; this maps the tool. Everything here is read from
# verifier.py by its syntax tree - nothing is listed by hand, so the map cannot drift from the
# code. It is written as a workbook laid out like Output.xlsx: an inventory of every function,
# the same flow drawn as a tree from each thing the tool produces, the file's sections, and the
# records that carry work from one step to the next.
ENGINE_FILE = os.path.join(ENGINE, "verifier.py")
MAP_ID_COLUMNS = 10
ENGINE_ROOTS = [("01 prepare-run", "prepare_run"), ("02 read-inputs", "read_inputs"), ("03 build-map", "build_map"),
                ("05 read-with-ai", "read_with_ai"), ("06 link-units", "link_units"),
                ("Output.xlsx", "build_workbook"), ("Cell 4 confirms the outline", "confirm_outline"),
                ("Cell 5 verifies the pack", "verify_evidence_pack"), ("The run itself", "run_pipeline"),
                ("Cell 3 opens the run", "open_run"), ("The settings a cell makes", "make_settings"),
                ("Replaying a run from its record", "replay_chat")]

def engine_facts():
    """Every function of verifier.py, what it calls, what calls it, where it lives and what it
    does - read from the file's syntax tree and its section headers."""
    source = open(ENGINE_FILE, encoding="utf-8").read()
    lines = source.split("\n")
    tree = ast.parse(source)
    sections = [(number, line.split("- ")[-1].strip()) for number, line in enumerate(lines, start=1)
                if line.startswith("# " + "-" * 20)]
    def section_of(line_number):
        found = [title for start, title in sections if start <= line_number]
        return found[-1] if found else "(the top of the file)"
    facts = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            continue
        body = "\n".join(lines[node.lineno - 1:node.end_lineno])
        said = ast.get_docstring(node) or ""
        facts[node.name] = {
            "name": node.name, "kind": "class" if isinstance(node, ast.ClassDef) else "function",
            "first_line": node.lineno, "last_line": node.end_lineno, "size": node.end_lineno - node.lineno + 1,
            "section": section_of(node.lineno), "body": body,
            "says": " ".join(said.split("\n")[0].split())[:300] or "(no description)",
            "asks_the_model": "load_prompt(" in body or "ctx.ask(" in body or "state.ask(" in body,
            "checks_an_answer": node.name.startswith("validate") or "Rejected(" in body,
            "writes": sorted(set(re.findall(r'"([a-z_]+)":\s*(?:\[|list\()', "".join(re.findall(r"StepResult\((\{.*?\})", body, re.S))))),
            "reads": sorted(set(re.findall(r'read\("([a-z_]+)"\)', body))),
        }
    for name, fact in facts.items():
        # a name used at all, not only called with brackets: a step that hands another step to combine()
        # refers to it by name, and that is a call as much as any other
        fact["calls"] = sorted(other for other in facts if other != name
                               and re.search(r"(?<![\w.])%s(?![\w])" % re.escape(other), fact["body"]))
    for name in facts:
        facts[name]["called_by"] = sorted(other for other in facts if name in facts[other]["calls"])
    for number, name in enumerate(sorted(facts), start=1):
        facts[name]["ref"] = "F-%04d" % number
    return facts, sections, len(lines)

def reached_from(facts, root):
    """Every function the work of one root reaches, following the calls."""
    seen, queue = {root} & set(facts), [root] if root in facts else []
    while queue:
        for child in facts[queue.pop()]["calls"]:
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen

def engine_tree(facts, rows_max=4000):
    """The same call flow as a tree: each thing the tool produces, then what it calls, and what
    those call, numbered so that sorting the ID columns gives the tree back. A function already
    shown is one row pointing at where it stands in full; a function that calls itself stops."""
    rows, shown = [], {}
    def emit(name, map_id, level, path):
        if len(rows) >= rows_max or name not in facts:
            return
        fact = facts[name]
        note = ""
        if name in path:
            note = "calls itself; the descent stops here"
        elif name in shown:
            note = "shown in full at %s" % shown[name]
        row = {"map_id": map_id, "level": level, "function": name, "ref": fact["ref"], "section": fact["section"],
               "lines": "%d-%d" % (fact["first_line"], fact["last_line"]), "size": fact["size"],
               "says": fact["says"], "calls": "; ".join(fact["calls"]), "note": note}
        for position, part in enumerate(map_id.split(".")[:MAP_ID_COLUMNS], start=1):
            row["id%d" % position] = part
        rows.append(row)
        if note:
            return
        shown[name] = map_id
        width = max(2, len(str(len(fact["calls"]))))
        for position, child in enumerate(fact["calls"], start=1):
            emit(child, "%s.%0*d" % (map_id, width, position), level + 1, path | {name})
    for number, (label, root) in enumerate(ENGINE_ROOTS, start=1):
        if root in facts:
            emit(root, "%02d" % number, 0, frozenset())
            rows[[r["map_id"] for r in rows].index("%02d" % number)]["says"] = \
                "%s - %s" % (label, facts[root]["says"])
    return rows

def build_engine_map(target=None):
    """Write the engine's own map as a workbook: Engine_Info, Functions, Function_Map, Sections
    and Records. Laid out like Output.xlsx - frozen headers, filters, grouped rows, and a
    reference in one sheet linking to its row in another."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.hyperlink import Hyperlink
    facts, sections, total_lines = engine_facts()
    tree = engine_tree(facts)
    target = target or os.path.join(os.path.dirname(ENGINE), "Engine_Map.xlsx")
    book = openpyxl.Workbook()
    book.remove(book.active)
    blue, green, orange = "D9E1F2", "E2EFDA", "FCE4D6"
    def sheet_of(name, headers, rows, widths, colours):
        sheet = book.create_sheet(name)
        for number, (header, width, colour) in enumerate(zip(headers, widths, colours), start=1):
            cell = sheet.cell(row=1, column=number, value=header)
            cell.font, cell.fill = Font(bold=True), PatternFill("solid", start_color=colour)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            sheet.column_dimensions[get_column_letter(number)].width = width
        for row_number, row in enumerate(rows, start=2):
            for number, value in enumerate(row, start=1):
                cell = sheet.cell(row=row_number, column=number, value=value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.freeze_panes = "B2"
        sheet.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(headers)), max(1, len(rows) + 1))
        return sheet
    # --- what this workbook is
    roots = [label for label, root in ENGINE_ROOTS if root in facts]
    info = [("The file", "engine/verifier.py", "%d lines, %d functions and classes, %d sections" %
             (total_lines, len(facts), len(sections))),
            ("Functions", "one row each", "what it does, where it lives, what it calls and what calls it"),
            ("Function_Map", "the same flow as a tree", "from each thing the tool produces (%s) down to the "
             "functions that do the work; sorting the ID columns gives the tree back" % ", ".join(roots[:4]) + ", …"),
            ("Sections", "the file's own headings", "how many lines and functions each holds"),
            ("Records", "what carries work between steps", "each kind of record, which function writes it and which read it"),
            ("How to read a row of Function_Map", "one function a row",
             "indented under the function that calls it; a function already shown points at where it stands in full"),
            ("Where it comes from", "read from the code",
             "every row is read from verifier.py by its syntax tree, so this map cannot drift from the code")]
    sheet_of("Engine_Info", ["What", "Item", "Detail"], info, [34, 30, 96], [blue, blue, green])
    # --- the inventory
    order = sorted(facts, key=lambda name: facts[name]["first_line"])
    rows = [(facts[name]["ref"], name, facts[name]["kind"], facts[name]["section"],
             "%d-%d" % (facts[name]["first_line"], facts[name]["last_line"]), facts[name]["size"],
             facts[name]["says"], "; ".join(facts[name]["calls"]), "; ".join(facts[name]["called_by"]),
             "; ".join(label for label, root in ENGINE_ROOTS if name in reached_from(facts, root)),
             "asks the model" if facts[name]["asks_the_model"] else "checks an answer" if facts[name]["checks_an_answer"] else "")
            for name in order]
    functions = sheet_of("Functions", ["Ref", "Function", "Kind", "Section", "Lines", "Size", "What it does",
                                       "Calls", "Called by", "Reached from", "Where the model enters"],
                         rows, [10, 30, 10, 40, 14, 8, 80, 50, 50, 50, 20],
                         [blue, blue, blue, blue, blue, blue, green, orange, orange, orange, orange])
    where = {facts[name]["ref"]: number for number, name in enumerate(order, start=2)}
    # --- the tree
    headers = ["MapID%d" % n for n in range(1, MAP_ID_COLUMNS + 1)] + \
              ["Level", "Function", "Function ref", "Section", "Lines", "Size", "What it does", "Calls", "Note"]
    body = [tuple(row.get("id%d" % n, "") for n in range(1, MAP_ID_COLUMNS + 1)) +
            (row["level"], row["function"], row["ref"], row["section"], row["lines"], row["size"],
             row["says"], row["calls"], row["note"]) for row in tree]
    map_sheet = sheet_of("Function_Map", headers, body,
                         [7] * MAP_ID_COLUMNS + [7, 30, 12, 34, 14, 8, 70, 44, 34],
                         [blue] * MAP_ID_COLUMNS + [blue, blue, orange, blue, blue, blue, green, orange, orange])
    map_sheet.sheet_properties.outlinePr.summaryBelow = False
    map_sheet.column_dimensions.group(get_column_letter(1), get_column_letter(MAP_ID_COLUMNS), outline_level=1)
    at_function = MAP_ID_COLUMNS + 2
    for number, row in enumerate(tree, start=2):
        if row["level"]:
            map_sheet.row_dimensions[number].outline_level = min(row["level"], 7)
        map_sheet.cell(row=number, column=at_function).alignment = Alignment(wrap_text=True, vertical="top",
                                                                            indent=min(row["level"], 15))
        cell = map_sheet.cell(row=number, column=at_function + 1)
        if cell.value in where:
            cell.hyperlink = Hyperlink(ref=cell.coordinate, location="'Functions'!A%d" % where[cell.value])
            cell.style = "Hyperlink"
    for number, name in enumerate(order, start=2):
        cell = functions.cell(row=number, column=1)
        first = next((row for row in tree if row["function"] == name and not row["note"]), None)
        if first:
            cell.hyperlink = Hyperlink(ref=cell.coordinate, location="'Function_Map'!A%d" %
                                       (2 + [row["function"] for row in tree].index(name)))
            cell.style = "Hyperlink"
    # --- the file's own sections
    bounds = sections + [(total_lines + 1, "")]
    section_rows = []
    for (start, title), (nxt, _) in zip(sections, bounds[1:]):
        inside = [name for name in facts if start <= facts[name]["first_line"] < nxt]
        section_rows.append((title, start, nxt - start, len(inside), "; ".join(sorted(inside))[:300]))
    sheet_of("Sections", ["Section", "First line", "Lines", "Functions", "Which functions"],
             sorted(section_rows, key=lambda row: row[1]), [54, 12, 10, 12, 90], [blue, blue, blue, blue, green])
    # --- what carries work from step to step
    kinds = sorted({kind for fact in facts.values() for kind in fact["writes"] + fact["reads"]})
    record_rows = [(kind,
                    "; ".join(sorted(name for name in facts if kind in facts[name]["writes"])),
                    "; ".join(sorted(name for name in facts if kind in facts[name]["reads"]))) for kind in kinds]
    sheet_of("Records", ["Record kind", "Written by", "Read by"], record_rows, [30, 46, 80], [blue, orange, green])
    book.save(target)
    return target, len(facts), len(tree)

def build_notebook(target=NOTEBOOK):
    """The notebook, four cells, written from the sources above so that it is never edited by hand."""
    cells = [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.splitlines(keepends=True)}
             for text in (CELL_1, CELL_2, CELL_3, CELL_4)]
    notebook = {"cells": cells, "metadata": {"language_info": {"name": "python"},
                                             "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
                "nbformat": 4, "nbformat_minor": 5}
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(notebook, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    return target


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "budgets"
    if what == "budgets":
        rows, within = report()
        print("%-12s %6s %7s %10s %s" % ("file", "lines", "budget", "explained", "status"))
        for row in rows:
            print("%-12s %6d %7d %9.0f%% %s" % (row["name"], row["total"], row["budget"], 100 * row["share"], "within budget" if row["ok"] else "OVER BUDGET"))
        sys.exit(0 if within else 1)
    if what == "check-docs":
        sys.exit(check_docs())
    if what == "engine-map":
        where, functions, rows = build_engine_map()
        print("%s: %d functions, %d rows of the tree" % (where, functions, rows))
    if what == "notebook":
        print(build_notebook(), "with 4 cells")
    if what == "recall":
        recall(sys.argv[2:] or ["A_minimal", "F_capital"])
    if what == "map-bar":
        import standin_chat
        print(map_report(standin_chat.chat_well_behaved, label="the stand-in"))
    if what == "map-measure":
        print(map_baseline_text(map_measure(sys.argv[2] if len(sys.argv) > 2 else "J_pipeline")))
    if what == "reading-report":
        import standin_chat
        print(run(standin_chat.chat_well_behaved, label="the stand-in"))
