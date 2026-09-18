"""build_notebook.py - writes AIVA_Interface.ipynb, the only file an analyst opens (plan 2.14).

Thirteen widgets and eighteen cells. The notebook holds no logic of its own: every cell calls a
function of the engine. Run `python tools/build_notebook.py` after changing anything here.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CELLS = []


def markdown(text):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)})


def code(title, text):
    source = "# ===== %s =====\n%s" % (title, text.strip("\n") + "\n")
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": source.splitlines(keepends=True)})


markdown("""
# AIVA 0.0.1 - AI Verification Assistant

**How to use this notebook.** Run the cells from top to bottom; every cell says in plain words what it did and what comes next.

1. Run cell 2 first: it makes the widgets. Fill in **08 JFrog index URL**, then run cell 3 to install the packages (once per cluster start). Cell 4 loads the engine and checks the environment.
2. Enter the **model ID**. Paste your `chat()` definition into cell 6, the only cell you edit. Paste the LLM endpoint, token and user id into their widgets.
3. Cell 8 creates the project folders. Upload the methodology, the package tarball and the model documentation into the three `Inputs` folders it names.
4. Cell 9 reads the inputs. Open `Outputs/Output.xlsx`, check *Level* and *Section (heading chain)* on sheet `Chunks_Canon` against the methodology's own outline, then run cell 10.
5. Cell 11 shows how many questions will go to `chat()`. Cell 12 runs them; cell 13 shows where the run stands. When the token runs out, paste a fresh one: no question is asked twice.
6. Download `Output.xlsx`, fill the four yellow columns on `Flagged_Items`, upload it into `Outputs/` and run cell 14. Cell 15 verifies the whole evidence pack.

AIVA raises *flagged items* for a person to decide. It rates nothing, and it never changes your input files.
""")

WIDGETS = '\ndef notebook_folder():\n    """The folder this notebook lives in, worked out explicitly (the working directory is not relied on)."""\n    try:\n        path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()\n        return os.path.dirname(path if path.startswith("/Workspace") else "/Workspace" + path)\n    except Exception:\n        return os.getcwd()\n\nAIVA_HOME = notebook_folder()\n\ndef existing(folder):\n    return sorted((n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))), reverse=True) if os.path.isdir(folder) else []\n\ndef make_widgets():\n    """Every widget at the top of the notebook. Nothing here needs an installed package, which is\n    why cell 2 can make them before anything is installed; running it again refreshes the two lists."""\n    w = dbutils.widgets\n    w.text("llm_endpoint", "", "01 LLM endpoint"); w.text("llm_token", "", "02 LLM token"); w.text("llm_user_id", "", "03 LLM user id")\n    w.text("model_id", "", "04 Model ID")\n    projects_dir = os.path.join(AIVA_HOME, "Projects")\n    try:\n        projects_dir = w.get("projects_dir") or projects_dir\n        model_id = w.get("model_id")\n    except Exception:\n        model_id = ""\n    dates = existing(os.path.join(projects_dir, model_id)) if model_id else []\n    w.dropdown("project", "New project, dated today", ["New project, dated today"] + dates, "05 Project")\n    try:\n        chosen = w.get("project")\n    except Exception:\n        chosen = ""\n    runs = [n for n in existing(os.path.join(projects_dir, model_id, chosen)) if n.startswith("Run_")] if model_id and chosen in dates else []\n    w.dropdown("run", runs[0] if runs else "New run", ["New run"] + runs, "06 Run")\n    w.text("projects_dir", projects_dir, "07 Projects folder"); w.text("jfrog_index_url", "", "08 JFrog index URL")\n    w.text("concurrency_limit", "4", "09 Concurrency limit"); w.text("token_cap", "40000", "10 Token cap")\n    w.text("reviewer_id", "", "11 Reviewer id"); w.text("reviewer_role", "", "12 Reviewer role")\n    w.text("scratch_dir", "", "13 Scratch folder (leave empty unless AIVA says it cannot write on the driver)")\n\nmake_widgets()\n'

code("Cell 2 - make the widgets", '''
# RUN THIS FIRST, on a freshly opened notebook and after every cluster start. It makes every widget
# at the top of the notebook and needs nothing installed, so the widgets are there to be filled in
# before anything else happens. Fill in at least "08 JFrog index URL", then run cell 3.
# Run this cell again at any time to refresh the Project and Run lists; it installs nothing.
import os, sys
''' + WIDGETS + '''
print("AIVA folder:", AIVA_HOME)
print("The widgets are at the top of the notebook. Fill in '08 JFrog index URL', then run cell 3.")
''')

code("Cell 3 - install the packages from the JFrog index, then restart Python", r"""
# Once per cluster start. The index URL is the widget "08 JFrog index URL" that cell 2 made.
# Restarting Python clears every name, so cell 4 sets the import path up again afterwards.
import os, re, subprocess, sys

