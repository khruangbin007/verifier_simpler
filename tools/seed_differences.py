"""seed_differences.py - plants ONE known difference at a time in a clean sample project.

Operators (plan 4.3). On R source: flip a sign, change a constant in three ways, remove a floor
or cap, swap an operator, change a comparison. On parameter data: change a cell, drop a row,
swap two values. On roxygen: rename a parameter, change a stated default, change a stated
value, drop the export tag. On documentation (.docx): change a value. The methodology is never
touched. Each mutant says which file and line it changed and which categories of flagged item
are expected for it. Used by run_harness.py; it can also list the mutants of a sample:

    python tools/seed_differences.py F_capital
"""
import gzip
import io
import os
import re
import sys
import tarfile
import warnings
import zipfile

TRIVIAL = ("0", "1", "2", "10", "100")
CODE_CATEGORIES = ("Code differs from methodology", "Hard-coded number not traced", "Package documentation differs from code")
DATA_CATEGORIES = ("Value differs from methodology", "Documentation differs from code")
ROXYGEN_CATEGORIES = ("Package documentation differs from code", "Package documentation differs from methodology")
DOC_CATEGORIES = ("Documentation differs from methodology", "Documentation differs from code")


def read_tarball(path):
    files, top = {}, ""
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            if member.isfile():
                top, name = member.name.split("/", 1)
                files[name] = archive.extractfile(member).read()
    return top, files


def write_tarball(top, files):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for path in sorted(files):
            member = tarfile.TarInfo("%s/%s" % (top, path))
            member.size, member.mtime, member.mode = len(files[path]), 1767225600, 0o644
            archive.addfile(member, io.BytesIO(files[path]))
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as handle:
        handle.write(raw.getvalue())
    return packed.getvalue()


def changed_number(text, way):
    """A constant changed in one of three ways: a tenth more, last digit plus one, halved."""
    decimals = len(text.split(".")[1]) if "." in text else 0
    value = float(text)
    if way == "a tenth more":
        new = value * 1.1
    elif way == "last digit plus one":
        new = value + 10 ** (-decimals)
    else:
        new = value / 2.0
    shown = ("%%.%df" % (decimals + (1 if way != "last digit plus one" else 0))) % new
    return shown if float(shown) != value else str(value + 1)


