"""signposts.py write|check: the table of contents, the part banners and every docstring's Used by / Uses / Holds,
generated from verifier.py itself. check exits 1 when any of them is stale."""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import ast, json, re, sys, symtable, textwrap
ENGINE_FILE = os.path.join(ENGINE, "verifier.py")
WIDTH = 118
SIGN = ("Used by:", "Uses:", "Holds:")
MODULE_DOC = '''"""
Verifier - verifier.py - the whole engine, in one file.

Reads a model's methodology, its package of code and data, and its documentation into numbered chunks; links each
chunk of the package to the chunks it takes something from and gives something to; and asks the organisation's
language model, through the chat() of cell 2, to explain each chunk of code, to find the chunks of the methodology
that bear on it, and to flag where the code may depart from them. One deliverable: Output.xlsm. Everything a run
does is recorded in the _Audit folder beside it.

The file is in four parts, in the order a run goes; each is one reviewer's contiguous share, and the contents below
give each part's and each section's lines. Every function's and class's docstring ends with its signposts:
  Used by - what calls it: a function, a notebook cell, or the runner by the name in STEP_FUNCTIONS;
  Uses    - the functions and classes of this file it calls;
  Holds   - the helpers written inside it, used only there.
A name from another section carries that section's number. The signposts are generated from the code, never
written by hand: a maintainer regenerates them after a change, and a check fails while any is stale.
"""'''
BANNERS = {
 "1": ["Runs in: cell 1 (setup), cell 2 (check_chat), cell 3 (review), cell 4 (verify).",
       "Entry points: setup, check_chat, review, verify; run_pipeline and run_step; step 01, prepare_run.",
       "Writes: the records run_manifest, step_records and audit_files; the _Audit folder. Reads them all back in cell 4."],
 "2": ["Runs in: cell 3, step 02 (read-inputs), for corners 1 and 3.",
       "Entry points: read_methodology and read_documentation, both through read_corner.",
       "Writes: the records chunks_canon (Chunks_Methodology), chunks_doc (Chunks_Documentation), info_rows, read_repairs."],
 "3": ["Runs in: cell 3, step 02 (read-inputs) for corner 2, and step 03 (link-chunks).",
       "Entry points: read_package; link_chunks.",
       "Writes: the records model_units (Chunks_Model), package_info and info_rows; unit_links."],
 "4": ["Runs in: cell 3, steps 04 (interpret-code) and 05 (search-methodology), and after every step.",
       "Entry points: interpret_code; search_methodology; rebuild_outputs, which writes Output.xlsm after each step.",
       "Writes: the records llm_calls; Output.xlsm, with its five sheets and its macro."]}
DOCSTRINGS = {"notebook_folder": "The workspace folder the notebook sits in; the working folder when that cannot be found.",
              "notebook_settings": "The run's settings as the notebook gives them: the defaults, with who is running it.",
              "node_id": "The id flowR gave a node of its syntax tree, or None."}
