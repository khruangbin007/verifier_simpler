"""golden.py capture FILE | compare FILE: every sample's Output.xlsm, audit records and _Audit files, with what differs
from run to run by nature masked - run ids, times, durations, local folders, the engine's own fingerprint."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import sys, os, re, json, glob, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier, openpyxl
from harness import Gateway, attach, open_sample, run_until_done
SAMPLES = ["A_minimal", "D_dosing", "F_capital", "F_capital_known", "G_schema", "H_twocolumn", "I_wordtraps", "J_pipeline"]
TIMEY = re.compile(r"(^|_)(seconds|sent_at|returned_at|written_at|started|finished|at|when|stamp|time|elapsed|opened|engine\w*|run_id|bytes|sha256)$")
def mask(value, key=""):
    if isinstance(value, dict):
        return {k: ("<masked>" if TIMEY.search(k) else mask(v, k)) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [mask(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"\d{4}-\d{2}-\d{2}_\d{4}[a-z]?", "<run>", value)
        value = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?", "<time>", value)
        value = re.sub(r"/tmp/[\w./-]+", "<dir>", value)
        return re.sub(r"\b\d+(\.\d+)? seconds?\b", "<n> seconds", value)
    return value
def capture_one(sample):
    settings = verifier.make_settings({})
    paths = open_sample(sample, settings)
    attach(Gateway(delay=(0, 0.001)))
    states = run_until_done(paths, settings)
    store = verifier.open_store(paths, settings)
    kinds = ["run_manifest", "step_records", "chunks_canon", "chunks_doc", "model_units", "package_info", "info_rows", "read_repairs", "unit_links", "llm_calls", "audit_files"]
    records = {}
    for kind in kinds:
        try:
            records[kind] = mask(store.read(kind))
        except Exception as problem:
            records[kind] = "unreadable: %s" % type(problem).__name__
    book = openpyxl.load_workbook(os.path.join(paths.project_dir, verifier.OUTPUT_FILE))
    sheets = {ws.title: [[mask(c.value) for c in row] for row in ws.iter_rows()
                         if not (ws.title == "Model_Package_Info" and row[0].value == "Identity")] for ws in book.worksheets}
    links = {ws.title: sorted(mask("%s>%s" % (c.coordinate, c.hyperlink.location or c.hyperlink.target)) for row in ws.iter_rows() for c in row if c.hyperlink) for ws in book.worksheets}
    audit = os.path.join(paths.project_dir, verifier.AUDIT_FOLDER)
    files = {}
    for path in sorted(glob.glob(audit + "/*/*.json")):
        files[os.path.relpath(path, audit)] = mask(json.load(open(path)))
    return {"states": states, "sheets": sheets, "links": links, "records": records, "files": files}
def first_differences(a, b, where="", out=None, most=6):
    out = [] if out is None else out
    if len(out) >= most: return out
    if type(a) != type(b):
        out.append("%s: %r != %r" % (where, str(a)[:120], str(b)[:120])); return out
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append("%s/%s: only in %s" % (where, k, "before" if k in a else "after"))
            else:
                first_differences(a[k], b[k], where + "/" + str(k), out, most)
            if len(out) >= most: break
    elif isinstance(a, list):
        if len(a) != len(b): out.append("%s: %d items != %d" % (where, len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            first_differences(x, y, "%s[%d]" % (where, i), out, most)
            if len(out) >= most: break
    elif a != b:
        out.append("%s: %r != %r" % (where, str(a)[:160], str(b)[:160]))
    return out
if __name__ == "__main__":
    mode, target = sys.argv[1], sys.argv[2]
    found = {sample: capture_one(sample) for sample in SAMPLES}
    if mode == "capture":
        json.dump(found, open(target, "w")); print("captured", {s: (len(v["records"]), len(v["files"]), sum(len(r) for r in v["sheets"].values())) for s, v in found.items()})
    else:
        base = json.load(open(target)); same = 0
        for sample in SAMPLES:
            diffs = first_differences(base[sample], json.loads(json.dumps(found[sample])), sample)
            same += not diffs
            for d in diffs: print("  DIFF", d[:300])
        print("identical: %d of %d samples" % (same, len(SAMPLES)))
