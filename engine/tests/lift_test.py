import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, json, shutil, tempfile, hashlib, subprocess, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ENGINE)
import verifier
SAMPLE = SAMPLES + "/F_capital/Inputs"
def hashes(root):
    return {os.path.relpath(os.path.join(b, n), root): hashlib.sha256(open(os.path.join(b, n), "rb").read()).hexdigest()
            for b, _, names in os.walk(root) for n in names if n != "README.txt"}
def old_project(projects, name, extra=None):
    inputs = os.path.join(projects, name, "Inputs")
    shutil.copytree(SAMPLE, inputs)
    for rel, data in (extra or {}).items():
        os.makedirs(os.path.dirname(os.path.join(projects, name, rel)), exist_ok=True)
        open(os.path.join(projects, name, rel), "w").write(data)
    return os.path.join(projects, name)
projects = tempfile.mkdtemp()
# A: a project in the older layout, with the optional tag rules
project = old_project(projects, "A", {"Inputs/tag_rules.yaml": "headings: []\n"})
before = hashes(os.path.join(project, "Inputs"))
_, missing, said = verifier.setup_project(projects, "A")
after = {k: v for k, v in hashes(project).items() if not k.startswith("Output") and not k.startswith("Audit")}
print("A moved:", said, "| nothing blocks:", not missing, "| Inputs gone:", not os.path.exists(os.path.join(project, "Inputs")),
      "| every file, same bytes, same place inside:", before == after)
# C: a folder in both places, both holding files
project = old_project(projects, "C", {"1_Methodology/mine.xml": "<a/>"})
_, missing, said = verifier.setup_project(projects, "C")
print("C blocks:", [m[:70] for m in missing if "both" in m], "| Inputs/1_Methodology left:", os.path.isdir(os.path.join(project, "Inputs", "1_Methodology")),
      "| the other two moved:", all(os.path.isdir(os.path.join(project, f)) and not os.path.exists(os.path.join(project, "Inputs", f)) for f in ("2_Model_Package", "3_Model_Documentation")))
print("   cell 3 would stop:", bool(missing))
# D: a folder above that holds only the tool's README gives way
project = old_project(projects, "D", {"1_Methodology/README.txt": "readme\n"})
_, missing, said = verifier.setup_project(projects, "D")
print("D moved:", said[:1], "| nothing blocks:", not missing, "| methodology present above:", sorted(os.listdir(os.path.join(project, "1_Methodology")))[:3])
# E: Inputs holding something of the analyst's own
project = old_project(projects, "E", {"Inputs/notes.docx": "x"})
_, missing, said = verifier.setup_project(projects, "E")
print("E said:", said[-1], "| kept:", os.listdir(os.path.join(project, "Inputs")))
# F: files at the project level beside the folders are not inputs
project = os.path.join(projects, "A")
open(os.path.join(project, "my copy of Output.xlsm"), "w").write("x")
listed = verifier.list_input_files(project)
names = [os.path.relpath(p, project) for corner in ("methodology", "package", "documentation") for p in listed[corner]]
print("F inputs read:", sorted(names), "| optional:", {k: bool(listed[k]) for k in ("tag_rules", "glossary")})