ALLOW_DEFAULT_INDEX = False      # True only on a cluster meant to install from pip's own default index

index_url = dbutils.widgets.get("jfrog_index_url").strip()
here = os.getcwd()
requirements = next((p for p in (os.path.join(here, "engine", "requirements.txt"), os.path.join(os.path.dirname(here), "engine", "requirements.txt")) if os.path.exists(p)), "")
hide = lambda text: re.sub(r"//[^/@\s]+@", "//...@", text or "")        # an index URL can carry a credential

if not requirements:
    print("requirements.txt was not found beside the notebook. Nothing was installed.")
elif not index_url and not ALLOW_DEFAULT_INDEX:
    print("No index URL yet, so nothing was installed: packages are never taken from an index you did not name.")
    print("Paste it into the widget '08 JFrog index URL' at the top of this notebook, then run this cell again.")
    print("To use pip's own default index instead, set ALLOW_DEFAULT_INDEX = True above.")
else:
    command = [sys.executable, "-m", "pip", "install", "-r", requirements] + (["--index-url", index_url] if index_url else [])
    print("Installing", requirements, "from", "the index in the widget." if index_url else "pip's own default index.")
    done = subprocess.run(command, capture_output=True, text=True)
    print(hide(done.stdout)[-1500:])
    if done.returncode:
        print("The install did not finish, so do not go on to cell 4. What pip said:")
        print(hide(done.stderr)[-1500:])
    else:
        try:
            dbutils.library.restartPython()
        except Exception:
            print("Please restart the Python process by hand, then go on with cell 4.")
