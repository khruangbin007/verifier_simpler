"""Merge the eight engine modules into four and take the old name out of the module names.

    core.py     <- aiva0_shared + aiva0r_reading + aiva1f_formats     (contracts, reading floor, front door)
    reading.py  <- aiva1_documents + aiva2_package                    (documents and the package)
    review.py   <- aiva3_mapping + aiva4_checks                       (mapping and checks)
    runner.py   <- aiva5_run_report                                   (the run, the workbook, the report)

For each merged module: one overview docstring is written by hand afterwards; the imports of its
parts are unioned; references between parts that are now in the same file are flattened
(shared.X -> X); references to other new modules are renamed (aiva3_mapping.X -> review.X).
"""
import ast
import os
import re

ENGINE = "engine"
GROUPS = [
    ("core", ["aiva0_shared", "aiva0r_reading", "aiva1f_formats"]),
    ("reading", ["aiva1_documents", "aiva2_package"]),
    ("review", ["aiva3_mapping", "aiva4_checks"]),
    ("runner", ["aiva5_run_report"]),
]
NEW_OF = {old: new for new, olds in GROUPS for old in olds}
# every alias the old modules were imported under, anywhere
ALIASES = {"aiva0_shared": ["shared"], "aiva0r_reading": ["reading"], "aiva1f_formats": ["formats"],
           "aiva1_documents": ["documents"], "aiva2_package": ["package"], "aiva3_mapping": ["mapping"],
           "aiva4_checks": ["checks"], "aiva5_run_report": ["run"]}


def split(source):
    """(docstring span, import lines, body) of one module."""
    tree = ast.parse(source)
    lines = source.split("\n")
    doc_end = tree.body[0].end_lineno if isinstance(tree.body[0], ast.Expr) else 0
    imports, body_lines, in_header = [], [], True
    for number, line in enumerate(lines[doc_end:], start=doc_end):
        if in_header and (line.startswith(("import ", "from ")) or not line.strip()):
            if line.strip():
                imports.append(line)
            continue
        in_header = False
        body_lines.append(line)
    return imports, "\n".join(body_lines)


def rewrite_references(body, own_parts, importer):
    """In one part's body, flatten references to the parts merged with it and rename the rest."""
    for old, aliases in ALIASES.items():
        names = [old] + aliases
        for name in names:
            pattern = r"(?<![\w.])%s\." % re.escape(name)
            if old in own_parts:
                body = re.sub(pattern, "", body)
            else:
                body = re.sub(pattern, NEW_OF[old] + ".", body)
    return body


def merge(new, olds):
    imports, bodies = [], []
    for old in olds:
        source = open(os.path.join(ENGINE, old + ".py"), encoding="utf-8").read()
        part_imports, body = split(source)
        for line in part_imports:
            found = re.match(r"import (aiva\w+)(?: as (\w+))?", line)
            if found:
                if NEW_OF[found.group(1)] != new:
                    line = "import %s" % NEW_OF[found.group(1)]
                else:
                    continue
            if line not in imports:
                imports.append(line)
        bodies.append("# %s\n# ---------------------------------------------------------------- from %s\n%s" % ("=" * 96, old, rewrite_references(body, olds, new)))
    stdlib = sorted(l for l in imports if not re.search(r"\b(yaml|core|reading|review|runner)\b", l))
    third = sorted(l for l in imports if re.search(r"\byaml\b", l))
    own = sorted(l for l in imports if re.search(r"\b(core|reading|review|runner)\b", l))
    header = '"""OVERVIEW PLACEHOLDER: %s"""\n\n' % new
    text = header + "\n".join(stdlib) + ("\n\n" + "\n".join(third) if third else "") + ("\n\n" + "\n".join(own) if own else "") + "\n\n" + "\n\n".join(bodies).rstrip() + "\n"
    open(os.path.join(ENGINE, new + ".py"), "w", encoding="utf-8").write(text)
    for old in olds:
        os.remove(os.path.join(ENGINE, old + ".py"))
    return len(text.split("\n"))


if __name__ == "__main__":
    for new, olds in GROUPS:
        print("%-8s %5d lines  <- %s" % (new, merge(new, olds), ", ".join(olds)))
