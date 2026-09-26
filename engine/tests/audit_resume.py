import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, json, shutil, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier, openpyxl
from harness import Gateway, SETTINGS, attach, TOKEN
class Flaky:
    """A gateway that goes down after some answers, echoing the token in its error, until it is fixed."""
    def __init__(self, after):
        self.gateway, self.after, self.good, self.fixed = Gateway(delay=(0, 0.002)), after, 0, False
    def __call__(self, system, main, history=()):
        if not self.fixed and self.good >= self.after:
            raise RuntimeError("503 Service Unavailable (token %s)" % verifier.live("llm_token"))
        reply = self.gateway(system, main, history)
        self.good += 1
        return reply
root = tempfile.mkdtemp()
project = os.path.join(root, "Projects", "RES")
shutil.copytree(SAMPLES + "/F_capital/Inputs", project, dirs_exist_ok=True)
settings = verifier.make_settings({}); SETTINGS[0] = settings
paths = verifier.open_run(os.path.join(root, "Projects"), "RES", scratch_root=tempfile.mkdtemp(), settings=settings)
chat = Flaky(after=25); attach(chat)
first = verifier.run_pipeline(paths, settings)
chat.fixed = True
second = verifier.run_pipeline(paths, settings)
print("first run:", first, "| after the fix:", second)
folder = os.path.join(project, "_Audit", "05_search-methodology")
names = sorted(os.listdir(folder))
steps = [n for n in names if "_step_attempt-" in n]
print("05 folder: %d files; the step's records: %s" % (len(names), steps))
outcomes = [(n[:4], json.load(open(os.path.join(folder, n))).get("outcome")) for n in names if "_step_" not in n]
cut = int(steps[0][:4])
print("  before attempt 1's record: %d exchanges, %s" % (sum(1 for n, _ in outcomes if int(n) < cut), sorted(set(o for n, o in outcomes if int(n) < cut))))
print("  after it, up to attempt 2's: %d exchanges, %s" % (sum(1 for n, _ in outcomes if int(n) > cut), sorted(set(o for n, o in outcomes if int(n) > cut))))
checks = verifier.verify_evidence_pack(paths, settings, live=verifier.NOTEBOOK["live"])
print("checks: %d of %d confirmed | token check: %s | inventory check: %s" % (sum(v == "Confirmed" for _, v, _ in checks), len(checks), checks[-2][1], checks[-1][1]))
hits = [os.path.relpath(os.path.join(b, n), project) for b, _, ns in os.walk(os.path.join(project, "_Audit")) for n in ns
        if TOKEN.encode() in open(os.path.join(b, n), "rb").read()]
fault = [n for n in names if "503" in open(os.path.join(folder, n), encoding="utf-8").read()]
print("files naming the 503: %d, e.g. %s | files holding the token: %s" % (len(fault), fault[:1], hits or "none"))
# a project laid out before: Audit_Log.xlsx at its root, the run carried on from it
os.rename(os.path.join(project, "_Audit", "Audit_Log.xlsx"), os.path.join(project, "Audit_Log.xlsx"))
shutil.rmtree(os.path.join(project, "_Audit"))
verifier.OPEN_STORES.clear()
again = verifier.open_run(os.path.join(root, "Projects"), "RES", scratch_root=tempfile.mkdtemp(), settings=settings)
print("root Audit_Log.xlsx moved:", os.path.exists(os.path.join(project, "_Audit", "Audit_Log.xlsx")) and not os.path.exists(os.path.join(project, "Audit_Log.xlsx")),
      "| opened:", again.opened[:70])
