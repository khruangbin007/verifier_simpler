"""A token that expires in cell 3: the cell halts, ends saying what chat() returned (never the token) and to run the whole
notebook again; after a new token and every cell again, the run carries on and finishes. Exits 1 when a check fails."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, json, shutil, glob, threading, io, contextlib, warnings, collections
warnings.filterwarnings("ignore")
home = "/tmp/rerun_audit"
shutil.rmtree(home, ignore_errors=True); os.makedirs(home)
repo = REPO
shutil.copytree(os.path.join(repo, "engine"), os.path.join(home, "engine")); shutil.copy(os.path.join(repo, "Verifier.ipynb"), home)
for staged in glob.glob(os.path.join(FLOWR_ARCHIVES or "/nonexistent", "flowr-*.tar.gz")): shutil.copy(staged, home)
os.chdir(home); sys.path.insert(0, TESTS)
from harness import Gateway, DBUtils
import verifier, openpyxl
verifier.notebook_folder = lambda d: home
cells = ["".join(c["source"]) for c in json.load(open("Verifier.ipynb"))["cells"] if c["cell_type"] == "code"]
dbutils = DBUtils()
class Chain:
    def __getattr__(self, name): return self
    def __call__(self, *a): return self
    def get(self): return "reviewer@example.com"
class Library:
    def restartPython(self): pass
dbutils.notebook, dbutils.library = Chain(), Library()
namespace = {"dbutils": dbutils}
class ExpiringChat:
    """The organisation's chat(): the token read from widget 02 when called; it expires after some answers."""
    def __init__(self, after):
        self.gateway, self.after, self.good, self.lock, self.valid = Gateway(delay=(0.001, 0.004)), after, 0, threading.Lock(), {"pat-1"}
    def __call__(self, system, main, history=()):
        with self.lock:
            if self.good >= self.after:
                self.valid.discard("pat-1")
            ok = verifier.live("llm_token") in self.valid
        if not ok:
            return {"error": {"code": 401, "message": "The access token has expired."}}
        reply = self.gateway(system, main, history)
        with self.lock:
            self.good += 1
        return reply
def cell(index, chat=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        verifier.check_chat(chat) if index == 1 else exec(cells[index], namespace)
    return out.getvalue()
dbutils.widgets.values.update({"project_name": "RERUN", "llm_token": "pat-1"})
shutil.copytree(SAMPLES + "/F_capital/Inputs", os.path.join(home, "Projects", "RERUN"), dirs_exist_ok=True)
chat = ExpiringChat(after=40)
first = [cell(0), cell(1, chat), cell(2)]
said = [l.strip() for l in first[2].splitlines() if "did not finish" in l or "stopped answering" in l]
failed = []
def check(label, ok):
    print("  %-4s %s" % ("ok" if ok else "FAIL", label))
    if not ok:
        failed.append(label)
out3 = first[2]
block = out3[out3.find("STOPPED"):] if "STOPPED" in out3 else ""
check("cell 3 halts and ends with the stop notice, not with cell 4", bool(block) and "run cell 4" not in out3.lower())
check("the notice says what chat() returned", any(l.startswith("What chat() returned: ") and "401" in l for l in block.split("\n")))
check("the token is never shown", "pat-1" not in out3)
check("it says to run the whole notebook again", "Run the whole notebook again, cells 1 to 4" in block)
print("first cell 3:", said[:2])
chat.valid.add("pat-2"); dbutils.widgets.values["llm_token"] = "pat-2"      # a new PAT pasted into widget 02
second = [cell(0), cell(1, chat), cell(2), cell(3)]
print("second cell 3:", [l.strip() for l in second[2].splitlines() if "Carrying on" in l or "A new run" in l or "Every step has run" in l][:2])
audit = os.path.join(home, "Projects", "RERUN", "_Audit")
for folder in sorted(f for f in os.listdir(audit) if os.path.isdir(os.path.join(audit, f))):
    names = sorted(os.listdir(os.path.join(audit, folder)))
    print("  %-22s %3d files, step records: %s" % (folder, len(names), [n for n in names if "_step_" in n or "fault" in n]))
folder = os.path.join(audit, "05_search-methodology")
names = sorted(os.listdir(folder))
steps = [int(n[:4]) for n in names if "_step_attempt-" in n]
calls = [(int(n[:4]), json.load(open(os.path.join(folder, n)))) for n in names if "_step_" not in n]
for label, low, high in (("attempt 1", 0, steps[0]), ("attempt 2", steps[0], steps[1])):
    part = [c for number, c in calls if low < number < high]
    print("  05 %s: %d exchanges, outcomes %s; last error: %s" % (label, len(part), dict(collections.Counter(c["outcome"] for c in part)),
          next((c["technical"][-1][:90] for c in reversed(part) if c.get("technical")), "-")))
ids = collections.Counter(c["question_id"] for _, c in calls)
twice = [q for q, n in ids.items() if n > 1]
print("  questions with more than one file: %d; of those answered in both: %d" % (len(twice), sum(1 for q in twice if sum(1 for _, c in calls if c["question_id"] == q and c["outcome"] == "answered") > 1)))
book = openpyxl.load_workbook(os.path.join(audit, "Audit_Log.xlsx"), read_only=True)
print("  Steps sheet:", [(r[0], r[1]) for r in list(book["Steps"].iter_rows(values_only=True))[1:]])
print("  Files sheet rows:", book["Files"].max_row - 1, "| on disk:", sum(len(os.listdir(os.path.join(audit, f))) for f in os.listdir(audit) if os.path.isdir(os.path.join(audit, f))))
print("  cell 4:", second[3].count("Confirmed") - second[3].count("Not confirmed"), "confirmed |", [l.strip()[:80] for l in second[3].splitlines() if "Not confirmed" in l])
print("  tokens in _Audit:", [p for p in glob.glob(audit + "/**/*", recursive=True) if os.path.isfile(p) and (b"pat-1" in open(p, "rb").read() or b"pat-2" in open(p, "rb").read())] or "none")

check("after a new token and every cell again, every step has run", "Every step has run." in second[2])
check("cell 4 confirms nine checks", second[3].count("Confirmed") - second[3].count("Not confirmed") == 9)
check("no token in the audit folder", not [p for p in glob.glob(audit + "/**/*", recursive=True) if os.path.isfile(p) and (b"pat-1" in open(p, "rb").read() or b"pat-2" in open(p, "rb").read())])
print("%d check(s) failed: %s" % (len(failed), failed) if failed else "every check passed")
sys.exit(1 if failed else 0)