def generate(text):
    lines = text.split("\n")
    # 1. the old three-part banners go
    out, i = [], 0
    while i < len(lines):
        if re.fullmatch(r"# ={90,100}", lines[i]) and i + 2 < len(lines) and re.fullmatch(r"# ={90,100}", lines[i + 2]):
            i += 3
            while i < len(lines) and not lines[i].strip() and out and not out[-1].strip():
                i += 1
            continue
        out.append(lines[i]); i += 1
    text = "\n".join(out)
    # 2. the module's docstring
    tree = ast.parse(text)
    first = tree.body[0]
    lines = text.split("\n")
    lines[first.lineno - 1:first.end_lineno] = MODULE_DOC.split("\n")
    text = "\n".join(lines)
    # 3. a docstring for each definition that lacks one
    tree = ast.parse(text); lines = text.split("\n")
    for node in sorted((n for n in tree.body if isinstance(n, ast.FunctionDef) and not ast.get_docstring(n)), key=lambda n: -n.lineno):
        indent = " " * (node.body[0].col_offset)
        lines.insert(node.body[0].lineno - 1, indent + '"""%s"""' % DOCSTRINGS[node.name])
    text = "\n".join(lines)
    # 4. the part banners' second lines, and the sections
    lines = [l for l in text.split("\n") if not (l.startswith("# Runs in: ") or l.startswith("# Entry points: ") or l.startswith("# Writes: "))]
    out = []
    for n, line in enumerate(lines):
        out.append(line)
        match = re.match(r"# PART (\d) of 4 - ", line)
        if match:
            out += ["# " + b for b in BANNERS[match.group(1)]]
    text = "\n".join(out)
    # 5. the signposts
    tree = ast.parse(text); lines = text.split("\n")
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    names = {n.name for n in defs}
    headers = [(i + 1, m.group(1)) for i, l in enumerate(lines) for m in [re.match(r"# -{8,} (\d+\.\d+) ", l)] if m]
    def section(line):
        found = ""
        for start, key in headers:
            if start <= line: found = key
        return found
    where = {n.name: (n.lineno, section(n.lineno)) for n in defs}
    table = symtable.symtable(text, "verifier.py", "exec")
    scopes = {(child.get_name(), child.get_lineno()): child for child in table.get_children()}
    def refs(scope):
        found = set()
        for sym in scope.get_symbols():
            name = sym.get_name()
            if name in names and sym.is_referenced() and (sym.is_global() or not (sym.is_local() or sym.is_free() or sym.is_parameter())):
                found.add(name)
        for child in scope.get_children():
            found |= refs(child)
        return found
    uses, users = {}, {n: set() for n in names}
    for node in defs:
        line = node.lineno if not getattr(node, "decorator_list", None) else node.decorator_list[0].lineno
        scope = scopes.get((node.name, node.lineno)) or scopes.get((node.name, line))
        uses[node.name] = (refs(scope) - {node.name}) if scope else set()
        for used in uses[node.name]:
            users[used].add(node.name)
    extra = {n: [] for n in names}
    cells = ["".join(c["source"]) for c in json.load(open(NOTEBOOK))["cells"] if c["cell_type"] == "code"]
    for number, cell in enumerate(cells, 1):
        for name in sorted(set(re.findall(r"verifier\.(\w+)\(", cell)) & names):
            extra[name].append("the notebook's cell %d" % number)
    steps = ast.literal_eval(next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "STEP_FUNCTIONS" for t in n.targets)).value)
    for name in steps:
        extra[name].append("the runner, by its name in STEP_FUNCTIONS (%s)" % where["run_step"][1] if where[name][1] != where["run_step"][1] else "the runner, by its name in STEP_FUNCTIONS")
    for node in tree.body:                                   # used at import, by a statement of the module itself
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id in names:
                    extra[sub.id].append("the module, as it is imported")
    def label(name, own):
        return name if where[name][1] == own else "%s (%s)" % (name, where[name][1])
    def wrapped(indent, head, items):
        body = head + " " + ", ".join(item.replace(" ", "\x00") for item in items) + "."   # a name and its section stay together
        return [l.replace("\x00", " ") for l in textwrap.wrap(body, width=WIDTH - len(indent), subsequent_indent=" " * (len(head) + 1),
                                                                break_on_hyphens=False, break_long_words=False)]
    for node in sorted(defs, key=lambda n: -n.lineno):
        own = where[node.name][1]
        doc = node.body[0]
        raw = lines[doc.lineno - 1:doc.end_lineno]
        indent = " " * doc.col_offset
        cut = next((i for i, l in enumerate(raw) if i and l.strip().startswith(SIGN)), None)
        if cut is not None:
            kept = raw[:cut]
        else:
            kept = list(raw)
            kept[-1] = kept[-1].rstrip()[:-3].rstrip()
            if not kept[-1].strip():
                kept.pop()
        block = []
        who = [label(n, own) for n in sorted(users[node.name], key=lambda n: where[n][0])] + list(dict.fromkeys(extra[node.name]))
        block += wrapped(indent, "Used by:", who or ["nothing in this file"])
        if uses[node.name]:
            block += wrapped(indent, "Uses:", [label(n, own) for n in sorted(uses[node.name], key=lambda n: where[n][0])])
        held = [n.name for n in node.body if isinstance(n, ast.FunctionDef)] if isinstance(node, ast.FunctionDef) else []
        if held:
            block += wrapped(indent, "Holds:", held)
        new = kept + [indent + l for l in block]
        new[-1] += '"""'
        lines[doc.lineno - 1:doc.end_lineno] = new
    text = "\n".join(lines)
    # 6. the contents, in two passes: its own length moves every line below it
    def contents(text):
        lines = text.split("\n")
        parts = [(i + 1, m.group(1), m.group(2)) for i, l in enumerate(lines) for m in [re.match(r"# PART (\d) of 4 - (.*?)   \(", l)] if m]
        secs = [(i + 1, m.group(1), m.group(2)) for i, l in enumerate(lines) for m in [re.match(r"# -{8,} (\d+\.\d+) (.*)$", l)] if m]
        ends = {}
        marks = sorted([(l, "P" + k) for l, k, _ in parts] + [(l, "S" + k) for l, k, _ in secs])
        total = len(lines) - (1 if lines and not lines[-1] else 0)   # the newline that ends the file opens no line
        for index, (line, key) in enumerate(marks):          # a part starts at the rule above its title
            later = [(l, k) for l, k in marks[index + 1:] if k[0] == "P" or key[0] == "S"]
            ends[key] = (later[0][0] - (2 if later[0][1][0] == "P" else 1)) if later else total
        block = ["# " + "=" * WIDTH, "# CONTENTS - four parts, in the order a run goes; each part is one reviewer's contiguous share of the file.", "#"]
        for pline, key, title in parts:
            block.append("#   PART %s   lines %5d-%-5d  %s   (reviewer %s)" % (key, pline - 1, ends["P" + key], title.lower(), key))
            for sline, skey, stitle in secs:
                if skey.split(".")[0] == key:
                    block.append("#     %-5s  lines %5d-%-5d  %s" % (skey, sline, ends["S" + skey], stitle))
        block += ["#", "# Every docstring ends with its signposts - Used by, Uses, Holds - generated from the code (see the docstring above).", "# " + "=" * WIDTH]
        return block
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("# CONTENTS - ")), None)
    if start is not None:
        end = next(i for i in range(start + 1, len(lines)) if re.fullmatch(r"# ={%d}" % WIDTH, lines[i]))
        del lines[start - 1:end + 1]
        while start - 2 >= 0 and not lines[start - 2].strip():   # and the blank lines it was set after
            del lines[start - 2]
            start -= 1
    anchor = next(i for i, l in enumerate(lines) if l.startswith("# PART 1 of 4")) - 1
    while not lines[anchor - 1].strip(): anchor -= 1
    placeholder = contents("\n".join(lines))
    lines[anchor:anchor] = ["", ""] + placeholder
    for _ in range(3):                                       # until the numbers stand still
        start = next(i for i, l in enumerate(lines) if l.startswith("# CONTENTS - ")) - 1
        fresh = contents("\n".join(lines))
        lines[start:start + len(fresh)] = fresh
    return "\n".join(lines)
if __name__ == "__main__":
    text = open(ENGINE_FILE).read()
    new = generate(text)
    if sys.argv[1] == "write":
        open(ENGINE_FILE, "w").write(new)
        print("signposts written")
    else:
        again = generate(new)
        print("idempotent:", again == new, "| the file's signposts are current:", new == text)
        sys.exit(0 if new == text else 1)