def code_mutants(path, text):
    """(operator, line number, description, new text) for one R file."""
    mutants, lines = [], text.split("\n")
    def put(number, new_line, operator, what):
        changed = list(lines)
        changed[number] = new_line
        mutants.append({"operator": operator, "file": path, "line": number + 1, "what": what, "text": "\n".join(changed), "expected": CODE_CATEGORIES})
    for number, line in enumerate(lines):
        code = line.split("#")[0]
        if not code.strip() or line.lstrip().startswith("#") or "function(" in code or "stop(" in code or "library(" in code:
            continue
        for sign, other in ((" + ", " - "), (" - ", " + ")):
            if sign in code:
                put(number, line.replace(sign, other, 1), "flip a sign", "'%s' became '%s'" % (sign.strip(), other.strip()))
                break
        for sign, other in ((" * ", " / "), (" / ", " * ")):
            if sign in code:
                put(number, line.replace(sign, other, 1), "swap an operator", "'%s' became '%s'" % (sign.strip(), other.strip()))
                break
        for sign, other in ((" > ", " < "), (" < ", " > "), (" >= ", " <= "), (" <= ", " >= ")):
            if sign in code and "<-" not in code.replace(" <- ", ""):
                put(number, line.replace(sign, other, 1), "change a comparison", "'%s' became '%s'" % (sign.strip(), other.strip()))
                break
        guard = re.search(r"\bp(max|min)\(([^(),]+), ([^(),]+)\)", code)
        if guard:
            put(number, line.replace(guard.group(0), guard.group(2), 1), "remove a floor or cap", "'%s' became '%s'" % (guard.group(0), guard.group(2)))
        for found in re.finditer(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", code):
            if found.group(0) in TRIVIAL or re.search(r"lines?\s*$", code[:found.start()]):
                continue
            for way in ("a tenth more", "last digit plus one", "halved"):
                new_line = line[:found.start()] + changed_number(found.group(0), way) + line[found.end():]
                put(number, new_line, "change a constant", "%s became %s (%s)" % (found.group(0), changed_number(found.group(0), way), way))
            break
    return mutants


def roxygen_mutants(path, text):
    mutants, lines = [], text.split("\n")
    def put(number, new_line, operator, what):
        changed = list(lines)
        if new_line is None:
            del changed[number]
        else:
            changed[number] = new_line
        line = number if new_line is None else number + 1        # after a deletion the block ends one line earlier
        mutants.append({"operator": operator, "file": path, "line": line, "what": what, "text": "\n".join(changed), "expected": ROXYGEN_CATEGORIES})
    for number, line in enumerate(lines):
        if not line.startswith("#'"):
            continue
        param = re.match(r"#' @param (\w+) ", line)
        if param:
            put(number, line.replace("@param %s " % param.group(1), "@param %s_x " % param.group(1), 1), "rename a parameter", "@param %s became %s_x" % (param.group(1), param.group(1)))
        stated = re.search(r"defaults to (\d+(?:\.\d+)?)", line)
        if stated:
            put(number, line.replace(stated.group(1), changed_number(stated.group(1), "halved"), 1), "change a stated default", "default %s became %s" % (stated.group(1), changed_number(stated.group(1), "halved")))
        value = re.search(r"(?<![\w.{])\d+\.\d+(?![\w.])", line)
        if value and not param and "deqn" not in line and "@" not in line:
            put(number, line.replace(value.group(0), changed_number(value.group(0), "a tenth more"), 1), "change a stated value", "%s became %s" % (value.group(0), changed_number(value.group(0), "a tenth more")))
        if line.strip() == "#' @export":
            put(number, None, "drop the export tag", "@export removed")
    return mutants


def data_mutants(path, data):
    import rdata
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = rdata.conversion.convert(rdata.parser.parse_data(data))
    single = not isinstance(parsed, dict)
    frame = parsed if single else list(parsed.values())[0]
    name = None if single else list(parsed.keys())[0]
    numeric = [c for c in frame.columns if str(frame[c].dtype).lower().startswith(("float", "int"))]
    if not numeric or len(frame) < 2:
        return []
    def written(new_frame):
        target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_seed.bin")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            rdata.write_rds(target, new_frame) if single else rdata.write_rda(target, {name: new_frame})
        with open(target, "rb") as handle:
            result = handle.read()
        os.remove(target)
        return result
    column, mutants = numeric[0], []
    cell = frame.copy()
    cell.loc[cell.index[0], column] = float(cell.loc[cell.index[0], column]) * 1.5
    mutants.append(("change a cell", "first row of %s times 1.5" % column, cell))
    mutants.append(("drop a row", "last row removed", frame.iloc[:-1].copy()))
    swapped = frame.copy()
    first, second = swapped.loc[swapped.index[0], column], swapped.loc[swapped.index[1], column]
    swapped.loc[swapped.index[0], column], swapped.loc[swapped.index[1], column] = second, first
    mutants.append(("swap two values", "first two values of %s swapped" % column, swapped))
    return [{"operator": operator, "file": path, "line": None, "what": what, "bytes": written(new), "expected": DATA_CATEGORIES} for operator, what, new in mutants]


def docx_mutants(name, data):
    """Change a value: the first decimal number or percentage in each paragraph of a .docx."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    parts = {item.filename: archive.read(item.filename) for item in archive.infolist()}
    document = parts["word/document.xml"].decode("utf-8")
    mutants, candidates = [], []
    for paragraph in re.finditer(r"<w:p[ >].*?</w:p>", document, re.S):            # headings and their numbering are left alone
        if "<w:pStyle w:val=\"Heading" in paragraph.group(0) or "<m:oMath" in paragraph.group(0):
            continue
        inner = re.search(r"(<w:t[^>]*>[^<]*?)(\d+\.\d+)(%?)", paragraph.group(0))
        if inner:
            candidates.append((paragraph.start() + inner.start(2), paragraph.start() + inner.end(2), inner.group(2), inner.group(3)))
    for start, end, old_value, percent in candidates[:6]:
        found = type("Found", (), {"start": lambda self, g: start, "end": lambda self, g: end, "group": lambda self, g: old_value if g == 2 else percent})()
        new_value = changed_number(found.group(2), "a tenth more")
        changed = document[:found.start(2)] + new_value + document[found.end(2):]
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as target:
            for filename in parts:
                target.writestr(filename, changed.encode("utf-8") if filename == "word/document.xml" else parts[filename])
        mutants.append({"operator": "change a value in the documentation", "file": name, "line": None, "new_value": new_value + found.group(3),
                        "what": "%s became %s" % (found.group(2), new_value), "bytes": packed.getvalue(), "expected": DOC_CATEGORIES})
    return mutants


def mutants_of(inputs_dir):
    """Every mutant of one sample: {"id", "operator", "file", "line", "what", "expected", "inputs": {relative path: bytes}}."""
    package_dir = os.path.join(inputs_dir, "2_Model_Package")
    tar_name = sorted(os.listdir(package_dir))[0]
    top, files = read_tarball(os.path.join(package_dir, tar_name))
    found = []
    for path in sorted(files):
        if path.startswith("R/") and path.lower().endswith(".r"):
            text = files[path].decode("utf-8")
            for mutant in code_mutants(path, text) + roxygen_mutants(path, text):
                mutant["inputs"] = {"2_Model_Package/" + tar_name: write_tarball(top, dict(files, **{path: mutant.pop("text").encode("utf-8")}))}
                found.append(mutant)
        elif path.lower().endswith((".rda", ".rds", ".rdata")):
            for mutant in data_mutants(path, files[path]):
                mutant["inputs"] = {"2_Model_Package/" + tar_name: write_tarball(top, dict(files, **{path: mutant.pop("bytes")}))}
                found.append(mutant)
    doc_dir = os.path.join(inputs_dir, "3_Model_Documentation")
    for name in sorted(os.listdir(doc_dir)):
        if name.lower().endswith(".docx"):
            with open(os.path.join(doc_dir, name), "rb") as handle:
                for mutant in docx_mutants(name, handle.read()):
                    mutant["inputs"] = {"3_Model_Documentation/" + name: mutant.pop("bytes")}
                    found.append(mutant)
    for number, mutant in enumerate(found, start=1):
        mutant["id"] = "S-%03d" % number
    return found


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sample = sys.argv[1] if len(sys.argv) > 1 else "F_capital"
    for mutant in mutants_of(os.path.join(root, "engine", "tests", "sample_projects", sample, "Inputs")):
        print(mutant["id"], mutant["operator"].ljust(36), mutant["file"], mutant["line"] or "", "|", mutant["what"])
