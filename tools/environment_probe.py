"""environment_probe.py - the environment probes P-1 to P-14 of the build plan (Phase 0).

Run from the notebook's appendix cell "Environment probe" on the Databricks cluster, with the
Projects folder of the Workspace as `folder`. P-1 to P-5 are timed here. P-6 to P-12 need the
analyst's eyes or the notebook's widgets: this tool prepares what it can, and the report has a
line for each where the analyst writes what was seen. P-13 records what chat() returns or raises
with an empty token, so that the wrapper's classifier can be matched to the real shapes.

    from environment_probe import run_probe
    print(run_probe("/Workspace/Users/me/AIVA/Projects", "/Workspace/Users/me/AIVA/docs", chat=chat, live=LIVE))

It also runs on any ordinary folder (`python tools/environment_probe.py <folder> --quick`), which
is how it is tested offline.
"""
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    local = tempfile.mkdtemp(prefix="aiva_probe_")
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
    local = os.path.join(tempfile.mkdtemp(prefix="aiva_probe_"), "large.bin")
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
    import runner
    live = live or runner.LiveValues()
    kept = dict(live.values)
    live.update(kept.get("llm_endpoint", ""), "", kept.get("llm_user_id", ""))
    answer, failure, seen = runner.call_chat(chat, "You answer with one word.", "Say yes.", live)
    live.update(kept.get("llm_endpoint", ""), kept.get("llm_token", ""), kept.get("llm_user_id", ""))
    return ["with an empty token chat() gave: %s" % (("an answer: %r" % answer[:60]) if answer else "no answer"),
            "the wrapper read this as: %s" % (failure or "a normal answer"), "what was seen (tokens removed): %s" % (seen[:300] or "nothing unusual")]


def run_probe(folder, docs_dir, chat=None, live=None, quick=False):
    """Run the probes in `folder` and write docs/environment_probe_<date>.md. Returns the report's path."""
    work = os.path.join(folder, "_aiva_probe")
    os.makedirs(work, exist_ok=True)
    sections = [("P-1 Appending to a file, by file size", probe_append(work, (0.1, 1) if quick else (1, 5, 20))),
                ("P-2 Writing .xlsx and .docx directly against build-locally-then-copy", probe_office_files(work)),
                ("P-3 200 small files against one JSON Lines file", probe_many_files(work)),
                ("P-4 Whole-file copy of a large file", probe_large_copy(work, 6 if quick else 60)),
                ("P-5 Replace onto an existing file", probe_replace(work))]
    visible = os.path.join(folder, "aiva_probe_visible.txt")
    with open(visible, "w", encoding="utf-8") as handle:
        handle.write("Written at %s. If you can see this file in the Workspace browser right away, tick P-6.\n" % datetime.datetime.now().isoformat(timespec="seconds"))
    download = os.path.join(work, "copied_probe.xlsx")
    digest = hashlib.sha256(open(download, "rb").read()).hexdigest() if os.path.exists(download) else "the probe workbook could not be written"
    sections += [
        ("P-6 Does a file written by the notebook show at once in the Workspace browser?", ["Look for aiva_probe_visible.txt in the Projects folder. Seen at once: [ ] yes  [ ] no"]),
        ("P-7 Download and upload", ["Download _aiva_probe/copied_probe.xlsx and upload it unchanged into the same folder.", "Its SHA-256 before download: %s" % digest,
                                     "Same SHA-256 after upload: [ ] yes [ ] no. Name the upload got: ________. Was the .xlsx unpacked like a .zip: [ ] yes [ ] no"]),
        ("P-8 Does the token widget accept a string as long as a real token?", ["Paste a real token into the widget, run cell 5, and compare the length it reports with the token's length: [ ] same [ ] cut"]),
        ("P-9 Mode A: does changing the token widget re-run cell 5 by itself while a background run works?", ["Start cell 12 in mode A with the stand-in, paste another token, run cell 13: token age went back to zero by itself: [ ] yes [ ] no"]),
        ("P-10 Mode B: the same with cell 5 run by hand", ["Token age went back to zero after running cell 5 by hand: [ ] yes [ ] no"]),
        ("P-11 For information: widgets seen from inside a running loop", ["dbutils.widgets.get inside a foreground loop saw a changed value: [ ] yes [ ] no"]),
        ("P-12 Optional: does a trivial Spark action from the background thread keep the cluster alive?", ["Cluster stayed up past its auto-termination time during a background run: [ ] yes [ ] no [ ] not tried"]),
        ("P-13 What chat() returns or raises with an empty token", probe_chat(chat, live) if chat else ["chat() was not given to the probe; run it from the notebook after cell 6."]),
        ("P-14 Which folder on the driver AIVA may build a run in", probe_scratch())]

def probe_scratch():
    """Where the driver lets this user write. A cluster is shared, so a scratch folder made by
    one user can refuse another; this says which folder AIVA settled on before a run needs it."""
    import runner
    try:
        return ["AIVA would build runs in: %s" % runner.pick_scratch_root()]
    except PermissionError as problem:
        return ["No folder on the driver allowed it. %s" % problem]
    os.makedirs(docs_dir, exist_ok=True)
    report = os.path.join(docs_dir, "environment_probe_%s.md" % datetime.date.today().isoformat())
    with open(report, "w", encoding="utf-8") as handle:
        handle.write("# Environment probe\n\nFolder probed: `%s`. Python %s. Run at %s%s.\n\n" % (
            folder, sys.version.split()[0], datetime.datetime.now().isoformat(timespec="seconds"), " (quick sizes)" if quick else ""))
        for title, lines in sections:
            handle.write("## %s\n\n%s\n\n" % (title, "\n".join("- " + line for line in lines)))
    shutil.rmtree(work, ignore_errors=True)
    return report


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else tempfile.mkdtemp(prefix="aiva_probe_folder_")
    print(run_probe(target, os.path.join(target, "docs") if "--quick" in sys.argv else os.path.join(ROOT, "docs"), quick="--quick" in sys.argv))
