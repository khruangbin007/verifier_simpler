"""Words once banned are now kept as the model wrote them: no answer is asked again for them, and no cell is withheld
for them. Technical text - a Python trace, an internal name - is still kept out of the workbook (R10)."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, warnings, collections
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier, openpyxl
from harness import Gateway, SETTINGS, attach, open_sample, run_until_done
settings = verifier.make_settings({})
paths = open_sample("F_capital", settings)
gateway = Gateway(words=1.0, delay=(0, 0.002)); attach(gateway)
states = run_until_done(paths, settings)
store = verifier.open_store(paths, settings)
calls = store.read("llm_calls")
reasked = [line for c in calls for line in c["what happened"] if "technical text" in line or "words" in line]
book = openpyxl.load_workbook(os.path.join(paths.project_dir, verifier.OUTPUT_FILE), read_only=True)
cells = [str(c) for row in book["Flagged_Items"].iter_rows(min_row=2, values_only=True) for c in row if c]
print("states:", states, "| questions:", len(calls), "| chat calls:", gateway.calls)
print("answers asked again for words:", len(reasked), "| cells keeping 'major departure':", sum("major departure" in c for c in cells),
      "| cells withheld anywhere:", sum(verifier.CELL_WITHHELD in str(c) for s in book.sheetnames for row in book[s].iter_rows(values_only=True) for c in row if c))
print("the gate:", repr(verifier.plain_cell("A critical error of high severity, a major finding", False, store)[:60]), "|",
      repr(verifier.plain_cell("It raised ValueError: bad input", False, store)[:60]))
