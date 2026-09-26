import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, re, json, shutil, tempfile, warnings, glob
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier, openpyxl
from harness import Gateway, SETTINGS, attach, run_until_done

def unit_of(ref): return re.sub(r"^([CDM]-\d+)-\d+$", r"\1", ref)
def shown_by(refs, sheet_refs):          # the macro's ShowOnly, row for row
    return [r for r in sheet_refs if any(r == w or r.startswith(w + "-") for w in refs)]

total_links, faults = 0, []
for sample in sorted(os.listdir(SAMPLES)):
    root = tempfile.mkdtemp()
    shutil.copytree(SAMPLES + "/%s/Inputs" % sample, os.path.join(root, "Projects", "L"), dirs_exist_ok=True)
    settings = verifier.make_settings({}); SETTINGS[0] = settings
    paths = verifier.open_run(os.path.join(root, "Projects"), "L", scratch_root=tempfile.mkdtemp(), settings=settings)
    attach(Gateway(delay=(0, 0.002)))
    run_until_done(paths, settings)
    book = openpyxl.load_workbook(os.path.join(paths.project_dir, verifier.OUTPUT_FILE))
    model, method = book["Chunks_Model"], book["Chunks_Methodology"]
    head = [c.value for c in model[1]]
    model_refs = [model.cell(row=r, column=1).value for r in range(2, model.max_row + 1)]
    method_refs = [method.cell(row=r, column=1).value for r in range(2, method.max_row + 1)]
    links = 0
    for row in range(2, model.max_row + 1):
        for header, target, refs_on in (("Relevant Chunks in Methodology (searched by LLM)", "Chunks_Methodology", method_refs),
                                        ("Immediate Upstream Model Chunk", "Chunks_Model", model_refs),
                                        ("Immediate Downstream Model Chunk", "Chunks_Model", model_refs)):
            cell = model.cell(row=row, column=head.index(header) + 1)
            value = cell.value or ""
            if not verifier.REF_LIST.match(value):
                if cell.hyperlink:
                    faults.append((sample, cell.coordinate, "a link on a cell that is not a list"))
                continue
            links += 1
            if not cell.hyperlink or not cell.hyperlink.location:
                faults.append((sample, cell.coordinate, "no link")); continue
            named = value.split("; ")
            wanted = named + ([unit_of(model_refs[row - 2])] if target == "Chunks_Model" else [])
            rows = shown_by(wanted, refs_on)
            expected = [r for r in refs_on if unit_of(r) in wanted]
            first = refs_on.index(next(r for r in refs_on if unit_of(r) == named[0])) + 2
            if rows != expected or set(map(unit_of, rows)) != set(wanted):
                faults.append((sample, cell.coordinate, "shows %s, not %s" % (rows, wanted)))
            if cell.hyperlink.location != "'%s'!A%d" % (target, first):
                faults.append((sample, cell.coordinate, "leads to %s" % cell.hyperlink.location))
    total_links += links
    by_column = {}
    for row in range(2, model.max_row + 1):
        for header in ("Relevant Chunks in Methodology (searched by LLM)", "Immediate Upstream Model Chunk", "Immediate Downstream Model Chunk"):
            if model.cell(row=row, column=head.index(header) + 1).hyperlink:
                by_column[header.split()[1] if header.startswith("Immediate") else "Relevant"] = by_column.get(header.split()[1] if header.startswith("Immediate") else "Relevant", 0) + 1
    print("%-16s links %3d %s" % (sample, links, by_column))
print("links on all samples: %d | faults: %s" % (total_links, faults or "none"))

# a project the tool wrote before: an unchanged Output.xlsx is replaced; a changed one stops the new run
for edited in (False, True):
    root = tempfile.mkdtemp()
    shutil.copytree(SAMPLES + "/D_dosing/Inputs", os.path.join(root, "Projects", "OLD"), dirs_exist_ok=True)
    settings = verifier.make_settings({}); SETTINGS[0] = settings
    paths = verifier.open_run(os.path.join(root, "Projects"), "OLD", scratch_root=tempfile.mkdtemp(), settings=settings)
    verifier.run_pipeline(paths, settings, stop_after="01")
    project = paths.project_dir
    os.rename(os.path.join(project, verifier.OUTPUT_FILE), os.path.join(project, "Output.xlsx"))   # as the old engine left it
    if edited:
        with open(os.path.join(project, "Output.xlsx"), "ab") as handle:
            handle.write(b" ")
    store = verifier.open_store(paths, settings)
    manifest = (store.read("run_manifest") or [{}])[0]
    manifest["last_workbook_sha256"] = verifier.file_sha256(os.path.join(project, "Output.xlsx")) if not edited else "0" * 64
    store.append("run_manifest", [manifest])
    store.sync()
    store.local_dir and None
    manifest_path = os.path.join(project, verifier.AUDIT_FILE)
    # the engine changed since: the next run is new
    try:
        again = verifier.open_run(os.path.join(root, "Projects"), "OLD", scratch_root=tempfile.mkdtemp(), settings=verifier.make_settings({"max_file_mb": 199.0}))
        print("unchanged Output.xlsx:" if not edited else "EDITED, yet opened:", again.opened, "| left:", sorted(os.listdir(project)))
    except verifier.RunStopped as problem:
        print("edited Output.xlsx:", problem, "| left:", sorted(os.listdir(project)))