""")

code("Cell 4 - the import path, the engine, and preflight", '''
# Cell 3 restarts Python, which clears everything, so the notebook's folder is worked out again here.
# Each cell imports what it uses, so that the order cells are run in does not matter.
import importlib, os, shutil, sys, tempfile

def notebook_folder():
    """The folder this notebook lives in, worked out explicitly (the working directory is not relied on)."""
    try:
        path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        return os.path.dirname(path if path.startswith("/Workspace") else "/Workspace" + path)
    except Exception:
        return os.getcwd()

AIVA_HOME = notebook_folder()
for folder in (os.path.join(AIVA_HOME, "engine"), os.path.join(AIVA_HOME, "engine", "tests"), os.path.join(AIVA_HOME, "tools")):
    if folder not in sys.path:
        sys.path.insert(0, folder)
import aiva5_run_report as aiva

print("AIVA folder:", AIVA_HOME)
print("Python", sys.version.split()[0])
for name in ("yaml", "openpyxl", "docx", "numpy", "scipy", "sympy", "pdfplumber", "pypdf", "rdata"):
    try:
        module = importlib.import_module(name)
        print("  %-11s %s" % (name, getattr(module, "__version__", "installed")))
    except Exception:
        print("  %-11s is NOT installed: run cell 3" % name)
projects_dir = dbutils.widgets.get("projects_dir")
os.makedirs(projects_dir, exist_ok=True)
probe = os.path.join(projects_dir, "aiva_preflight.txt")
try:
    with open(probe, "w") as handle:
        handle.write("preflight")
    with open(probe) as handle:
        readable = handle.read() == "preflight"
    os.remove(probe)
    print("Writing to the Projects folder and reading back:", "works" if readable else "does NOT work")
except Exception as problem:
    print("Writing to the Projects folder does NOT work (%s). Ask whether workspace file writing is enabled on this cluster." % type(problem).__name__)
print("Free local scratch space: %.1f GB" % (shutil.disk_usage(tempfile.gettempdir()).free / 1e9))
print("Path budget: model IDs of up to %d characters keep downloaded files within what Excel can open." % 24)
''')

code("Cell 5 - USE THE LATEST WIDGET VALUES (the only cell that reads the three LLM widgets)", '''
# With Databricks' default widget behaviour this cell runs again by itself whenever a widget value changes and
# the main thread is free. It copies the three values into memory and prints the token's age, never the token.
if "LIVE" not in globals():
    LIVE = aiva.LiveValues()
LIVE.update(dbutils.widgets.get("llm_endpoint"), dbutils.widgets.get("llm_token"), dbutils.widgets.get("llm_user_id"))

def aiva_live(name):
    """Read a live value at the moment chat() is CALLED."""
    return LIVE.get(name)

token = LIVE.get("llm_token")
print("Endpoint set:", bool(LIVE.get("llm_endpoint")), "| user id set:", bool(LIVE.get("llm_user_id")),
      "| token: %d characters, pasted %.1f minutes ago" % (len(token), LIVE.token_age_minutes()) if token else "| no token pasted yet")
''')

code("Cell 6 - YOUR CELL: paste your chat() definition below", '''
# Keep the signature. Return a dictionary with the generated text under "answer".
# Read the three live values when chat() is CALLED, never when it is defined.
# AIVA always calls chat() with an empty history: every question stands on its own.
import requests

def chat(SystemPrompt, MainPrompt, history=[]):
    payload = {
        "app": "sparkair",
        "enable_streaming": False,
        "flow_name": "general_chat",
        "history": history,
        "optionalParameter": {
            "maxtoken": 250000,
            "contextlength": 250000,
            "Temperature": 0.01,          # low: the same question gives the same answer
            "Top_k": 1,
            "Penalty": 1.1,
            "DefaultPrompt": SystemPrompt,
        },
        "query": MainPrompt,
        "select_all": False,
    }
    headers = {
        "Authorization": f'Bearer {aiva_live("llm_token")}',
        "SP_SSO_UID": aiva_live("llm_user_id"),
        "Content-Type": "application/json",
    }
    url = f'{aiva_live("llm_endpoint")}'
    resp = requests.post(url, json=payload, headers=headers, timeout=24000000)
    return resp.json()        # the generated text is under "answer"
''')

code("Cell 7 - chat() self-test (or switch to the stand-in)", '''
import time
USE_STANDIN = False           # True: a deterministic stand-in answers instead of the real model (for trying AIVA out)
if USE_STANDIN:
    import standin_chat
    ACTIVE_CHAT = standin_chat.chat
    SECONDS_PER_CALL = 0.05
    print("The stand-in chat() is selected. It is a test double, not a model: use it only to try the process out.")
else:
    ACTIVE_CHAT = chat
    started = time.time()
    answer_of_call = aiva.call_chat(ACTIVE_CHAT, "You answer with one word.", "Answer with the single word: ready", LIVE)
    answer, failure, seen = answer_of_call
    SECONDS_PER_CALL = time.time() - started
    if answer:
        print("chat() answered in %.1f seconds: %r" % (SECONDS_PER_CALL, answer[:60]))
        print("The gateway also reported: %s" % (answer_of_call.meta or "nothing beyond the answer"))
    else:
        print("chat() gave no usable answer. AIVA read this as: %s. What was seen (token removed): %s" % (failure, seen[:300]))
''')

code("Cell 8 - project setup", '''
def current_settings():
    return aiva.make_settings({"concurrency_limit": int(dbutils.widgets.get("concurrency_limit") or 4), "token_cap": int(dbutils.widgets.get("token_cap") or 40000),
                               "reviewer_id": dbutils.widgets.get("reviewer_id"), "reviewer_role": dbutils.widgets.get("reviewer_role")})

def current_paths(new_run_allowed=True):
    project = dbutils.widgets.get("project")
    project_date = "" if project.startswith("New project") else project
    run_id = dbutils.widgets.get("run")
    run_id = "" if run_id == "New run" else run_id
    if not run_id and "PATHS" in globals() and PATHS.model_id == dbutils.widgets.get("model_id") and (not project_date or PATHS.project_date == project_date):
        return PATHS                                   # keep working on the run this session opened
    return aiva.open_run(dbutils.widgets.get("projects_dir"), dbutils.widgets.get("model_id"), project_date, run_id,
                         scratch_root=dbutils.widgets.get("scratch_dir"))

project = dbutils.widgets.get("project")
project_dir, missing = aiva.setup_project(dbutils.widgets.get("projects_dir"), dbutils.widgets.get("model_id"), "" if project.startswith("New project") else project)
print("Project folder:", project_dir)
print("\\n".join(missing) if missing else "All three Inputs folders hold at least one file. Go on with cell 9.")
''')

code("Cell 9 - start or resume the run: reading steps (no AI involved)", '''
SETTINGS = current_settings()
PATHS = current_paths()
RESULT = aiva.run_pipeline(PATHS, SETTINGS, chat=None, live=LIVE, stop_after="06")
print(RESULT["message"])
store = aiva.open_store(PATHS, SETTINGS)
for outline in store.read("outline"):
    if outline["corner"] == "canon":
        print("\\nOutline of the methodology as AIVA read it (first 60 lines):\\n" + "\\n".join(outline["lines"][:60]))
print("\\nRun folder:", PATHS.run_dir, "\\nOpen Outputs/Output.xlsx: the three Chunks sheets show everything that was read.")
''')

code("Cell 10 - confirm the outline of the methodology", '''
# Run this after you have checked Level and Section (heading chain) on sheet Chunks_Canon against the
# methodology's own table of contents. The AI steps do not start without it.
print(aiva.confirm_outline(PATHS, SETTINGS, dbutils.widgets.get("reviewer_id")))
''')

code("Cell 11 - call plan", '''
plan = aiva.call_plan(PATHS, SETTINGS, "08", seconds_per_call=SECONDS_PER_CALL)
print("Questions for step %s: %d" % (plan["step"], plan["questions"]))
for question_type, count in sorted(plan["by_type"].items()):
    print("  %-26s %d" % (question_type, count))
print("Largest prompt: about %d tokens (cap %d). Expected duration: about %s minutes." % (plan["largest_estimated_tokens"], plan["token_cap"], plan["expected_minutes"]))
print(plan["note"])
''')

code("Cell 12 - run the AI steps and the checks", '''
import threading
MODE = "A"                    # "A" or "B": background thread (cell 13 shows progress). "C": foreground, stops by itself after FOREGROUND_MINUTES.
FOREGROUND_MINUTES = 12
STATE = aiva.AskState()

def keep_alive():
    try:
        spark.range(1).count()                        # a trivial Spark action, so that the cluster does not shut down mid-run
    except Exception:
        pass

def work():
    settings = dict(SETTINGS, foreground_minutes=FOREGROUND_MINUTES if MODE == "C" else 0.0, token_wait="stop" if MODE == "C" else "wait")
    RESULT.update(aiva.run_pipeline(PATHS, aiva.make_settings({k: v for k, v in settings.items() if v != aiva.DEFAULT_SETTINGS.get(k)}),
                                    chat=ACTIVE_CHAT, live=LIVE, state=STATE, keep_alive=keep_alive))

if MODE == "C":
    work()
    print(RESULT["message"])
else:
    WORKER = threading.Thread(target=work, name="aiva-run", daemon=True)
    WORKER.start()
    print("The run works in the background. Run cell 13 to see where it stands; paste a fresh token whenever cell 13 asks for one.")
''')

code("Cell 13 - status (run again to refresh); pause and stop switches", '''
PAUSE, STOP = False, False    # set one to True and run this cell to pause or stop the background run; False again to go on
if "STATE" in globals():
    STATE.control["pause"], STATE.control["stop"] = PAUSE, STOP
store = aiva.open_store(PATHS, SETTINGS)
print(aiva.progress_text(store, RESULT.get("message", "") if "RESULT" in globals() else ""))
for record in store.read("step_records"):
    print("  step %s %-22s %s" % (record["step_id"], record["skill"], ", ".join("%s: %s" % item for item in sorted(record["counts"].items()))))
for label, value in aiva.call_statistics(store):
    print("  %-52s %s" % (label, value))
print("Token pasted %.1f minutes ago.%s" % (LIVE.token_age_minutes(), " The run is WAITING FOR A FRESH TOKEN: paste it into the widget (mode B: then run cell 5)." if "STATE" in globals() and STATE.waiting_for_token else ""))
print("Background run is", "working" if "WORKER" in globals() and WORKER.is_alive() else "not working at the moment")
''')

code("Cell 14 - determinations: run after uploading the completed Output.xlsx into Outputs/", '''
SETTINGS = current_settings()
RESULT = aiva.run_pipeline(PATHS, SETTINGS, chat=ACTIVE_CHAT if "ACTIVE_CHAT" in globals() else None, live=LIVE, determinations=True)
store = aiva.open_store(PATHS, SETTINGS)
last = [r for r in store.read("step_records") if r["skill"] == "record-determinations"][-1:]
for record in last:
    print("Determinations recorded this time:", record["counts"].get("determinations recorded", 0))
    print("\\n".join(record["messages"]))
print("Both output files were rebuilt. Outputs/ holds Output.xlsx and Validation_Report.docx.")
''')

code("Cell 15 - verify this evidence pack", '''
for what, verdict, detail in aiva.verify_evidence_pack(PATHS, SETTINGS, live=LIVE):
    print("%-14s %s%s" % (verdict, what, " (" + detail + ")" if detail else ""))
''')

code("Cell 16 - appendix: environment probe (run once per environment; writes docs/environment_probe_<date>.md)", '''
import os
import environment_probe
print(environment_probe.run_probe(dbutils.widgets.get("projects_dir"), os.path.join(AIVA_HOME, "docs"), chat=chat if "chat" in globals() else None, live=LIVE))
''')

code("Cell 17 - appendix: reviewer sanity checks, one per bundle (stand-in chat, sample projects; change REVIEWER and run)", '''
REVIEWER = 1                  # 1 documents, 2 package, 3 mapping, 4 checks, 5 run and report
import datetime, os, shutil, tempfile, standin_chat
SAMPLE, STOP_AFTER = {1: ("F_capital", "02"), 2: ("F_capital", "04"), 3: ("A_minimal", "08"), 4: ("F_capital_known", ""), 5: ("A_minimal", "")}[REVIEWER]
demo_projects = tempfile.mkdtemp(prefix="aiva_sanity_")
shutil.copytree(os.path.join(AIVA_HOME, "engine", "tests", "sample_projects", SAMPLE, "Inputs"), os.path.join(demo_projects, "SANITY", datetime.date.today().isoformat(), "Inputs"))
demo_settings = aiva.make_settings({"require_outline_confirmation": False})
demo_paths = aiva.open_run(demo_projects, "SANITY")
print(aiva.run_pipeline(demo_paths, demo_settings, chat=standin_chat.chat, stop_after=STOP_AFTER)["message"])
print("Open", os.path.join(demo_paths.outputs_dir, "Output.xlsx"), "and compare with 'HOW TO SANITY-CHECK IT' at the top of the bundle you review.")
''')

code("Cell 18 - appendix: evaluation harness launcher (stand-in chat; takes a few minutes)", '''
import run_harness
run_harness.main(["F_capital", "--limit", "10"])        # remove the limit for the full set of seeded differences
''')


def build(target):
    notebook = {"cells": CELLS, "metadata": {"language_info": {"name": "python"}, "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
                "nbformat": 4, "nbformat_minor": 5}
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(notebook, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    return target


if __name__ == "__main__":
    print(build(os.path.join(ROOT, "AIVA_Interface.ipynb")), "with", len(CELLS), "cells")
