"""ask_all when every question is refused: with the model otherwise answering, the step goes on and each question ends
unanswered; in an outage, where the short question goes unanswered too, the step stops as before."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, tempfile, threading, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier
from harness import attach, Gateway
verifier.CHAT_BACKOFF = 0.01 if hasattr(verifier, "CHAT_BACKOFF") else None
class Paths: pass
def run(outage):
    paths = Paths(); paths.local_dir = tempfile.mkdtemp()
    ctx = verifier.StepContext(settings=verifier.make_settings({"parallel_chats": 4}), options={"paths": paths}, read=lambda kind: [],
                               work_dir=tempfile.mkdtemp(), note=lambda *a: None, provenance=verifier.Provenance("r", "05", "search-methodology"))
    asked = {"questions": 0, "checks": 0}; lock = threading.Lock()
    def chat(system, main, history=()):
        with lock:
            if system == verifier.STILL_ANSWERING:
                asked["checks"] += 1
                return {"error": "503 Service Unavailable"} if outage else {"answer": "OK"}
            asked["questions"] += 1
        return {"error": "413 the request is too large"}           # every question refused
    attach(Gateway(delay=(0, 0.001)))
    work = [{"id": "q%02d" % n, "type": "methodology search", "unit_ref": "M-%04d" % n, "system": "s", "main": "question %d" % n} for n in range(30)]
    taken, stopped, peak = verifier.ask_all(ctx, chat, work, lambda item: item, lambda question: None, types=("methodology search",))
    checks = [(c["question_type"], c["outcome"]) for c in ctx.checks]
    print("%-28s stopped: %-5s | questions ended: %2d of 30, answered %d | short questions asked: %d, recorded: %s | exchange files: %d"
          % ("an outage" if outage else "every question refused", bool(stopped), len(taken), sum(1 for _, r in taken if r["answer"]), asked["checks"], checks[:2], len(ctx.exchanges)))
run(outage=False)
run(outage=True)
print("the main thread still reads the widgets (not marked a worker):", not getattr(verifier.CHAT_WORKER, "active", False))
