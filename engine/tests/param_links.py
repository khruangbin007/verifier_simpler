import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, shutil, tempfile, tarfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ENGINE); sys.path.insert(0, TESTS)
import verifier, openpyxl
code = '''get_param <- function(name) get(name, envir = asNamespace("capreq"))
param_value <- function(n) get_param(n)
reads_by_wrapper <- function() get_param("lgd_floors")
reads_two_levels <- function() param_value("lgd_floors")
floors_of <- function(kind) get(paste0(kind, "_floors"))
reads_template <- function() floors_of("lgd")
read_setting <- function(file) readRDS(system.file("extdata", paste0(file, ".rds"), package = "capreq"))
reads_setting <- function() read_setting("confidence")
reads_by_paste <- function(kind) get(paste0(kind, "_floors"))
reads_unknown <- function(x) get(x)
cache <- new.env()
.onLoad <- function(libname, pkgname) assign("floors", lgd_floors, envir = cache)
reads_cache <- function(seg) cache$floors$lgd_floor[cache$floors$segment == seg]
store_limits <- function() cache[["limits"]] <- lgd_floors
reads_limits <- function() cache[["limits"]]
store_segment <- function() cache$segment <- lgd_floors$segment
reads_segment <- function() cache$segment
set_params <- function() assign("params", lgd_floors, envir = topenv())
reads_params <- function() params$lgd_floor
remember <- function() last_floors <<- lgd_floors
reads_remembered <- function() last_floors
'''
expect = {"reads_by_wrapper": ["lgd_floors", "get_param"], "get_param": ["lgd_floors"], "reads_two_levels": ["lgd_floors", "param_value"],
          "reads_template": ["lgd_floors", "floors_of"], "floors_of": ["lgd_floors"], "reads_setting": ["confidence", "read_setting"],
          "read_setting": ["confidence"], "reads_by_paste": ["lgd_floors (possible)"], "reads_unknown": [verifier.UNKNOWN_NAME],
          "reads_cache": [".onLoad", "cache"], "reads_limits": ["store_limits", "cache"], "reads_segment": ["store_segment", "cache"], "reads_params": ["set_params"],
          "reads_remembered": ["remember"]}
root = tempfile.mkdtemp()
inputs = os.path.join(root, "Projects", "P")
shutil.copytree(SAMPLES + "/F_capital/Inputs", inputs)
corner = os.path.join(inputs, "2_Model_Package")
archive = [os.path.join(corner, f) for f in os.listdir(corner)][0]
with tarfile.open(archive) as tar:
    tar.extractall(corner, filter="data")
os.remove(archive)
package = [os.path.join(corner, d) for d in os.listdir(corner) if os.path.isdir(os.path.join(corner, d))][0]
open(os.path.join(package, "R", "zz_patterns.R"), "w").write(code)
settings = verifier.make_settings({})
paths = verifier.open_run(os.path.join(root, "Projects"), "P", scratch_root=tempfile.mkdtemp(), settings=settings)
verifier.run_pipeline(paths, settings, stop_after="03")
book = openpyxl.load_workbook(os.path.join(paths.project_dir, verifier.OUTPUT_FILE))
sheet = book["Chunks_Model"]
head = [c.value for c in sheet[1]]
col = {h: i for i, h in enumerate(head)}
rows = [[c.value for c in r] for r in sheet.iter_rows(min_row=2)]
units = {u["ref"]: u for u in verifier.open_store(paths, settings).read("model_units")}
name_of = {ref: u["name"] for ref, u in units.items()}
def named(cell):
    out = []
    for item in (cell or "").split("; "):
        ref = item.split(" ")[0]
        out.append(name_of.get(ref, "?") + item[len(ref):] if ref in name_of else item)
    return out
wrong = 0
for r in rows:
    name = name_of.get(r[0], "")
    if name in expect:
        got = named(r[col["Immediate Upstream Model Chunk"]])
        ok = sorted(got) == sorted(expect[name])
        wrong += not ok
        print("%s %-18s upstream: %s%s" % ("ok " if ok else "BAD", name, "; ".join(got), "" if ok else "   (expected %s)" % expect[name]))
for r in rows:
    if r[col["Kind"]] in ("Parameter table", "Parameter object"):
        print("data %s | text starts: %r | downstream: %s | link: %s" % (r[0], (r[col["Text"]] or "").split("\n")[0], "; ".join(named(r[col["Immediate Downstream Model Chunk"]])),
              bool(sheet.cell(row=rows.index(r) + 2, column=col["Immediate Downstream Model Chunk"] + 1).hyperlink)))
info = book["Model_Package_Info"]
print([tuple(c.value for c in row) for row in info.iter_rows(min_row=2) if row[0].value == "Package data" and "Stored" in str(row[1].value)])
print("step 03 said:", [m for rec in verifier.open_store(paths, settings).read("step_records") if rec["step_id"] == "03" for m in rec["messages"]])
print("wrong:", wrong)
