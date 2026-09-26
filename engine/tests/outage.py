"""Outages of chat() in the middle of a run, then every cell run again once chat() works: nothing answered before
the outage is asked again, and the workbook comes out as a run without an outage."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, json, shutil, glob, threading, collections, time, io, contextlib, _thread
home = "/tmp/outage"
shutil.rmtree(home, ignore_errors=True); os.makedirs(home)
repo = REPO
shutil.copytree(os.path.join(repo, "engine"), os.path.join(home, "engine"), dirs_exist_ok=True); shutil.copy(os.path.join(repo, "Verifier.ipynb"), home)
for staged in glob.glob(os.path.join(FLOWR_ARCHIVES or "/nonexistent", "flowr-*.tar.gz")): shutil.copy(staged, home)
os.chdir(home); os.environ["ENGINE"] = os.path.join(home, "engine"); sys.path.insert(0, TESTS)
from harness import Gateway, DBUtils, SETTINGS
import verifier, openpyxl
verifier.notebook_folder = lambda d: home
cells = ["".join(c["source"]) for c in json.load(open("Verifier.ipynb"))["cells"] if c["cell_type"] == "code"]
dbutils = DBUtils()
class Chain:
    def __getattr__(self, name): return self
    def __call__(self, *a): return self
    def get(self): return "reviewer@example.com"
class Library:
    def restartPython(self): print("(restartPython)")
dbutils.notebook, dbutils.library = Chain(), Library()
namespace = {"dbutils": dbutils}

class OrganisationChat:
    """chat() as an organisation writes it: the token read from widget 02 at call time; a gateway that can be down
    (503), or that stops accepting a token when it expires (an error, no "answer")."""
    def __init__(self, gateway, how, after):
        self.gateway, self.how, self.after, self.lock = gateway, how, after, threading.Lock()
        self.good, self.down, self.valid, self.fixed = 0, False, {"token-1"}, False
        self.answers = collections.Counter()           # (system, main) -> answers given
        self.on_first_failure = None
    def __call__(self, system, main, history=()):
        with self.lock:
            if not self.fixed and self.good >= self.after:
                if self.how == "503": self.down = True
                if self.how == "expired": self.valid.discard("token-1")
            down, valid = self.down, verifier.live("llm_token") in self.valid
        if down or not valid:
            if self.on_first_failure:
                hook, self.on_first_failure = self.on_first_failure, None
                hook()
            if down:
                raise RuntimeError("503 Server Error: Service Unavailable for url: https://gateway.example/v1/chat")
            return {"error": {"code": 401, "message": "The access token %s has expired." % verifier.live("llm_token")}}
        reply = self.gateway(system, main, history)
        with self.lock:
            self.good += 1
            if system != "Reply with the single word OK.":
                self.answers[(system, main)] += 1
        return reply
    def fix(self):
        with self.lock:
            self.fixed, self.down = True, False
            self.valid.add("token-2")
        if self.how == "expired":
            dbutils.widgets.values["llm_token"] = "token-2"      # the user pastes a new token into widget 02

def cell(index, chat=None):
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            if index == 1:
                verifier.check_chat(chat)                        # cell 2: the user's chat(), then check_chat(chat)
            else:
                exec(cells[index], namespace)
    except KeyboardInterrupt:
        out.write("(the cell was interrupted)\n")
    return out.getvalue()

def project(name):
    dbutils.widgets.values.update({"project_name": name, "llm_token": "token-1"})
    shutil.copytree(SAMPLES + "/F_capital/Inputs", os.path.join(home, "Projects", name), dirs_exist_ok=True)

def model_sheet():
    book = openpyxl.load_workbook(os.path.join(verifier.NOTEBOOK["paths"].project_dir, verifier.OUTPUT_FILE), read_only=True)
    return list(book["Chunks_Model"].iter_rows(values_only=True))

def said_by(text):
    keep = ("did not finish", "stopped answering", "Run cell", "no interpretation", "could not", "interrupted", "Carrying on", "carry on", "Starting")
    return [line.strip() for line in text.splitlines() if any(k in line for k in keep)][:4]

print("=== a run without an outage")
cell(0); project("CLEAN")
clean_chat = OrganisationChat(Gateway(delay=(0.005, 0.02)), "none", 10**9)
cell(1, clean_chat); print(said_by(cell(2))[:1] or "finished")
reference, asked_in_clean = model_sheet(), sum(clean_chat.answers.values())
print("questions answered:", asked_in_clean)

for name, how, after, interrupt, broken_reruns in (("S1_503", "503", 10, False, 1),
                                                    ("S2_token_expired", "expired", 34, False, 0),
                                                    ("S3_503_compare", "503", 52, False, 0),
                                                    ("S4_interrupted", "503", 14, True, 0)):
    print("\n===", name)
    project(name)
    chat = OrganisationChat(Gateway(delay=(0.005, 0.02)), how, after)
    if interrupt:
        chat.on_first_failure = lambda: threading.Timer(1.5, _thread.interrupt_main).start()
    start = time.time()
    cell(0); cell(1, chat); text = cell(2)
    print("cell 3 during the outage (%.0f s):" % (time.time() - start), said_by(text))
    store = verifier.open_store(verifier.NOTEBOOK["paths"], verifier.notebook_settings())
    print("  answers kept: %d recorded in the audit log, %d held in memory" % (
        sum(1 for c in store.read("llm_calls") if c["outcome"] == "answered"),
        len(verifier.ANSWERS.get(verifier.NOTEBOOK["paths"].local_dir) or {})))
    for _ in range(broken_reruns):                              # every cell run again while chat() still fails
        texts = [cell(0), cell(1, chat), cell(2)]
        print("  every cell again, chat() still failing - cell 2:", said_by(texts[1])[:1] or texts[1].strip().splitlines()[:1], "| cell 3:", said_by(texts[2])[:1])
    chat.fix()
    texts = [cell(0), cell(1, chat), cell(2), cell(3)]          # chat() works again: every cell run again
    result = verifier.NOTEBOOK["result"]
    again = {key: n for key, n in chat.answers.items() if n > 1}
    confirmed = texts[3].count("Confirmed") - texts[3].count("Not confirmed")
    print("  after the fix, every cell again: %s | answered questions asked again: %d | Chunks_Model as without an outage: %s | cell 4: %d of 8" % (
        result["state"], len(again), model_sheet() == reference, confirmed))
    print("  said:", said_by(texts[2])[:2])
    everything = "".join(texts) + text
    paths = verifier.NOTEBOOK["paths"]
    files = [os.path.join(paths.project_dir, verifier.OUTPUT_FILE), os.path.join(paths.project_dir, "Audit_Log.xlsx"), os.path.join(paths.local_dir, "run_log.txt")]
    import zipfile
    def holds(path, token):
        data = open(path, "rb").read()
        blobs = [data] + ([zipfile.ZipFile(path).read(n) for n in zipfile.ZipFile(path).namelist()] if zipfile.is_zipfile(path) else [])
        return any(token.encode() in blob for blob in blobs)
    leaked = [os.path.basename(f) for f in files for token in ("token-1", "token-2") if os.path.exists(f) and holds(f, token)]
    print("  a token in what the cells printed: %s | in Output.xlsm, Audit_Log.xlsx or run_log.txt: %s" % (
        "token-1" in everything or "token-2" in everything, leaked or "none"))
