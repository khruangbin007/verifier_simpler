import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import os, sys, re, shutil, tempfile, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, TESTS); sys.path.insert(0, ENGINE)
import verifier, openpyxl
from harness import Gateway, SETTINGS, attach, run_until_done
unit_of = lambda ref: re.sub(r"^([CDM]-\d+)-\d+$", r"\1", ref)
faults, totals = [], {"items": 0, "location links": 0, "methodology links": 0, "count links": 0}
for sample in sorted(os.listdir(SAMPLES)):
    root = tempfile.mkdtemp()
    shutil.copytree(SAMPLES + "/%s/Inputs" % sample, os.path.join(root, "Projects", "L"), dirs_exist_ok=True)
    settings = verifier.make_settings({}); SETTINGS[0] = settings
    paths = verifier.open_run(os.path.join(root, "Projects"), "L", scratch_root=tempfile.mkdtemp(), settings=settings)
    attach(Gateway(delay=(0, 0.002))); run_until_done(paths, settings)
    book = openpyxl.load_workbook(os.path.join(paths.project_dir, verifier.OUTPUT_FILE))
    items, model, method = book["Flagged_Items"], book["Chunks_Model"], book["Chunks_Methodology"]
    model_refs = [model.cell(row=r, column=1).value for r in range(2, model.max_row + 1)]
    method_refs = [method.cell(row=r, column=1).value for r in range(2, method.max_row + 1)]
    locations = [items.cell(row=r, column=2).value for r in range(2, items.max_row + 1)]
    totals["items"] += len(locations)
    for r in range(2, items.max_row + 1):
        ident, location, refs = (items.cell(row=r, column=c) for c in (1, 2, 3))
        if ident.value != "F-%04d" % (r - 1):
            faults.append((sample, ident.coordinate, "id %s" % ident.value))
        first = model_refs.index(next(x for x in model_refs if unit_of(x) == location.value)) + 2
        if not location.hyperlink or location.hyperlink.location != "'Chunks_Model'!A%d" % first:
            faults.append((sample, location.coordinate, "location link")); continue
        totals["location links"] += 1
        if [x for x in model_refs if unit_of(x) == location.value] != [x for x in model_refs if x == location.value or x.startswith(location.value + "-")]:
            faults.append((sample, location.coordinate, "the macro's rule"))
        if refs.value:
            named = refs.value.split("; ")
            where = method_refs.index(next(x for x in method_refs if unit_of(x) == named[0])) + 2
            if not refs.hyperlink or refs.hyperlink.location != "'Chunks_Methodology'!A%d" % where:
                faults.append((sample, refs.coordinate, "methodology link")); continue
            totals["methodology links"] += 1
        for column in (10, 11):
            cell = items.cell(row=r, column=column)
            if cell.protection.locked:
                faults.append((sample, cell.coordinate, "locked"))
        for column in (10, 11):                              # the reviewer's cells: shaded in the reviewer's colour
            if (items.cell(row=r, column=column).fill.start_color.rgb or "")[-6:] != "C6EFCE":
                faults.append((sample, items.cell(row=r, column=column).coordinate, "not shaded"))
    head = [c.value for c in model[1]]
    count_col = head.index("Count of Flagged Items (by LLM)") + 1
    for r in range(2, model.max_row + 1):
        cell = model.cell(row=r, column=count_col)
        n = cell.value if isinstance(cell.value, int) else 0
        unit = unit_of(model.cell(row=r, column=1).value)
        if n != locations.count(unit) and isinstance(cell.value, int):
            faults.append((sample, cell.coordinate, "count %s, rows %d" % (n, locations.count(unit))))
        if n:
            first = locations.index(unit) + 2
            if not cell.hyperlink or cell.hyperlink.location != "'Flagged_Items'!A%d" % first:
                faults.append((sample, cell.coordinate, "count link")); continue
            totals["count links"] += 1
        elif cell.hyperlink:
            faults.append((sample, cell.coordinate, "a link on a count of 0"))
    checks = items.data_validations.dataValidation
    if locations and (len(checks) != 1 or checks[0].formula1 != '"%s"' % ",".join(verifier.FLAGGED_DECISIONS) or str(checks[0].sqref) != "J2:J%d" % (len(locations) + 1)):
        faults.append((sample, "J", "dropdown %s" % [(c.formula1, str(c.sqref)) for c in checks]))
    protected = [name for name in book.sheetnames if book[name].protection.sheet]
    if protected:
        faults.append((sample, "sheets", "protected: %s" % protected))
    print("%-16s items %3d | sheets %s" % (sample, len(locations), book.sheetnames[-1]))
print(totals, "| faults:", faults[:8] or "none")
