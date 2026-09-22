"""Rules that hold for the whole engine: one-way imports, line budgets, plain code, no execution of
input text (R7), and the wording lint, static and dynamic (R1, R10)."""
import ast
import glob
import os
import re
import unittest

import helpers
import core
import develop

BUNDLES = ("core", "reading", "review", "runner", "develop")
FORBIDDEN_NAMES = ("eval", "exec", "compile", "__import__")           # called as a bare name
FORBIDDEN_ATTRIBUTES = ("sympify", "parse_expr", "system", "popen", "lambdify")   # called on any owner
PYTHON_TRACES = re.compile(r"Traceback|\b\w+(Error|Exception)\b|<class |object at 0x|\bnan\b|"
                           r"[:=(\[]\s*None\b|\{'|\['|^None$")


def engine_source(name):
    with open(os.path.join(helpers.ENGINE_DIR, name + ".py"), encoding="utf-8") as handle:
        return handle.read()


def own_words(text):
    """A cell's text without its visibly quoted parts: the lint applies to AIVA's own words."""
    return re.sub(r"\u201c.*?\u201d", "", text, flags=re.S)


class ImportDirection(unittest.TestCase):
    def test_a_module_imports_only_the_modules_below_it(self):
        """core imports nothing of the engine; reading imports core; review imports core and reading;
        runner imports all three; develop imports whatever it measures. One direction, no cycles."""
        for position, name in enumerate(BUNDLES):
            for node in ast.walk(ast.parse(engine_source(name))):
                imported = []
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom):
                    imported = [node.module or ""]
                for module in imported:
                    if module in BUNDLES:
                        self.assertIn(module, BUNDLES[:position], "%s imports %s" % (name, module))

    def test_no_engine_file_imports_tests_or_tools(self):
        for name in BUNDLES[:4]:                     # develop.py is about the tool, and may drive the tests' stand-in
            self.assertNotRegex(engine_source(name), r"(?m)^\s*(import|from)\s+(standin_chat|failing_chat|tools)")


class LineBudgetsAndStyle(unittest.TestCase):
    def test_every_bundle_is_within_its_budget(self):
        rows, within = develop.report()
        self.assertTrue(within, [(r["name"], r["total"]) for r in rows if not r["ok"]])

    def test_only_the_dataclass_decorator_and_no_execution_of_text(self):
        for name in BUNDLES:
            for node in ast.walk(ast.parse(engine_source(name))):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    for decorator in node.decorator_list:
                        text = ast.unparse(decorator)
                        self.assertTrue(text.startswith("dataclass"), "%s uses @%s" % (name, text))
                if isinstance(node, ast.Call):
                    called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    banned = FORBIDDEN_ATTRIBUTES if isinstance(node.func, ast.Attribute) else FORBIDDEN_NAMES + FORBIDDEN_ATTRIBUTES
                    self.assertNotIn(called, banned, "%s calls %s()" % (name, called))
                    if called == "load" and isinstance(node.func, ast.Attribute):
                        owner = ast.unparse(node.func.value)
                        self.assertNotIn(owner, ("yaml", "pickle", "marshal"), "%s uses %s.load" % (name, owner))

    def test_every_file_opens_with_the_same_overview(self):
        for name in BUNDLES:
            overview = ast.get_docstring(ast.parse(engine_source(name))) or ""
            for heading in ("WHAT THIS FILE DOES", "WHAT IT TAKES IN AND PRODUCES", "WHICH SHEETS SHOW ITS RESULTS",
                            "DESIGN RULES ENFORCED HERE", "HOW TO SANITY-CHECK IT"):
                self.assertIn(heading, overview, "%s lacks the overview part '%s'" % (name, heading))


class StaticWordingLint(unittest.TestCase):
    """No banned word in anything the engine ships. The one assignment in aiva0 that has to
    name the words is the allow-list."""

    def lintable_files(self):
        patterns = ("engine/*.py", "engine/pipeline.yaml", "engine/references/**/*", "docs/*.md", "Verifier.ipynb")
        files = []
        for pattern in patterns:
            files.extend(p for p in glob.glob(os.path.join(helpers.ROOT_DIR, pattern), recursive=True) if os.path.isfile(p))
        return files

    def test_no_banned_wording(self):
        for path in self.lintable_files():
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            if path.endswith("core.py"):
                start = text.index("BANNED_WORDING_PATTERNS = (")
                text = text[:start] + text[text.index(")\n", text.index("impact", start)):]
            text = re.sub(r"<!-- wording-policy-sentence -->.*?<!-- end -->", "", text, flags=re.S)
            self.assertEqual(core.has_banned_wording(text), "", "banned wording in %s" % os.path.relpath(path, helpers.ROOT_DIR))

    def test_no_domain_concept_in_engine_prompts_or_stop_words(self):
        domain_words = re.compile(r"\b(credit|loan|bank|capital|default|dose|dosing|patient|clearance|obligor|mortgage)\b", re.I)
        for pattern in ("engine/references/prompts/*", "engine/references/stopwords.txt", "engine/references/bridge_patterns.yaml"):
            for path in glob.glob(os.path.join(helpers.ROOT_DIR, pattern)):
                with open(path, encoding="utf-8") as handle:
                    self.assertIsNone(domain_words.search(handle.read()), "domain word in %s" % path)


def scan_workbook(test, path):
    """The dynamic lint for Output.xlsx: used by every end-to-end test."""
    import openpyxl
    import runner
    input_columns = {}
    for sheet_layout in runner.load_layout()["sheets"]:
        input_columns[sheet_layout["name"]] = {c["header"] for c in sheet_layout["columns"] if c.get("input_text")}
    workbook = openpyxl.load_workbook(path)
    for sheet in workbook.worksheets:
        headers = [cell.value for cell in sheet[1]]
        for row in sheet.iter_rows(min_row=2):
            for header, cell in zip(headers, row):
                if cell.value is None:
                    continue
                test.assertNotIsInstance(cell.value, float, "%s!%s holds a decimal number" % (sheet.title, cell.coordinate))
                if header in input_columns[sheet.title] or not isinstance(cell.value, str):
                    continue
                text = own_words(cell.value)
                where = "%s!%s: %s" % (sheet.title, cell.coordinate, cell.value[:120])
                test.assertEqual(core.has_banned_wording(text), "", where)
                test.assertIsNone(PYTHON_TRACES.search(text), where)
                test.assertIsNone(re.search(r"(?<![\w.])\d+\.0(?!\d)", text), "whole number shown with a decimal point: " + where)


def scan_document(test, path):
    """The dynamic lint for the two Word files."""
    import docx
    document = docx.Document(path)
    texts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            texts.extend(cell.text for cell in row.cells)
    for text in texts:
        test.assertEqual(core.has_banned_wording(own_words(text)), "", text[:120])
        test.assertIsNone(PYTHON_TRACES.search(own_words(text)), text[:120])


if __name__ == "__main__":
    unittest.main()
