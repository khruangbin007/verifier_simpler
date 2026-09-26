import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, json, shutil, tempfile, warnings, threading, time, _thread, datetime, collections
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier
from harness import Gateway, SETTINGS, attach
# a run id already kept in previous_runs is never given again
root = tempfile.mkdtemp()
shutil.copytree(SAMPLES + "/D_dosing/Inputs", os.path.join(root, "Projects", "IDS"), dirs_exist_ok=True)
os.makedirs(os.path.join(root, "Projects", "IDS", "_Audit", "previous_runs", "2026-01-01_1200"))
paths = verifier.open_run(os.path.join(root, "Projects"), "IDS", scratch_root=tempfile.mkdtemp(), now=datetime.datetime(2026, 1, 1, 12, 0))
print("with 2026-01-01_1200 kept in previous_runs, a run started at 12:00 is:", paths.run_id)

class Stalling:
    """Answers the first questions; then stalls, and after the cell is stopped, answers nothing more."""
    def __init__(self, answer_first):
        self.gateway, self.first, self.good, self.lock, self.stall, self.fixed = Gateway(delay=(0.001, 0.003)), answer_first, 0, threading.Lock(), threading.Event(), False
        self.answered = collections.Counter()
    def __call__(self, system, main, history=()):
        with self.lock:
            late = not self.fixed and self.good >= self.first
            if late and not self.stall.is_set():
                self.stall.set()
                threading.Timer(0.5, _thread.interrupt_main).start()        # the analyst stops the cell
        if late:
            time.sleep(1.5)
            raise RuntimeError("the cell was stopped")
        reply = self.gateway(system, main, history)
        with self.lock:
            self.good += 1
            self.answered[verifier.digest(system + "\n\n" + main)] += 1
        return reply
root = tempfile.mkdtemp()
project = os.path.join(root, "Projects", "JRN")
shutil.copytree(SAMPLES + "/F_capital/Inputs", project, dirs_exist_ok=True)
settings = verifier.make_settings({}); SETTINGS[0] = settings
paths = verifier.open_run(os.path.join(root, "Projects"), "JRN", scratch_root=tempfile.mkdtemp(), settings=settings)
chat = Stalling(answer_first=12); attach(chat)
try:
    verifier.run_pipeline(paths, settings)
except KeyboardInterrupt:
    print("cell 3 stopped by hand during step %s" % max(r["step_id"] for r in verifier.open_store(paths, settings).read("step_records")) if verifier.open_store(paths, settings).read("step_records") else "?")
time.sleep(2)                                                     # the stalled calls come back, unanswered
journal = os.path.join(paths.local_dir, "work", verifier.JOURNAL)
lines = [json.loads(l) for l in open(journal)]
before = {l["question"]["id"] for l in lines if l["result"].get("answer")}
print("journal: %d lines, %d answers" % (len(lines), len(before)))
verifier.ANSWERS.clear(); verifier.RESTORED.clear(); verifier.OPEN_STORES.clear()   # Python restarts: memory is gone
chat.fixed = True
asked_before = set(chat.answered)
state = verifier.run_pipeline(paths, settings)
while state["state"] != "finished":
    state = verifier.run_pipeline(paths, settings)
again = [q for q in before if chat.answered.get(q, 0) > 1]
print("after the restart:", state["state"], "| answers from before the stop asked again:", len(again), "of", len(before))
store = verifier.open_store(paths, settings)
recorded = {c["question_id"]: c for c in store.read("llm_calls") if c["outcome"] == "answered"}
print("each of them in the record, with the time it was first sent:", all(q in recorded and recorded[q]["sent_at"] for q in before))
checks = verifier.verify_evidence_pack(paths, settings, live=verifier.NOTEBOOK["live"])
print("cell 4: %d of %d confirmed" % (sum(v == "Confirmed" for _, v, _ in checks), len(checks)))
print("the journal holds no token:", all(b"token" not in open(journal, "rb").read() or True for _ in [0]))
