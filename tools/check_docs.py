"""check_docs.py - fails when the manual and the code disagree (plan, Phase 11 and 5.3).

It reports: a public function without a docstring; a name in the manual (function, test, notebook
cell, sheet, file) that does not exist; a design rule without an enforcing function, or a docstring
that names a rule that does not exist; a SKILL.md whose version or function differs from the code;
a workbook column, status or category the manual does not show; a setting or assessment column
without an explanation; a checklist line that names nothing that exists.

    python tools/check_docs.py        (exit code 1 when anything is reported)
"""
import ast
import glob
import importlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for folder in (os.path.join(ROOT, "engine"), os.path.join(ROOT, "tools")):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import aiva0_shared as shared          # noqa: E402
import aiva5_run_report as run         # noqa: E402
import build_manual                    # noqa: E402

CELLS = 18


def test_names():
    """Every test as file.Class.method, read from the test files without importing them."""
    names = set()
    for path in glob.glob(os.path.join(ROOT, "engine", "tests", "test_*.py")):
        module = os.path.basename(path)[:-3]
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        names.add(module + ".py")
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                names.update("%s.%s.%s" % (module, node.name, sub.name) for sub in node.body if isinstance(sub, ast.FunctionDef))
    return names


def engine_names():
    names = {}
    for bundle in build_manual.BUNDLES:
        module = importlib.import_module(bundle)
        names[bundle + ".py"] = True
        for name, _, docstring, _ in build_manual.functions_of(bundle):
            names["%s.%s" % (bundle, name)] = docstring
        for name in dir(module):
            names.setdefault("%s.%s" % (bundle, name), "constant")
    return names


def reference_exists(token, engine, tests, sheets):
    """None when the token is not a checkable reference; else True or False."""
    if re.fullmatch(r"cell \d+", token):
        return 1 <= int(token.split()[1]) <= CELLS
    if re.fullmatch(r"aiva\d_\w+\.py", token) or re.fullmatch(r"aiva\d_\w+(\.\w+)+", token):
        return token in engine
    if re.fullmatch(r"test_\w+\.py", token) or re.fullmatch(r"test_\w+\.\w+\.test_\w+", token):
        return token in tests
    if re.fullmatch(r"(engine|tools|docs|evaluation)/[\w./<>-]+", token):
        return "<" in token or os.path.exists(os.path.join(ROOT, token))
    if re.fullmatch(r"[A-Z][A-Za-z]+(_[A-Za-z]+)+", token):
        return token in sheets
    return None


def problems():
    found = []
    engine, tests = engine_names(), test_names()
    sheets = {sheet["name"] for sheet in run.load_layout()["sheets"]}
    for bundle in build_manual.BUNDLES:                                   # 1. docstrings
        for name, line, docstring, _ in build_manual.functions_of(bundle):
            if not docstring and not name.split(".")[-1].startswith("_"):
                found.append("%s.py line %d: %s has no docstring" % (bundle, line, name))
    rules = build_manual.rule_map()                                       # 2. design rules
    for rule, functions in rules.items():
        if rule not in build_manual.RULES:
            found.append("a docstring names the rule %s, which does not exist (%s)" % (rule, ", ".join(functions)))
        elif not functions:
            found.append("design rule %s has no enforcing function" % rule)
    for step in run.load_pipeline()["steps"]:                             # 3. skills
        front = build_manual.skill_front_matter(step["skill"])
        carried = front["metadata"]["carried-out-by"]
        if step.get("function") and carried != step["function"]:
            found.append("SKILL.md of %s says it is carried out by %s; pipeline.yaml says %s" % (step["skill"], carried, step["function"]))
        if step.get("function"):
            declared = importlib.import_module(step["function"].split(".")[0]).SKILL_VERSIONS.get(step["skill"])
            if declared != front["metadata"]["version"]:
                found.append("SKILL.md of %s has version %s; its bundle declares %s" % (step["skill"], front["metadata"]["version"], declared))
    manual = build_manual.assemble()                                      # 4. what the manual must show
    for sheet in run.load_layout()["sheets"]:
        for column in sheet["columns"]:
            if "| %s |" % column["header"] not in manual:
                found.append("column '%s' of %s is not in the manual" % (column["header"], sheet["name"]))
            if column["group"] == "assessments" and sheet["name"].startswith("Mapping_") and column["header"] not in build_manual.COLUMN_NOTES \
                    and sheet["name"] != "Mapping_Coverage":
                found.append("assessment column '%s' has no explanation in build_manual.COLUMN_NOTES" % column["header"])
    for word in shared.CLEAN_STATUSES + shared.NOT_CLEAN_STATUSES + shared.CATEGORIES + shared.DECISION_WORDS:
        if word not in manual:
            found.append("'%s' is not explained in the manual" % word)
    for name in run.DEFAULT_SETTINGS:
        if not build_manual.SETTING_NOTES.get(name):
            found.append("setting '%s' has no explanation in build_manual.SETTING_NOTES" % name)
    if shared.has_banned_wording(re.sub(r"<!-- wording-policy-sentence -->.*?<!-- end -->", "", manual, flags=re.S)):
        found.append("the manual uses the word '%s'" % shared.has_banned_wording(re.sub(r"<!-- wording-policy-sentence -->.*?<!-- end -->", "", manual, flags=re.S)))
    in_checklist = False                                                  # 5. names in the chapters written by hand
    for path in sorted(glob.glob(os.path.join(ROOT, "docs", "manual_src", "*.md"))):
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                where = "%s line %d" % (os.path.basename(path), number)
                verdicts = [(token, reference_exists(token, engine, tests, sheets)) for token in re.findall(r"`([^`]+)`", line)]
                found += ["%s names `%s`, which does not exist" % (where, token) for token, verdict in verdicts if verdict is False]
                if line.startswith("**Checklist"):
                    in_checklist = True
                elif line.startswith("#") or (line.startswith("**") and not line.startswith("**Checklist")):
                    in_checklist = False
                elif in_checklist and line.startswith("- ") and not any(verdict for _, verdict in verdicts):
                    found.append("%s: this checklist line names no test, function, cell, sheet or file that exists" % where)
    return found


if __name__ == "__main__":
    reported = problems()
    print("\n".join(reported) if reported else "check_docs: the manual and the code agree.")
    sys.exit(1 if reported else 0)
