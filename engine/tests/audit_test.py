import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, json, shutil, tempfile, warnings, collections
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier, openpyxl
from harness import Gateway, SETTINGS, attach, run_until_done
root = tempfile.mkdtemp()
project = os.path.join(root, "Projects", "AUD")
shutil.copytree(SAMPLES + "/F_capital/Inputs", project, dirs_exist_ok=True)
settings = verifier.make_settings({}); SETTINGS[0] = settings
paths = verifier.open_run(os.path.join(root, "Projects"), "AUD", scratch_root=tempfile.mkdtemp(), settings=settings)
attach(Gateway(delay=(0, 0.002)))
print("states:", run_until_done(paths, settings))
audit = os.path.join(project, "_Audit")
print("project folder:", sorted(os.listdir(project)))
print("_Audit:", sorted(os.listdir(audit)))
for folder in sorted(f for f in os.listdir(audit) if os.path.isdir(os.path.join(audit, f))):
    names = sorted(os.listdir(os.path.join(audit, folder)))
    print("  %-22s %4d files: %s ... %s" % (folder, len(names), names[0], names[-1]))
book = openpyxl.load_workbook(os.path.join(audit, "Audit_Log.xlsx"), read_only=True)
print("sheets:", book.sheetnames)
rows = list(book["Files"].iter_rows(values_only=True))
print("Files header:", rows[0]); print("   first:", rows[1][:4]); print("   last: ", rows[-1][:4])
on_disk = sorted(os.path.relpath(os.path.join(b, n), audit).replace(os.sep, "/") for b, _, ns in os.walk(audit) for n in ns if n.endswith(".json"))
print("inventory = files on disk:", sorted(r[2] for r in rows[1:]) == on_disk, len(on_disk), "| numbers 1..n in order:", [r[0] for r in rows[1:]] == list(range(1, len(rows))))
chat = next(r[2] for r in rows[1:] if "methodology-comparison" in r[2])
exchange = json.load(open(os.path.join(audit, chat)))
print("a chat file:", chat, "| keys:", sorted(exchange)[:14])
print("   SystemPrompt starts:", exchange["chat_input"]["SystemPrompt"][:60].replace("\n", " "), "| MainPrompt chars:", len(exchange["chat_input"]["MainPrompt"]), "| answer chars:", len(exchange["chat_output"]["answer"]), "| sent", exchange["sent_at"], "returned", exchange["returned_at"])
checks = verifier.verify_evidence_pack(paths, settings, live=verifier.NOTEBOOK["live"])
for what, verdict, detail in checks[-3:]:
    print("  %-70s %s %s" % (what, verdict, detail))
print("checks confirmed: %d of %d" % (sum(v == "Confirmed" for _, v, _ in checks), len(checks)))
