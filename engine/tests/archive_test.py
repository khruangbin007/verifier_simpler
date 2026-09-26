import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, shutil, tempfile, warnings, hashlib, openpyxl
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier
from harness import Gateway, SETTINGS, attach
def tree(root):
    return {os.path.relpath(os.path.join(b, n), root): hashlib.sha256(open(os.path.join(b, n), "rb").read()).hexdigest()
            for b, _, ns in os.walk(root) for n in ns}
root = tempfile.mkdtemp()
project = os.path.join(root, "Projects", "ARC")
shutil.copytree(SAMPLES + "/D_dosing/Inputs", project, dirs_exist_ok=True)
attach(Gateway(delay=(0, 0.002)))
runs = []
for number, cap in enumerate((200.0, 199.0, 198.0)):             # a setting changed: each time a new run
    settings = verifier.make_settings({"max_file_mb": cap}); SETTINGS[0] = settings
    before = {**{"_Audit/" + k: v for k, v in tree(os.path.join(project, "_Audit")).items() if not k.startswith("previous_runs")},
              **({"Output.xlsm": tree(project)["Output.xlsm"]} if os.path.exists(os.path.join(project, "Output.xlsm")) else {})}
    paths = verifier.open_run(os.path.join(root, "Projects"), "ARC", scratch_root=tempfile.mkdtemp(), settings=settings)
    print("run %d opened: %s" % (number + 1, paths.opened[:230]))
    if runs:
        kept = os.path.join(project, "_Audit", "previous_runs", runs[-1])
        after = {("_Audit/" + k if k != "Output.xlsm" else k): v for k, v in tree(kept).items()}
        print("   kept in previous_runs/%s: %d files, byte for byte the run before: %s" % (runs[-1], len(after), after == before))
    verifier.run_pipeline(paths, settings)
    runs.append(paths.run_id)
print("_Audit now:", sorted(os.listdir(os.path.join(project, "_Audit"))), "| previous_runs:", sorted(os.listdir(os.path.join(project, "_Audit", "previous_runs"))))
checks = verifier.verify_evidence_pack(paths, settings, live=verifier.NOTEBOOK["live"])
print("cell 4 on the current run: %d of %d confirmed | inventory check: %s" % (sum(v == "Confirmed" for _, v, _ in checks), len(checks), checks[-1][2]))
book = openpyxl.load_workbook(os.path.join(project, "_Audit", "Audit_Log.xlsx"), read_only=True)
print("Steps sheet:", [r[:2] for r in list(book["Steps"].iter_rows(values_only=True))[1:]])
files = list(book["Files"].iter_rows(values_only=True))
print("Files header:", files[0])
row = next(r for r in files[1:] if "code-interpretation" in r[2])
print("an exchange:", row[2], "| about:", row[4], "| sent", row[5], "| returned", row[6])
