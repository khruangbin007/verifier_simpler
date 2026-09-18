"""
AIVA 0.0.1 - aiva4_checks.py - deterministic checks, final statuses and flagged items. For Reviewer 4.

WHAT THIS FILE DOES
  It confirms or contradicts, by code, every link that involves a formula, a number, a
  table or a stated rule, and then decides the final status of every unit:
    - formulas: code and methodology as expression trees, symbols aligned BEFORE comparing,
      a bounded symbolic step, then 200 seeded sample points; "differs" always comes with a
      counterexample, and "could not be decided" is never clean;
    - values: one comparison rule for parameter tables, numbers in code, numbers in roxygen
      text and numbers in the documentation; its text is shown on Model_Package_Info;
    - rules: floors, caps and thresholds stated in a passage, looked for in the code first;
    - in-package documentation: roxygen blocks and help pages against the code, no AI;
    - accounting: status rules applied top to bottom, one flagged item per unit and
      category, and the four-part coverage identity checked on every run.

WHAT IT TAKES IN AND PRODUCES
  In: all units and chunks, parameter_tables, the graph ledger, the bridge vocabulary,
  judgement_problems, second_opinions, doc_judgements, unresolved_references, package_info.
  Out: math_checks, value_checks, rule_checks, package_doc_checks, new ledger edges,
  unit_status, flagged_items, coverage.

WHICH SHEETS SHOW ITS RESULTS
  The assessment columns and "Overall status" of both mapping sheets, Mapping_Coverage,
  Flagged_Items, and the comparison rule on Model_Package_Info.

DESIGN RULES ENFORCED HERE (function names in brackets)
  R1  no claim without evidence: "differs" only with a counterexample     [compare_formulas]
  R2  nothing is dropped: every unit gets exactly one status; every unit that is not clean
      is named by a flagged item; the run stops if this does not hold     [check_identity]
  R3  the AI proposes, code disposes: alignment by AI is validated one-to-one and fixed
      before the comparison, never chosen because it makes two sides agree [align]
  R5  same input, same output: fixed seed, fixed orders                   [sample_points]
  R7  no input text is executed: trees are evaluated by AIVA's own evaluator and are turned
      into SymPy objects node by node; no string is ever parsed by SymPy  [evaluate, to_sympy]
  R10 no field rates seriousness: items carry a category and a neutral next step only

HOW TO SANITY-CHECK IT
  Run `python -m unittest engine/tests/test_aiva4_checks.py`. In the notebook run the
  appendix cell "Reviewer 4 sanity check" on sample F_capital_known with the stand-in chat,
  then open Output.xlsx: the row of function cond_pd reads "Numerical check: differs. With
  ...", its status is "Traced - differences flagged", and Flagged_Items holds an item of the
  category "Code differs from methodology" for it.
"""
import math
import random
import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import aiva0_shared as shared
import aiva1_documents
import aiva2_package
import aiva3_mapping

SKILL_VERSIONS = {"check-mathematics": "0.0.1", "check-values": "0.0.1", "check-rules": "0.0.1",
                  "check-package-docs": "0.0.1", "account-coverage": "0.0.1"}

class AivaDefect(Exception):
    """The run contradicts itself (the coverage identity does not hold). This is a defect in
    AIVA, not in the model under review, and the message says which part failed."""

# ---------------------------------------------------------------- the one rule for comparing values
VALUE_RULE_TEXT = (
    "Values are compared under one rule, and there is no hidden tolerance. Percent, basis points and scientific "
    "notation are first converted to plain decimals. A value agrees at stated precision when rounding it to the "
    "number of decimals of the methodology's value gives the methodology's value, under round-half-even or "
    "round-half-up. When a documentation value is written with fewer decimals than the methodology's value, the "
    "comparison is made at that coarser precision and reported as such. Otherwise the values differ, and both are "
    "shown with their citations.")

def compare_values(stated, other, exact=False):
    """The value rule of plan 2.8. `stated` is the methodology's number and `other` the value
    compared with it, both as {"value", "decimals", ...} from shared.parse_number. `exact`
    marks a stored or coded value, which has no written precision of its own.
    Returns (outcome, note): agrees | agrees at stated precision | agrees at the coarser
    precision | differs; the note names the rounding convention when the two differ."""
    m, v = Decimal(stated["value"]), Decimal(other["value"])
    if m == v:
        return "agrees", ""
    if not exact and other["decimals"] < stated["decimals"]:
        step = Decimal(1).scaleb(-int(other["decimals"]))
        if v in (m.quantize(step, rounding=ROUND_HALF_EVEN), m.quantize(step, rounding=ROUND_HALF_UP)):
            return "agrees at the coarser precision", ""
        return "differs", ""
    step = Decimal(1).scaleb(-int(stated["decimals"]))
    even, up = v.quantize(step, rounding=ROUND_HALF_EVEN), v.quantize(step, rounding=ROUND_HALF_UP)
    if m in (even, up):
        return "agrees at stated precision", "" if even == up else "under round-half-even" if m == even else "under round-half-up"
    return "differs", ""

def number_of(text):
    """The single number a table cell or a default holds, or None."""
    found = shared.find_numbers(str(text))
    return found[0] if len(found) == 1 else shared.parse_number(str(text).strip())

# ---------------------------------------------------------------- expression tree -> SymPy, node by node
class NotEvaluable(Exception):
    """The formula uses an operation AIVA cannot evaluate. The message names it."""

def to_sympy(expr):
    """One explicit table from AIVA's tree to SymPy objects. Numbers become exact rationals.
    No string is ever handed to SymPy's parser. Enforces: R7"""
    import sympy
    args = [to_sympy(arg) for arg in expr.args] if expr.op not in ("num", "sym") else []
    if expr.op == "num":
        return sympy.Rational(str(Decimal(expr.value)))
    if expr.op == "sym":
        return sympy.Symbol(expr.name, real=True)
    simple = {"add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b,
              "div": lambda a, b: a / b, "pow": lambda a, b: a ** b, "neg": lambda a: -a}
    if expr.op in simple:
        return simple[expr.op](*args)
    if expr.op == "cmp":
        relation = {"<": sympy.Lt, "<=": sympy.Le, ">": sympy.Gt, ">=": sympy.Ge, "==": sympy.Eq, "!=": sympy.Ne}[expr.name]
        return relation(*args)
    if expr.op == "piecewise" or (expr.op == "call" and expr.name == "piecewise"):
        return sympy.Piecewise((args[1], args[0]), (args[2], True))
    calls = {"exp": sympy.exp, "log": sympy.log, "sqrt": sympy.sqrt, "abs": sympy.Abs, "max": sympy.Max, "min": sympy.Min,
             "floor": sympy.floor, "ceiling": sympy.ceiling, "log1p": lambda x: sympy.log(1 + x), "expm1": lambda x: sympy.exp(x) - 1,
             "normal_cdf": lambda x: (1 + sympy.erf(x / sympy.sqrt(2))) / 2,
             "normal_inverse": lambda x: sympy.sqrt(2) * sympy.erfinv(2 * x - 1)}
    if expr.op == "call" and expr.name in calls:
        return calls[expr.name](*args)
    raise NotEvaluable("'%s'" % (expr.name or expr.op))

def symbolic_step(code_tree, stated_tree, settings):
    """Bounded symbolic work: expand the difference always; simplify fully only for small
    trees; nothing for very large ones. "agrees" only when the difference is exactly zero;
    a difference that does not reduce proves nothing and the numeric step decides."""
    size = len(list(shared.expr_walk(code_tree))) + len(list(shared.expr_walk(stated_tree)))
    if size > 400:
        return "skipped (size)"
    try:
        import sympy
        difference = sympy.expand(to_sympy(code_tree) - to_sympy(stated_tree))
        if difference != 0 and size <= 60:
            difference = sympy.simplify(difference)
        return "agrees" if difference == 0 else "not shown equal"
    except Exception:                                   # SymPy could not handle it: the numeric step decides
        return "not shown equal"

# ---------------------------------------------------------------- AIVA's own numeric evaluator
def evaluate(expr, values):
    """The value of a tree at one point. Returns None where the point is outside the domain
    of a function used (such a point is not valid and is not counted). Enforces: R7"""
    from scipy import special
    op = expr.op
    if op == "num":
        return float(Decimal(expr.value))
    if op == "sym":
        return values[expr.name]
    args = [evaluate(arg, values) for arg in expr.args]
    if any(arg is None for arg in args):
        return None
    try:
        if op in ("add", "sub", "mul", "neg"):
            return {"add": lambda: args[0] + args[1], "sub": lambda: args[0] - args[1], "mul": lambda: args[0] * args[1], "neg": lambda: -args[0]}[op]()
        if op == "div":
            return args[0] / args[1] if args[1] != 0 else None
        if op == "pow":
            result = args[0] ** args[1] if not (args[0] == 0 and args[1] < 0) else None
            return result if isinstance(result, float) or isinstance(result, int) else None
        if op == "cmp":
            return {"<": args[0] < args[1], "<=": args[0] <= args[1], ">": args[0] > args[1], ">=": args[0] >= args[1],
                    "==": args[0] == args[1], "!=": args[0] != args[1]}[expr.name]
        if op == "piecewise" or (op == "call" and expr.name == "piecewise"):
            return args[1] if args[0] else args[2]
        name, x = expr.name, args[0]
        if name in ("log", "log1p"):
            return (math.log(x) if x > 0 else None) if name == "log" else (math.log1p(x) if x > -1 else None)
        if name == "sqrt":
            return math.sqrt(x) if x >= 0 else None
        if name == "normal_inverse":
            return float(special.ndtri(x)) if 0 < x < 1 else None
        plain = {"exp": math.exp, "expm1": math.expm1, "abs": abs, "floor": math.floor, "ceiling": math.ceil,
                 "normal_cdf": lambda value: float(special.ndtr(value))}
        if name in plain:
            return float(plain[name](x))
        if name in ("max", "min"):
            return max(args) if name == "max" else min(args)
        if name == "round":
            return float(round(x, int(args[1]) if len(args) > 1 else 0))
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    raise NotEvaluable("'%s'" % (expr.name or op))

def unit_interval_symbols(tree):
    """Symbols that sit under a square root, a logarithm or the inverse normal function are
    drawn from (0, 1), which keeps most sample points inside the domain."""
    narrow = set()
    for node in shared.expr_walk(tree):
        if node.op == "call" and node.name in ("sqrt", "log", "normal_inverse", "log1p"):
            narrow.update(shared.expr_symbols(node))
    return narrow

def sample_points(trees, symbols, settings, data_values):
    """The sample points: a fixed, recorded seed; ranges (0, 1), (1, 10) and (-10, 10) in turn;
    symbols with a narrow domain always from (0, 1); symbols supplied by a stored table take
    its values row by row; and, on purpose, points at, just below and just above every
    constant that appears in a comparison, a maximum or a minimum. Enforces: R5"""
    generator = random.Random(int(settings["numeric_seed"]))
    narrow = set().union(*[unit_interval_symbols(tree) for tree in trees])
    ranges = ((0.0, 1.0), (1.0, 10.0), (-10.0, 10.0))
    points = []
    for number in range(int(settings["numeric_points"])):
        low, high = ranges[number % 3]
        point = {}
        for symbol in symbols:
            if symbol in data_values:
                point[symbol] = data_values[symbol][number % len(data_values[symbol])]
            else:
                point[symbol] = generator.uniform(0.0, 1.0) if symbol in narrow else generator.uniform(low, high)
        points.append(point)
    thresholds = set()
    for tree in trees:
        for node in shared.expr_walk(tree):
            if node.op in ("cmp", "piecewise") or (node.op == "call" and node.name in ("max", "min", "piecewise")):
                thresholds.update(float(Decimal(arg.value)) for arg in node.args if arg.op == "num")
    for threshold in sorted(thresholds):
        for symbol in symbols:
            for value in (threshold, threshold * 0.999 - 1e-9, threshold * 1.001 + 1e-9):
                point = dict(points[len(points) % max(1, int(settings["numeric_points"]))])
                point[symbol] = value
                points.append(point)
    return points

def numeric_step(code_tree, stated_tree, symbols, settings, data_values):
    """Evaluate both trees at every sample point. Returns (result text, valid points,
    counterexample or None). Any disagreement beyond the relative tolerance is a difference,
    recorded with the inputs and both results. Enforces: R1"""
    valid, tolerance = 0, float(settings["relative_tolerance"])
    for point in sample_points([code_tree, stated_tree], symbols, settings, data_values):
        ours, theirs = evaluate(code_tree, point), evaluate(stated_tree, point)
        if ours is None or theirs is None or isinstance(ours, bool) or isinstance(theirs, bool):
            continue
        if math.isnan(ours) or math.isnan(theirs) or math.isinf(ours) or math.isinf(theirs):
            continue
        valid += 1
        if abs(ours - theirs) > tolerance * max(1.0, abs(ours), abs(theirs)):
            return "differs", valid, {"inputs": {s: point[s] for s in symbols}, "code": ours, "methodology": theirs}
    if valid < int(settings["min_valid_points"]):
        return "not run", valid, None
    return "agrees (%d points)" % valid, valid, None

# ---------------------------------------------------------------- symbol alignment (fixed before comparing)
def align(code_symbols, stated_symbols, bridge_by_term):
    """Align code symbols with the symbols of the stated formula, by code only: identical
    normalised names; the same name apart from capital letters when that is unambiguous;
    then the bridge vocabulary (both described by the same words). One-to-one. Returns
    (pairs [(code, stated, matched by)], code symbols left, stated symbols left)."""
    pairs, left_code, left_stated = [], list(code_symbols), list(stated_symbols)
    def take(code, stated, how):
        pairs.append((code, stated, how))
        left_code.remove(code)
        left_stated.remove(stated)
    for code in list(left_code):
        if code in left_stated:
            take(code, code, "name")
    for code in list(left_code):
        same = [s for s in left_stated if s.lower() == code.lower()]
        rivals = [c for c in left_code if c.lower() == code.lower()]
        if len(same) == 1 and len(rivals) == 1:
            take(code, same[0], "name, apart from capital letters")
    def described(symbol):
        return {word for entry in bridge_by_term.get(symbol, []) for word in entry["words"]}
    for code in list(left_code):
        mine = described(code) | set(aiva3_mapping.split_words(code.replace("$", " "), set()))
        scores = []
        for stated in left_stated:
            theirs = described(stated)
            if mine and theirs:
                scores.append((len(mine & theirs) / len(mine | theirs), stated))
        scores.sort(key=lambda item: (-item[0], item[1]))
        if scores and scores[0][0] >= 0.5 and (len(scores) == 1 or scores[1][0] < scores[0][0]):
            take(code, scores[0][1], "vocabulary")
    return pairs, left_code, left_stated

def rename(tree, mapping, substitute):
    """The code tree written in the stated formula's symbols; defaults put in as numbers."""
    if tree.op == "sym":
        if tree.name in substitute:
            return shared.Expr("num", value=substitute[tree.name])
        return shared.Expr("sym", name=mapping.get(tree.name, tree.name))
    return shared.Expr(tree.op, name=tree.name, value=tree.value, args=tuple(rename(arg, mapping, substitute) for arg in tree.args))

def right_side(tree):
    return tree.args[1] if tree.op == "eq" else tree

def prepare_alignment(code_tree, stated_tree, defaults, bridge_by_term):
    """Everything about one comparison that is settled before any number is computed: the
    aligned pairs, the defaults put in (only where the stated formula shows that very
    number), and what is still left for the align-symbols question."""
    code_side, stated_side = right_side(code_tree), right_side(stated_tree)
    pairs, left_code, left_stated = align(sorted(shared.expr_symbols(code_side)), sorted(shared.expr_symbols(stated_side)), bridge_by_term)
    constants = {node.value for node in shared.expr_walk(stated_side) if node.op == "num"}
    substitute = {}
    for symbol in list(left_code):
        number = number_of(defaults.get(symbol, "")) if defaults.get(symbol) else None
        if number and number["value"] in constants:
            substitute[symbol] = number["value"]
            left_code.remove(symbol)
    return {"code": code_side, "stated": stated_side, "pairs": pairs, "left_code": left_code, "left_stated": left_stated,
            "substitute": substitute}

def compare_formulas(prepared, settings, data_values):
    """Symbolic step, then numeric step, on an alignment that is already fixed. Returns the
    outcome fields of a MathCheck. Enforces: R1, R3"""
    if prepared["left_code"] or prepared["left_stated"]:
        return {"outcome": shared.CHECK_UNDECIDED, "undecided_reason": shared.UNDECIDED_REASONS[2], "symbolic": "not run",
                "numeric": "not run", "counterexample": None, "points_valid": 0}
    mapping = {code: stated for code, stated, _ in prepared["pairs"]}
    code_tree = rename(prepared["code"], mapping, prepared["substitute"])
    symbols = sorted(set(shared.expr_symbols(prepared["stated"])) | set(shared.expr_symbols(code_tree)))
    values = {mapping.get(symbol, symbol): rows for symbol, rows in data_values.items()}
    result = {"symbolic": symbolic_step(code_tree, prepared["stated"], settings), "numeric": "not run",
              "counterexample": None, "points_valid": 0, "undecided_reason": None}
    if result["symbolic"] == "agrees":
        return dict(result, outcome="agrees")
    try:
        numeric, valid, counterexample = numeric_step(code_tree, prepared["stated"], symbols, settings, values)
    except NotEvaluable:
        return dict(result, outcome=shared.CHECK_UNDECIDED, undecided_reason=shared.UNDECIDED_REASONS[4])
    result.update(numeric=numeric, points_valid=valid, counterexample=counterexample)
    if numeric == "differs":
        return dict(result, outcome="differs")
    if numeric == "not run":
        return dict(result, outcome=shared.CHECK_UNDECIDED, undecided_reason=shared.UNDECIDED_REASONS[5])
    return dict(result, outcome="agrees")

# ---------------------------------------------------------------- what every check step reads
CODE_RELATIONS = ("Implements", "Partly implements", "Differs from")
PROSE_FORMULA_PHRASES = ("product of", "sum of", "multiplied by", "divided by", "ratio of", "square root of", " times the ")

def load_world(ctx):
    """Units, chunks, the graph and the latest link of every linked pair, read once per step."""
    units, canon, doc = ctx.read("model_units"), ctx.read("chunks_canon"), ctx.read("chunks_doc")
    ledger = ctx.read("graph_ledger")
    world = {"units": units, "canon": canon, "doc": doc, "ledger": ledger, "graph": aiva3_mapping.load_graph(ledger),
             "by_ref": {record["ref"]: record for record in units + canon + doc}, "links": {}, "children": {},
             "tables": {table["unit_ref"]: table for table in ctx.read("parameter_tables")}, "bridge": {}}
    for record in ledger:
        if record["record_type"] == "edge" and record["kind"] == "corresponds":
            world["links"][(record["source"], record["target"])] = record      # a later edge has the last word
    for unit in units:
        if unit.get("parent_ref"):
            world["children"].setdefault(unit["parent_ref"], []).append(unit)
    for entry in ctx.read("bridge_vocabulary"):
        world["bridge"].setdefault(entry["term"], []).append(entry)
    return world

def linked(world, ref, prefix, relations=shared.LINKING_RELATIONS):
    """References in one corner ("C-", "D-", "M-") that `ref` is linked to, either way round."""
    found = [t for (s, t), e in world["links"].items() if s == ref and t.startswith(prefix) and e["relation"] in relations]
    found += [s for (s, t), e in world["links"].items() if t == ref and s.startswith(prefix) and e["relation"] in relations]
    return sorted(set(found))

def check_edge(ctx, world, source, target, how, sentence, relation=None):
    """A check never rewrites a link: it appends a new edge on the same pair, which then has
    the last word in the workbook and in the status rules."""
    previous = world["links"].get((source, target), {})
    text = (previous.get("evidence", {}).get("how_text", "") + "\n" + sentence).strip()
    return shared.Edge(source, target, "corresponds", how, ctx.provenance, relation=relation or previous.get("relation", ""),
                       confidence=previous.get("confidence"), evidence={"how_text": text, "check": True})

def number_text(value):
    return shared.plain_number(float("%.6g" % value)) if isinstance(value, float) else str(value)

# ---------------------------------------------------------------- step 11: check-mathematics
def stated_formula(chunk, prose_answers):
    """The formula a passage states, as (tree, source, reason it cannot be used). A passage
    without any formula gives (None, "", "") and needs no mathematical check."""
    equation = chunk.get("equation")
    if equation:
        if equation["readable"]:
            source = "inline notation" if equation["source_form"] == "inline" else "structured markup"
            return shared.expr_from_dict(equation["expression"]), source, ""
        image = equation["source_form"] == "image" or bool(equation.get("image_sha256"))
        return None, "", shared.UNDECIDED_REASONS[0] if image else shared.UNDECIDED_REASONS[1]
    answer = prose_answers.get(chunk["ref"])
    if answer is not None:
        return (answer, "read by AI from prose", "") if answer != "unusable" else (None, "", shared.UNDECIDED_REASONS[1])
    return None, "", ""

def code_forms(unit, world):
    """The formulas a unit offers for comparison, as (tree, defaults, reference it came from).
    A function offers its composed form and the forms of the statements inside it; a
    statement offers its own expression and its composed form."""
    forms = []
    members = [unit] + (world["children"].get(unit["ref"], []) if unit["kind"] == shared.KIND_FUNCTION else [])
    owner = unit if unit["kind"] == shared.KIND_FUNCTION else world["by_ref"].get(unit.get("parent_ref") or "", unit)
    defaults = {shared.normalise_symbol(name): default for name, default in ((owner.get("code") or {}).get("formals") or ()) if default}
    for member in members:
        code = member.get("code") or {}
        for form in ("expression", "composed"):
            if code.get(form) and code[form] not in [f[3] for f in forms]:
                forms.append((shared.expr_from_dict(code[form]), defaults, member["ref"], code[form]))
    return [(tree, defaults, ref) for tree, defaults, ref, _ in forms]

def stored_values(world):
    """Numeric columns of stored tables, as {"object$column": [values]}, for the numeric step."""
    values = {}
    for table in world["tables"].values():
        for position, column in enumerate(table["header"]):
            cells = [number_of(row[position]) for row in table["rows"]]
            if cells and all(cells):
                values["%s$%s" % (table["object_name"], column)] = [float(Decimal(cell["value"])) for cell in cells]
    return values

def math_sentence(target_ref, result, pairs, substitute, ours="the code", theirs="the methodology"):
    """The words of one comparison, as shown in the Math check cell."""
    shown = ", ".join("%s = %s" % (code, stated) for code, stated, _ in pairs if code != stated)
    shown += (", " if shown and substitute else "") + ", ".join("%s = %s (its default)" % item for item in sorted(substitute.items()))
    with_text = " (with %s)" % shown if shown else ""
    if result["outcome"] == "agrees":
        how = shared.HOW_SYMBOLIC if result["symbolic"] == "agrees" else shared.HOW_NUMERIC_AGREES.format(n=result["points_valid"])
        return "%s: %s%s" % (target_ref, how, with_text)
    if result["outcome"] == "differs":
        example = result["counterexample"]
        inputs = ", ".join("%s = %s" % (name, number_text(value)) for name, value in sorted(example["inputs"].items()))
        return "%s: %s. With %s: %s gives %s, %s gives %s%s" % (target_ref, shared.HOW_NUMERIC_DIFFERS, inputs or "no inputs", ours,
                                                                number_text(example["code"]), theirs, number_text(example["methodology"]), with_text)
    return "%s: %s: %s" % (target_ref, shared.CHECK_UNDECIDED, result["undecided_reason"])

def combine(results):
    """Several forms of one unit against one formula: any form that agrees settles it; else
    any form that differs (with its counterexample); else it could not be decided."""
    for wanted in ("agrees", "differs"):
        for result in results:
            if result["outcome"] == wanted:
                return result
    return results[0]

def check_mathematics(ctx):
    """Step 11, skill check-mathematics. Pairs: every function or formula statement linked to
    a passage that states a formula; every roxygen \\deqn formula against the function it
    documents; every documentation equation against the methodology equation it is linked
    to. Alignment is settled first (by code, then by the validated align-symbols answer)
    and only then are the two sides compared. Enforces: R1, R3"""
    world, settings, references = load_world(ctx), ctx.settings, ctx.options["references_dir"]
    notation, values = aiva1_documents.load_notation(references), stored_values(world)
    pairs = [(world["by_ref"][s], world["by_ref"][t]) for (s, t), e in sorted(world["links"].items())
             if s.startswith("M-") and t.startswith("C-") and e["relation"] in CODE_RELATIONS
             and world["by_ref"][s]["kind"] in (shared.KIND_FUNCTION, shared.KIND_FORMULA)]
    prose = {}
    for _, chunk in pairs:
        if not chunk.get("equation") and chunk["kind"] == "Paragraph" and any(p in chunk["text"].lower() for p in PROSE_FORMULA_PHRASES):
            prose[chunk["ref"]] = aiva3_mapping.narrow_question("read-formula-from-prose", chunk["ref"], [("PARAGRAPH", chunk["text"][:3000])],
                                                                references, settings, more={"notation": notation})
    answers = ctx.ask([q for q in prose.values() if not q["too_large"]]) if prose else {}
    prose_answers = {}
    for ref, question in prose.items():
        final = answers.get(question["question_id"])
        if final and final["outcome"] == "accepted":
            if final["answer"]["formula"].strip():
                prose_answers[ref] = aiva1_documents.parse_formula(final["answer"]["formula"], notation)
        else:
            prose_answers[ref] = "unusable"
    jobs = []                                            # (unit, target, stated tree, source, [prepared forms], reason)
    for unit, chunk in pairs:
        tree, source, reason = stated_formula(chunk, prose_answers)
        if tree is None and not reason:
            continue
        forms = code_forms(unit, world) if tree is not None else []
        prepared = [dict(prepare_alignment(code, tree, defaults, world["bridge"]), through=ref) for code, defaults, ref in forms]
        jobs.append((unit, chunk, tree, source, prepared, reason or (shared.UNDECIDED_REASONS[3] if not prepared else "")))
    for unit in world["units"]:                          # roxygen formulas against the function they document
        target = world["by_ref"].get((unit.get("roxygen") or {}).get("documents_ref") or "")
        for formula in (unit.get("roxygen") or {}).get("formulas", ()):
            if target and formula["readable"] and target["kind"] == shared.KIND_FUNCTION:
                tree = shared.expr_from_dict(formula["expression"])
                prepared = [dict(prepare_alignment(code, tree, defaults, world["bridge"]), through=ref) for code, defaults, ref in code_forms(target, world)]
                jobs.append((target, unit, tree, "roxygen", prepared, "" if prepared else shared.UNDECIDED_REASONS[3]))
    for (s, t), edge in sorted(world["links"].items()):  # documentation equations against methodology equations
        left, right = world["by_ref"][s], world["by_ref"][t]
        if s.startswith("D-") and t.startswith("C-") and (left.get("equation") or {}).get("readable") and right.get("equation"):
            tree, source, reason = stated_formula(right, {})
            prepared = [dict(prepare_alignment(shared.expr_from_dict(left["equation"]["expression"]), tree, {}, world["bridge"]), through=s)] if tree else []
            jobs.append((left, right, tree, source, prepared, reason))
    questions = {}
    for unit, chunk, tree, source, prepared, reason in jobs:
        for form in prepared:
            if form["left_code"] and form["left_stated"]:
                question = aiva3_mapping.narrow_question(
                    "align-symbols", unit["ref"], [("CODE SYMBOLS", ", ".join(form["left_code"])), ("EQUATION SYMBOLS", ", ".join(form["left_stated"]))],
                    references, settings, more={"code_symbols": list(form["left_code"]), "equation_symbols": list(form["left_stated"])})
                form["question_id"] = question["question_id"]
                questions[question["question_id"]] = question
    answers = ctx.ask(list(questions.values())) if questions else {}
    checks, by_pair = [], {}
    for unit, chunk, tree, source, prepared, reason in jobs:
        results = []
        for form in prepared:
            final = answers.get(form.get("question_id", ""))
            if final and final["outcome"] == "accepted":
                for pair in final["answer"]["alignment"]:
                    form["pairs"].append((pair["code"], pair["equation"], "AI (validated)"))
                    form["left_code"].remove(pair["code"])
                    form["left_stated"].remove(pair["equation"])
            results.append(dict(compare_formulas(form, settings, values), form=form))
        if results:
            best = combine(results)
            form = best.pop("form")
        else:
            best = {"outcome": shared.CHECK_UNDECIDED, "undecided_reason": reason, "symbolic": "not run", "numeric": "not run",
                    "counterexample": None, "points_valid": 0}
            form = {"code": None, "pairs": [], "substitute": {}, "through": unit["ref"]}
        record = dict(best, check_id="", unit_ref=unit["ref"], target_ref=chunk["ref"], formula_source=source,
                      code_formula=shared.expr_to_text(form["code"]) if form["code"] is not None else "",
                      methodology_formula=shared.expr_to_text(right_side(tree)) if tree is not None else "",
                      alignment=[list(pair) for pair in form["pairs"]], seed=int(settings["numeric_seed"]), through=form["through"])
        ours = "the documentation" if unit.get("heading_chain") is not None else "the code"
        theirs = "the formula in the roxygen block" if source == "roxygen" else "the methodology"
        record["sentence"] = math_sentence(chunk["ref"], record, form["pairs"], form["substitute"], ours, theirs)
        by_pair[(unit["ref"], chunk["ref"])] = record
        checks.append(record)
    for record in checks:                                # a statement takes the function-level result for the same passage
        unit = world["by_ref"][record["unit_ref"]]
        parent = by_pair.get((unit.get("parent_ref"), record["target_ref"]))
        if unit["kind"] == shared.KIND_FORMULA and record["outcome"] != "agrees" and parent:
            record.update(outcome=parent["outcome"], undecided_reason=parent["undecided_reason"], counterexample=parent["counterexample"],
                          inherited_from=parent["unit_ref"], sentence="%s (taken from the check of the whole function %s)" % (parent["sentence"], parent["unit_ref"]))
    edges = []
    for number, record in enumerate(checks, start=1):
        record["check_id"] = "MC-%04d" % number
        if record["outcome"] != shared.CHECK_UNDECIDED and record["formula_source"] != "roxygen":
            how = shared.HOW_NUMERIC_DIFFERS if record["outcome"] == "differs" else shared.HOW_SYMBOLIC if record["symbolic"] == "agrees" \
                else shared.HOW_NUMERIC_AGREES.format(n=record["points_valid"])
            edges.append(check_edge(ctx, world, record["unit_ref"], record["target_ref"], how, record["sentence"],
                                    relation="Differs from" if record["outcome"] == "differs" else None))
    counts = {"pairs checked": len(checks)}
    for outcome in ("agrees", "differs", shared.CHECK_UNDECIDED):
        counts[outcome] = sum(1 for record in checks if record["outcome"] == outcome)
    return shared.StepResult({"math_checks": checks, "graph_ledger": aiva3_mapping.ledger_records(world["ledger"], edges)}, counts, [])

# ---------------------------------------------------------------- tables: reconciliation cell by cell
def quote(text, citation=""):
    """Input text is always shown visibly quoted, with its citation (same form as in aiva5)."""
    inner = shared.normalise_text(text or "").replace("\u201c", '"').replace("\u201d", '"')
    return "\u201c%s\u201d%s" % (inner, " (%s)" % citation if citation else "")

def plain_key(text):
    return re.sub(r"[\s_]+", " ", str(text)).strip().lower()

def header_words(header, stop):
    return frozenset(aiva3_mapping.split_words(re.sub(r"\(.*?\)|%", " ", header), stop))

def map_columns(ours, theirs, stop):
    """Columns matched by header: equal words after normalisation. Returns [(ours, theirs)]."""
    pairs, used = [], set()
    for column in ours["header"]:
        same = [other for other in theirs["header"] if other not in used and header_words(other, stop)
                and header_words(other, stop) == header_words(column, stop)]
        if len(same) == 1:
            pairs.append((column, same[0]))
            used.add(same[0])
    return pairs

def as_grid(table):
    """The one layout rule that is supported: a table in long form (two key columns and one
    value column) is turned into a grid, so that it can be laid over a printed grid."""
    kinds = table.get("column_types") or []
    if len(table["header"]) != 3 or len(kinds) != 3 or kinds[2] == "text" or "text" not in kinds[:2]:
        return None
    columns = list(dict.fromkeys(row[1] for row in table["rows"]))
    rows = {}
    for row in table["rows"]:
        rows.setdefault(row[0], {})[row[1]] = row[2]
    return {"header": [table["header"][0]] + columns, "row_key": [table["header"][0]],
            "rows": [[key] + [rows[key].get(column, "") for column in columns] for key in rows]}

def reconcile(ours, theirs, stop, exact, ai_map=None):
    """Compare two tables cell by cell under the value rule. `theirs` holds the values as
    stated (the methodology, or the documentation when it is compared with the package);
    `ours` holds the values compared with them. Columns are matched by header, else by
    values, else by the validated AI answer `ai_map`; rows by normalised key. Returns the
    fields of a ValueCheck."""
    pairs = [(a, b, "by header") for a, b in map_columns(ours, theirs, stop)]
    if len(pairs) < 2 and as_grid(ours) and len(map_columns(as_grid(ours), theirs, stop)) >= 2:
        ours = as_grid(ours)
        pairs = [(a, b, "by header (long form laid over the grid)") for a, b in map_columns(ours, theirs, stop)]
    if ai_map and len(pairs) < 2:
        pairs = [(a, b, "by AI (validated)") for a, b in ai_map["columns"]]
    key_name = (ours.get("row_key") or [""])[0]
    key_pair = next((p for p in pairs if p[0] == key_name), None) or (("(row number)", "(row number)", "") if not pairs else pairs[0])
    if ai_map and ai_map.get("key"):
        key_pair = (ai_map["key"][0], ai_map["key"][1], "by AI (validated)")
    position = lambda table, name: table["header"].index(name) if name in table["header"] else None
    def keyed(table, name):
        index = position(table, name)
        return {plain_key(row[index]) if index is not None else str(n): row for n, row in enumerate(table["rows"], start=1)}
    our_rows, their_rows = keyed(ours, key_pair[0]), keyed(theirs, key_pair[1])
    if len(pairs) < 2 and not (their_rows.keys() & our_rows.keys()):
        return {"column_map": [], "key_map": "", "cells": [], "only_in_package": [], "only_in_other": [], "outcome": "could not be compared"}
    if len(pairs) < 2:                                   # no usable headers: match columns by their values
        pairs = [key_pair] + columns_by_values(ours, theirs, our_rows, their_rows, key_pair, exact)
    cells = []
    for ours_name, theirs_name, _ in pairs:
        if (ours_name, theirs_name) == key_pair[:2]:
            continue
        percent = "%" in theirs_name and "%" not in ours_name
        for key in sorted(our_rows.keys() & their_rows.keys()):
            mine, stated = our_rows[key][position(ours, ours_name)], their_rows[key][position(theirs, theirs_name)]
            stated_number = shared.parse_number(stated.strip().rstrip("%"), "%") if percent and number_of(stated) else number_of(stated)
            my_number = number_of(mine)
            if stated_number and my_number:
                outcome, note = compare_values(stated_number, my_number, exact)
            else:
                outcome, note = ("agrees" if plain_key(mine) == plain_key(stated) else "differs"), ""
            cells.append({"row": our_rows[key][position(ours, key_pair[0])] if position(ours, key_pair[0]) is not None else key,
                          "column": ours_name, "value": mine, "stated": stated, "outcome": (outcome + " " + note).strip()})
    only_ours = [our_rows[k][position(ours, key_pair[0]) or 0] for k in sorted(our_rows.keys() - their_rows.keys())]
    only_theirs = [their_rows[k][position(theirs, key_pair[1]) or 0] for k in sorted(their_rows.keys() - our_rows.keys())]
    differs = any(cell["outcome"].startswith("differs") for cell in cells) or only_ours or only_theirs
    return {"column_map": [list(p) for p in pairs], "key_map": "%s = %s" % key_pair[:2], "cells": cells, "only_in_package": only_ours,
            "only_in_other": only_theirs, "outcome": "could not be compared" if not cells else "differs" if differs else "agrees"}

def columns_by_values(ours, theirs, our_rows, their_rows, key_pair, exact):
    """Match columns whose values agree with exactly one column on the other side for most keys."""
    pairs, common = [], sorted(our_rows.keys() & their_rows.keys())
    for i, ours_name in enumerate(ours["header"]):
        if ours_name == key_pair[0]:
            continue
        scores = []
        for j, theirs_name in enumerate(theirs["header"]):
            agree = sum(1 for key in common if number_of(our_rows[key][i]) and number_of(their_rows[key][j]) and
                        compare_values(number_of(their_rows[key][j]), number_of(our_rows[key][i]), exact)[0] != "differs")
            scores.append((agree, theirs_name))
        good = [name for agree, name in scores if common and agree * 2 > len(common)]
        if len(good) == 1:
            pairs.append((ours_name, good[0], "by values"))
    return pairs

def table_sentences(check, ours_label, theirs_label, target_ref):
    """The words of one table comparison, as shown in the workbook."""
    lines = ["row %s, column %s: %s %s, %s %s (%s row %s): %s" % (c["row"], c["column"], ours_label, c["value"], theirs_label,
             c["stated"], target_ref, c["row"], c["outcome"]) for c in check["cells"] if not c["outcome"].startswith("agrees") or " " in c["outcome"][7:]]
    lines += ["row %s is in %s only" % (row, ours_label) for row in check["only_in_package"]]
    lines += ["row %s is in %s only (%s)" % (row, theirs_label, target_ref) for row in check["only_in_other"]]
    if check["outcome"] == "could not be compared":
        return ["The table could not be laid over %s: no columns or row keys could be matched." % target_ref]
    agreed = sum(1 for c in check["cells"] if c["outcome"].startswith("agrees"))
    how = ", ".join(sorted({p[2] for p in check["column_map"] if p[2]}))
    return ["%d of %d values agree with %s (columns matched %s; rows identified by %s)." % (
        agreed, len(check["cells"]), target_ref, how or "by position", check["key_map"])] + lines

# ---------------------------------------------------------------- step 12: check-values
def numbers_with_context(text, stop):
    """Every number of a text with the words around it (four before, three after). Two numbers
    are only ever compared when they are attached to the same words."""
    found = []
    for number in shared.find_numbers(text or ""):
        before = aiva3_mapping.split_words(text[max(0, number["position"] - 60):number["position"]], stop)[-4:]
        after = aiva3_mapping.split_words(text[number["position"] + len(number["as_written"]):][:45], stop)[:3]
        found.append(dict(number, context=set(before + after)))
    return found

def prose_value_lines(text, stated_texts, stop, trivial, label):
    """Numbers in a documentation passage or a roxygen block against the numbers of the
    passages it is linked to. A number that is stated somewhere in the linked passages
    agrees; a number attached to the same words as a DIFFERENT stated number differs; a
    number without a counterpart is not compared and nothing is claimed about it."""
    stated = [dict(n, ref=ref) for ref, passage in stated_texts for n in numbers_with_context(passage, stop)]
    lines, differs, mine = [], False, numbers_with_context(text, stop)
    taken = [s for s in stated if any(compare_values(s, number)[0] != "differs" for number in mine)]   # stated numbers that found their equal
    for number in mine:
        if number["value"] in trivial:
            continue
        outcomes = [(compare_values(s, number), s) for s in stated]
        agreeing = [(o, s) for o, s in outcomes if o[0] != "differs"]
        if agreeing:
            (outcome, note), s = agreeing[0]
            lines.append("%s %s, methodology %s (%s): %s" % (label, number["as_written"], s["as_written"], s["ref"], (outcome + " " + note).strip()))
            continue
        close = sorted(((len(number["context"] & s["context"]), s["ref"], s) for s in stated if s not in taken and len(number["context"] & s["context"]) >= 2),
                       key=lambda item: (-item[0], item[1]))
        if close:
            differs = True
            lines.append("%s %s, methodology %s (%s): differs" % (label, number["as_written"], close[0][2]["as_written"], close[0][1]))
        else:
            lines.append("%s %s: not compared (no counterpart in the linked passages)" % (label, number["as_written"]))
    return lines, differs

def check_values(ctx):
    """Step 12, skill check-values: parameter tables against the tables they are linked to
    (a table that the judge did not link is still matched by its shape); documentation
    tables against methodology tables; numbers written in linked code; numbers in
    documentation passages and roxygen text. All under compare_values. Enforces: R1"""
    world, settings = load_world(ctx), ctx.settings
    stop = aiva3_mapping.load_word_lists(ctx.options["references_dir"])["stop"]
    trivial, checks, edges = set(settings["trivial_numbers"]), [], []
    chunk_table = lambda chunk: dict(chunk["table"], row_key=[chunk["table"]["header"][0]] if chunk["table"]["header"] else [])
    for unit in world["units"]:                          # 1. stored tables
        table = world["tables"].get(unit["ref"])
        if not table:
            continue
        targets = [ref for ref in linked(world, unit["ref"], "C-") + linked(world, unit["ref"], "D-") if world["by_ref"][ref].get("table")]
        if not any(ref.startswith("C-") for ref in targets):
            shapes = sorted(((aiva3_mapping.table_shape_score(table, c["table"], stop), c["ref"]) for c in world["canon"] if c.get("table")), reverse=True)
            if shapes and shapes[0][0] >= 2.0 and (len(shapes) == 1 or shapes[1][0] < shapes[0][0]):
                targets.append(shapes[0][1])
                edges.append(shared.Edge(unit["ref"], shapes[0][1], "corresponds", shared.HOW_TABLE, ctx.provenance, relation="Implements",
                                         evidence={"how_text": shared.HOW_TABLE + "."}))
        for target in sorted(set(targets)):
            result = reconcile(table, chunk_table(world["by_ref"][target]), stop, exact=True)
            labels = ("package", "methodology" if target.startswith("C-") else "documentation")
            checks.append(dict(result, unit_ref=unit["ref"], target_ref=target, what="parameter table", labels=list(labels),
                               sentences=table_sentences(result, labels[0], labels[1], target)))
    pending = {}                                         # tables that code could not lay over each other: ask which columns correspond
    for check in checks:
        if check["outcome"] == "could not be compared" and ctx.ask is not None:
            unit, other = world["by_ref"][check["unit_ref"]], world["by_ref"][check["target_ref"]]
            table = world["tables"][unit["ref"]]
            shown = "\n".join(["; ".join(table["header"])] + ["; ".join(row) for row in table["rows"][:3]])
            question = aiva3_mapping.narrow_question("map-table-columns", unit["ref"], [("PACKAGE TABLE (%s)" % unit["name"], shown)], ctx.options["references_dir"], settings,
                                                     passages=[(other["ref"], aiva3_mapping.passage_label(other), aiva3_mapping.passage_text(other, settings))],
                                                     more={"package_header": list(table["header"])})
            question["other_headers"] = {letter: list(world["by_ref"][ref]["table"]["header"]) for letter, ref in question["letters"].items()}
            pending[question["question_id"]] = (check, question)
    answers = ctx.ask([q for _, q in pending.values() if not q["too_large"]]) if pending else {}
    for question_id, (check, question) in sorted(pending.items()):
        final = answers.get(question_id)
        if final and final["outcome"] == "accepted" and final["answer"].get("table") != "NONE":
            answer = final["answer"]
            ai_map = {"columns": [(c["package"], c["other"]) for c in answer["columns"]], "key": (answer["key"]["package"], answer["key"]["other"])}
            result = reconcile(world["tables"][check["unit_ref"]], chunk_table(world["by_ref"][check["target_ref"]]), stop, exact=True, ai_map=ai_map)
            check.update(result, sentences=table_sentences(result, check["labels"][0], check["labels"][1], check["target_ref"]))
    for (source, target), edge in sorted(world["links"].items()):          # 2. documentation tables against methodology tables
        left, right = world["by_ref"][source], world["by_ref"][target]
        if source.startswith("D-") and target.startswith("C-") and left.get("table") and right.get("table") and edge["relation"] in shared.LINKING_RELATIONS:
            result = reconcile(chunk_table(left), chunk_table(right), stop, exact=False)
            checks.append(dict(result, unit_ref=source, target_ref=target, what="documentation table", labels=["documentation", "methodology"],
                               sentences=table_sentences(result, "documentation", "methodology", target)))
    for unit in world["units"]:                          # 3. numbers written in linked code
        code = unit.get("code") or {}
        has_children = unit["kind"] == shared.KIND_FUNCTION and any(c["kind"] == shared.KIND_FORMULA for c in world["children"].get(unit["ref"], []))
        numbers = [n for n in code.get("numbers", ()) if n["value"] not in trivial]
        if unit["kind"] not in (shared.KIND_FUNCTION, shared.KIND_FORMULA) or has_children or not numbers or not linked(world, unit["ref"], "C-"):
            continue
        family = [unit["ref"], unit.get("parent_ref")] + [c["ref"] for c in world["children"].get(unit.get("parent_ref") or "", [])]
        passages = sorted({ref for member in family if member for ref in linked(world, member, "C-")})
        cited = sorted({e["target"] for ref in passages for e in world["graph"]["out"].get(ref, []) if e["kind"] == "cross_reference"})
        stated = [dict(n, ref=ref, value=n["value"].lstrip("-")) for ref in passages + cited for n in shared.find_numbers(world["by_ref"][ref]["text"])]
        cells, missing = [], False                       # a sign belongs to the formula, which the mathematical check covers
        for number in numbers:
            match = next((s for s in stated if compare_values(s, number, exact=True)[0] != "differs"), None)
            missing = missing or match is None
            cells.append("%s: stated in %s as %s" % (number["as_written"], match["ref"], quote(match["as_written"])) if match
                         else "%s: not stated in the linked passages" % number["as_written"])
        checks.append({"unit_ref": unit["ref"], "target_ref": ", ".join(passages), "what": "number in code", "cells": cells, "column_map": [],
                       "key_map": "", "only_in_package": [], "only_in_other": [], "outcome": "not stated" if missing else "agrees", "sentences": cells})
    sources = [(c, "documentation", "number in documentation", [(r, world["by_ref"][r]["text"]) for r in linked(world, c["ref"], "C-")])
               for c in world["doc"] if c["kind"] == "Paragraph"]
    for unit in world["units"]:                          # 4. numbers in prose: documentation and roxygen text
        target = (unit.get("roxygen") or {}).get("documents_ref")
        if target and world["by_ref"][target]["kind"] == shared.KIND_FUNCTION:
            family = [target] + [c["ref"] for c in world["children"].get(target, [])]
            passages = sorted({ref for member in family for ref in linked(world, member, "C-")})
            text = " ".join(tag["text"] for tag in unit["roxygen"]["tags"] if tag["tag"] in ("description", "details", "param", "return"))
            sources.append((dict(unit, text=text), "package documentation", "number in roxygen", [(r, world["by_ref"][r]["text"]) for r in passages]))
    for source, label, what, stated_texts in sources:
        if stated_texts:
            lines, differs = prose_value_lines(source["text"], stated_texts, stop, trivial, label)
            if lines:
                checks.append({"unit_ref": source["ref"], "target_ref": ", ".join(ref for ref, _ in stated_texts), "what": what, "cells": lines,
                               "column_map": [], "key_map": "", "only_in_package": [], "only_in_other": [],
                               "outcome": "differs" if differs else "agrees", "sentences": lines})
    for number, check in enumerate(checks, start=1):
        check.update(check_id="VC-%04d" % number, rule_text=VALUE_RULE_TEXT)
        if check["what"] in ("parameter table", "documentation table") and check["outcome"] in ("agrees", "differs") and check["target_ref"].startswith("C-"):
            how = shared.HOW_VALUE_DIFFERS if check["outcome"] == "differs" else shared.HOW_VALUE_AGREES
            edges.append(check_edge(ctx, world, check["unit_ref"], check["target_ref"], how, check["sentences"][0],
                                    relation="Differs from" if check["outcome"] == "differs" else None))
    counts = {"checks": len(checks), "with a difference": sum(1 for c in checks if c["outcome"] in ("differs", "not stated"))}
    return shared.StepResult({"value_checks": checks, "graph_ledger": aiva3_mapping.ledger_records(world["ledger"], edges)}, counts, [])

# ---------------------------------------------------------------- step 13: check-rules
FLOOR_PHRASES = ("at least", "no less than", "not less than", "never below", "not below", "never taken below", "taken below",
                 "minimum of", "floor of", "floored at", "subject to a minimum")
CAP_PHRASES = ("at most", "no more than", "not more than", "not exceed", "never above", "maximum of", "cap of", "capped at",
               "subject to a maximum")

def stated_rules(chunk):
    """Floors and caps a passage states: (kind, number, sentence), recognised by generic phrases."""
    rules = []
    for sentence in re.split(r"(?<=[.;])\s+", chunk["text"]):
        lowered = sentence.lower()
        for kind, phrases in (("floor", FLOOR_PHRASES), ("cap", CAP_PHRASES)):
            phrase = next((p for p in phrases if p in lowered), None)
            numbers = shared.find_numbers(sentence)
            if phrase and numbers:
                after = [n for n in numbers if n["position"] >= lowered.find(phrase)]
                rules.append((kind, (after or numbers)[0], sentence.strip()))
                break
    return rules

def rule_in_trees(kind, number, members):
    """Code looks first: a maximum (for a floor), a minimum (for a cap), a piecewise expression
    or a comparison that holds the stated number, written as a number or held as the default
    of an argument. Returns where it was seen, or ""."""
    wanted = ("max",) if kind == "floor" else ("min",)
    defaults = {shared.normalise_symbol(name): number_of(default) for member in members
                for name, default in ((member.get("code") or {}).get("formals") or ()) if default and number_of(default)}
    def holds_number(arg):
        held = {"value": arg.value, "decimals": 0} if arg.op == "num" else defaults.get(arg.name) if arg.op == "sym" else None
        return bool(held) and compare_values(number, held, exact=True)[0] != "differs"
    for member in members:
        code = member.get("code") or {}
        for form in ("expression", "composed"):
            for node in shared.expr_walk(shared.expr_from_dict(code[form])) if code.get(form) else ():
                holds = node.op in ("cmp", "piecewise") or (node.op == "call" and node.name in wanted + ("piecewise",))
                if holds and any(holds_number(arg) for arg in node.args):
                    name = "maximum" if node.name == "max" else "minimum" if node.name == "min" else "condition"
                    return "%s with %s (%s, line %s)" % (name, number["as_written"], member["ref"], (member.get("lines") or ["?"])[0])
    return ""

def check_rules(ctx):
    """Step 13, skill check-rules. For every top-level function (and every formula statement
    outside a function) linked to a passage that states a floor or a cap: code inspection
    first; only when the code shows no such node is the check-rule question asked."""
    world, settings, references = load_world(ctx), ctx.settings, ctx.options["references_dir"]
    pending, checks = [], []
    for unit in world["units"]:
        if unit["kind"] not in (shared.KIND_FUNCTION, shared.KIND_FORMULA) or unit.get("parent_ref"):
            continue
        members = [unit] + world["children"].get(unit["ref"], [])
        passages = sorted({ref for member in members for ref in linked(world, member["ref"], "C-", CODE_RELATIONS)})
        for ref in passages:
            for kind, number, sentence in stated_rules(world["by_ref"][ref]):
                where = rule_in_trees(kind, number, members)
                record = {"unit_ref": unit["ref"], "target_ref": ref, "rule_as_stated": sentence, "rule_kind": kind, "rule_number": number["as_written"],
                          "located_by": "code inspection", "outcome": "applied" if where else "", "where_in_code": where}
                if not where:
                    code_text = aiva3_mapping.cut_code(unit["text"], int(settings["max_unit_chars"]))
                    question = aiva3_mapping.narrow_question("check-rule", unit["ref"], [("UNIT (%s)" % aiva3_mapping.passage_label(unit), code_text),
                                                             ("RULE AS STATED", sentence)], references, settings, more={"rule_text": sentence, "code_text": code_text})
                    pending.append((record, question))
                checks.append(record)
    answers = ctx.ask([q for _, q in pending if not q["too_large"]]) if pending else {}
    for record, question in pending:
        final = answers.get(question["question_id"])
        record["located_by"] = "AI (validated)"
        if final and final["outcome"] == "accepted":
            record.update(outcome=final["answer"]["outcome"], where_in_code=final["answer"].get("quote_from_unit", ""))
        else:
            record.update(outcome="could not be decided", where_in_code="")
    for number, record in enumerate(checks, start=1):
        record["check_id"] = "RC-%04d" % number
        what = "%s of %s stated in %s" % (record["rule_kind"].capitalize(), record["rule_number"], record["target_ref"])
        shown = {"applied": "present in the code", "not applied": "not present in the code", "applied differently": "applied differently in the code",
                 "could not be decided": "could not be decided (the AI's answer could not be used)"}[record["outcome"]]
        where = record["where_in_code"] if record["located_by"] == "code inspection" else quote(record["where_in_code"]) if record["where_in_code"] else ""
        record["sentence"] = "%s: %s%s; located by %s" % (what, shown, " (%s)" % where if where else "", record["located_by"])
    return shared.StepResult({"rule_checks": checks}, {"rules checked": len(checks), "not applied as stated": sum(1 for r in checks if r["outcome"] in ("not applied", "applied differently"))}, [])

# ---------------------------------------------------------------- step 14: check-package-docs (no AI)
def check_package_docs(ctx):
    """Step 14, skill check-package-docs. Roxygen blocks and help pages against the code they
    document: arguments, stated defaults, stated values, @export against NAMESPACE, usage
    against the signature, page in step with its source block, block and page present for
    exported objects, a data block for every stored object, example code that parses."""
    world, checks = load_world(ctx), []
    trivial = set(ctx.settings["trivial_numbers"])
    def add(unit_ref, about_ref, check, outcome, detail):
        checks.append({"unit_ref": unit_ref, "about_ref": about_ref, "check": check, "outcome": outcome, "detail": detail})
    blocks, pages = {}, {}
    for unit in world["units"]:
        if unit.get("roxygen") and unit["roxygen"]["documents_ref"]:
            blocks[unit["roxygen"]["documents_ref"]] = unit
        if unit.get("helppage"):
            pages[unit["helppage"]["rd_name"]] = unit
    for target_ref, block in sorted(blocks.items()):
        target, tags = world["by_ref"][target_ref], block["roxygen"]["tags"]
        tag_names = {tag["tag"] for tag in tags}
        if target.get("data"):
            described = set(re.findall(r"\\item\{([^{}]+)\}", block["text"]))
            missing = [name for name, _ in target["data"]["columns"] if name not in described and name != "(row name)"]
            add(target_ref, block["ref"], "columns described", "differs" if missing else "agrees",
                "The data block does not describe: %s" % ", ".join(missing) if missing else "Every column is described in %s" % block["ref"])
            continue
        if target["kind"] != shared.KIND_FUNCTION:
            continue
        formals = [name for name, _ in target["code"]["formals"]]
        documented = [name.strip() for tag in tags if tag["tag"] == "param" for name in tag["name"].split(",")]
        if tag_names & {"inheritParams", "rdname", "describeIn"}:
            add(block["ref"], target_ref, "arguments", "not applicable", "Arguments are documented elsewhere (inherited); not compared")
        else:
            missing = [name for name in formals if name not in documented and name != "..."]
            extra = [name for name in documented if name not in formals]
            parts = ["@param %s is documented; %s has no such argument" % (name, target["name"]) for name in extra]
            parts += ["argument %s of %s is not documented" % (name, target["name"]) for name in missing]
            add(block["ref"], target_ref, "arguments", "differs" if parts else "agrees",
                "; ".join(parts) + " (arguments: %s)" % ", ".join(formals) if parts else "Every argument is documented")
        defaults = dict(target["code"]["formals"])
        for tag in tags:
            stated = re.search(r"[Dd]efaults?(?:\s+(?:to|is|of|value))?:?\s+([-\w.%\"']+)", tag["text"]) if tag["tag"] == "param" else None
            if stated and defaults.get(tag["name"]):
                written, actual = stated.group(1).strip("\"'."), defaults[tag["name"]].strip("\"'")
                same = (compare_values(number_of(written), number_of(actual), exact=True)[0] != "differs") if number_of(written) and number_of(actual) \
                    else written == actual
                add(block["ref"], target_ref, "defaults", "agrees" if same else "differs",
                    "@param %s states the default %s; the code has %s" % (tag["name"], written, actual))
        exported = target["code"]["exported"]
        if exported is not None and ("export" in tag_names) != bool(exported):
            add(block["ref"], target_ref, "export", "differs", "The block has @export but NAMESPACE does not export %s" % target["name"]
                if "export" in tag_names else "NAMESPACE exports %s but the block has no @export" % target["name"])
        members = [target] + world["children"].get(target_ref, [])
        used = [n for member in members for n in (member.get("code") or {}).get("numbers", ())] + [number_of(d) for d in defaults.values() if d and number_of(d)]
        text = " ".join(tag["text"] for tag in tags if tag["tag"] in ("description", "details", "return"))
        absent = [n["as_written"] for n in shared.find_numbers(re.sub(r"\\d?eqn\{.*?\}\}?", " ", text)) if n["value"] not in trivial
                  and not any(compare_values(n, u, exact=True)[0] != "differs" for u in used)]
        if shared.find_numbers(text):
            add(block["ref"], target_ref, "stated values", "differs" if absent else "agrees",
                "The block states %s; the code of %s does not use %s" % (", ".join(absent), target["name"], "this value" if len(absent) == 1 else "these values")
                if absent else "Every value stated in the block is used in the code")
        for tag in tags:
            if tag["tag"] == "examples" and any(isinstance(r, tuple) for r in aiva2_package.parse_r_source(tag["text"])):
                add(block["ref"], target_ref, "examples", "differs", "The example code could not be parsed")
    for unit in world["units"]:
        page = unit.get("helppage")
        if page:
            target = next((u for u in world["units"] if u["kind"] == shared.KIND_FUNCTION and u["name"] == page["rd_name"] and not u["inside"]), None)
            if target:
                usage = re.search(r"\(([^)]*)\)", page["usage"])
                shown = [part.split("=")[0].strip() for part in usage.group(1).split(",")] if usage and usage.group(1).strip() else []
                formals = [name for name, _ in target["code"]["formals"]]
                add(unit["ref"], target["ref"], "usage", "agrees" if shown == formals else "differs",
                    "Usage shows (%s); the function has (%s)" % (", ".join(shown), ", ".join(formals)))
            if page["generated_from_ref"] is None:
                add(unit["ref"], target["ref"] if target else None, "page in step", "not applicable", "A hand-written page (no roxygen source block was found)")
            elif page["in_step_with_source"] is False:
                add(unit["ref"], page["generated_from_ref"], "page in step", "differs", "Out of step with its roxygen source %s: the arguments differ" % page["generated_from_ref"])
            else:
                add(unit["ref"], page["generated_from_ref"], "page in step", "agrees", "In step with its roxygen source %s" % page["generated_from_ref"])
        code = unit.get("code") or {}
        if unit["kind"] == shared.KIND_FUNCTION and not unit["inside"]:
            if code.get("exported") and unit["ref"] not in blocks:
                add(unit["ref"], None, "block present", "differs", "Exported function %s has no roxygen block" % unit["name"])
            elif code.get("exported") and unit["name"] not in pages and any(u.get("helppage") for u in world["units"]):
                add(unit["ref"], None, "page present", "differs", "Exported function %s has no help page" % unit["name"])
            elif unit["ref"] not in blocks:
                add(unit["ref"], None, "block present", "not applicable", "Internal function, no block")
        if unit.get("data") and unit["data"]["assessable"] and unit["ref"] not in blocks and unit["file"].startswith("data/"):
            add(unit["ref"], None, "data block present", "differs", "Stored object %s has no roxygen data block" % unit["name"])
    for number, check in enumerate(checks, start=1):
        check["check_id"] = "PD-%04d" % number
    return shared.StepResult({"package_doc_checks": checks}, {"checks": len(checks), "differ": sum(1 for c in checks if c["outcome"] == "differs")}, [])

# ---------------------------------------------------------------- step 15: account-coverage
NEXT_STEPS = {
    shared.CAT_CODE_DIFFERS: "Compare the code with the cited passage, starting from the inputs shown under What was observed.",
    shared.CAT_CODE_NOT_TRACED: "Decide whether this code implements a part of the methodology; if so, name the passage.",
    shared.CAT_MATH_UNDECIDED: "Compare the formula in the code with the cited passage by hand; AIVA could not decide it.",
    shared.CAT_VALUE_DIFFERS: "Compare the listed rows of the package table with the cited table of the methodology.",
    shared.CAT_NUMBER_NOT_TRACED: "Find where the methodology states this number, or confirm that it needs no statement.",
    shared.CAT_DATA_NOT_TRACED: "Decide which table of the methodology this stored object corresponds to, if any.",
    shared.CAT_DATA_NOT_DESCRIBED: "Check whether the stored object and each of its columns should be described in the package.",
    shared.CAT_PKGDOC_VS_CODE: "Compare the roxygen block or help page with the function it documents.",
    shared.CAT_PKGDOC_VS_CANON: "Compare the value stated in the package documentation with the cited passage.",
    shared.CAT_DOC_NOT_TRACED: "Decide which passage of the methodology this statement of the documentation rests on, if any.",
    shared.CAT_DOC_VS_CANON: "Compare the statement in the documentation with the cited passage of the methodology.",
    shared.CAT_DOC_VS_CODE: "Compare the statement in the documentation with the cited unit of the package.",
    shared.CAT_NOT_READ: "Review this item by hand; AIVA could not read or assess it.",
    shared.CAT_AI_UNUSABLE: "Review this unit by hand, or run AIVA again; the AI's answer could not be used.",
    shared.CAT_AI_DISAGREE: "Read both quotations and decide whether the unit and the passage state the same thing."}

def concerns_of(record):
    if record.get("heading_chain") is not None:
        return shared.CONCERNS[3] if record["corner"] == "doc" else shared.CONCERNS[0]
    if record.get("data") or record["kind"] in (shared.KIND_TABLE, shared.KIND_OBJECT):
        return shared.CONCERNS[1]
    return shared.CONCERNS[2] if record["kind"] in (shared.KIND_ROXYGEN, shared.KIND_HELP, shared.KIND_VIGNETTE) else shared.CONCERNS[0]

def citation(record):
    """How a unit or a passage is cited next to a quotation."""
    if record.get("heading_chain") is not None:
        place = " > ".join(record["heading_chain"][-2:]) or record["source_file"]
        return "%s, %s, %s%s" % (record["ref"], place, record["kind"].lower(), " %d" % record["para_no"] if record.get("para_no") else "")
    lines = " lines %d-%d" % tuple(record["lines"]) if record.get("lines") else ""
    return "%s, %s%s" % (record["ref"], record["file"], lines)

def render_path(record, world):
    """The supporting path of an item, hop by hop, each hop with its citation (plan 2.5)."""
    graph, by_ref = world["graph"], world["by_ref"]
    if record.get("heading_chain") is not None:
        hops = ["%s %s in %s" % (record["ref"], record["kind"].lower(), " > ".join(record["heading_chain"][-2:]) or record["source_file"])]
    else:
        hops = ["%s %s `%s` (%s)" % (record["ref"], record["kind"].lower(), record["name"], citation(record).split(", ", 1)[1])]
    parent = by_ref.get(record.get("parent_ref") or "")
    if parent:
        hops.append("inside %s %s %s" % (parent["kind"].lower(), parent["ref"], parent["name"]))
    for owner in [record] + ([parent] if parent else []):
        for edge in graph["out"].get(owner["ref"], []):
            if edge["kind"] == "reads_data":
                where = "; ".join("%s %s" % (k, edge["evidence"][k]) for k in ("row_key", "column") if edge["evidence"].get(k))
                hops.append("reads %s %s %s%s" % (by_ref[edge["target"]]["kind"].lower(), edge["target"], by_ref[edge["target"]]["name"], " [%s]" % where if where else ""))
    for prefix, verb in (("C-", "corresponds to"), ("M-", "corresponds to"), ("D-", "described by documentation")):
        for ref in linked(world, record["ref"], prefix)[:2]:
            edge = world["links"].get((record["ref"], ref)) or world["links"].get((ref, record["ref"]))
            hops.append("%s %s (%s): %s" % (verb, ref, edge["relation"], edge["how"]))
    for edge in graph["in"].get(record["ref"], []):
        if edge["kind"] == "documents":
            hops.append("documented by %s %s" % (by_ref[edge["source"]]["kind"].lower(), edge["source"]))
    return [hops[0]] + ["  > " + hop for hop in dict.fromkeys(hops[1:8])]

def gather(ctx, world):
    """All check records and AI notes, grouped by the unit they belong to."""
    facts = {}
    def at(ref):
        return facts.setdefault(ref, {"math": [], "values": [], "rules": [], "pkgdoc": [], "problems": [], "opinions": [], "unresolved": []})
    for record in ctx.read("math_checks"):
        at(record["target_ref"] if record["formula_source"] == "roxygen" else record["unit_ref"])["math"].append(record)
        if record["formula_source"] == "roxygen":
            at(record["unit_ref"])["math"].append(dict(record, shown_only=True))
    for kind, slot in (("value_checks", "values"), ("rule_checks", "rules"), ("package_doc_checks", "pkgdoc"),
                       ("second_opinions", "opinions"), ("unresolved_references", "unresolved")):
        for record in ctx.read(kind):
            at(record["unit_ref"])[slot].append(record)
    seen = set()
    for record in ctx.read("judgement_problems"):
        if (record["unit_ref"], record["target_corner"]) not in seen:
            seen.add((record["unit_ref"], record["target_corner"]))
            at(record["unit_ref"])["problems"].append(record)
    facts["states_nothing"] = {r["unit_ref"] for r in ctx.read("doc_judgements") if r.get("states_nothing_checkable")}
    return facts

def ai_judged_difference(world, ref, prefix):
    """Passages the AI judge itself called deviating or inconsistent (not a check's edge)."""
    return [t for (s, t), e in sorted(world["links"].items()) if s == ref and t.startswith(prefix) and e["relation"] == "Differs from"
            and not e["evidence"].get("check")]

def model_unit_outcome(unit, world, facts, raised):
    """The status rules for one model unit, top to bottom (plan 2.9). Returns (status, name of
    the deciding rule, reason shown). Differences and undecided checks are raised as it goes."""
    ref, kind, code, mine = unit["ref"], unit["kind"], unit.get("code") or {}, facts.get(unit["ref"], {})
    def note(category, line, check_id=""):
        entry = raised.setdefault((ref, category), {"lines": [], "checks": []})
        entry["lines"].append(line)
        entry["checks"].append(check_id)
    if kind in (shared.KIND_NOT_READ, shared.KIND_COMPILED) or (unit.get("data") and not unit["data"]["assessable"]):
        reason = unit.get("read_problem") or "This stored object was not compared: %s." % (unit.get("data") or {}).get("not_assessable_reason", "it could not be read")
        note(shared.CAT_NOT_READ, reason)
        return shared.ST_NOT_ASSESSED, "could not be read or assessed", reason
    if kind == shared.KIND_TEST:
        return shared.ST_UNIT_TEST, "test block", "a test block"
    if kind == shared.KIND_OTHER:
        return shared.ST_SUPPORTING, "package file without code", "a package file without code (%s)" % unit["name"]
    if unit["file"].startswith(("vignettes/", "inst/doc/")) and kind != shared.KIND_VIGNETTE:
        return shared.ST_SUPPORTING, "example code in a vignette", "example code in a vignette; it is not part of the model"
    differs, undecided = False, False
    for record in mine.get("math", []):
        if record.get("shown_only"):
            continue
        if record["outcome"] == "differs":
            differs = True
            note(shared.CAT_PKGDOC_VS_CODE if record["formula_source"] == "roxygen" else shared.CAT_CODE_DIFFERS, record["sentence"], record["check_id"])
        elif record["outcome"] == shared.CHECK_UNDECIDED:
            undecided = True
            note(shared.CAT_MATH_UNDECIDED, record["sentence"], record["check_id"])
    for target in ai_judged_difference(world, ref, "C-"):
        differs = True
        note(shared.CAT_CODE_DIFFERS, "The AI judged that this unit deviates from %s: %s" % (target, world["links"][(ref, target)]["evidence"]["how_text"].split("\n")[0]))
    for record in mine.get("values", []):
        category = {"parameter table": shared.CAT_VALUE_DIFFERS, "number in code": shared.CAT_NUMBER_NOT_TRACED,
                    "number in roxygen": shared.CAT_PKGDOC_VS_CANON}.get(record["what"], shared.CAT_VALUE_DIFFERS)
        if record["what"] == "parameter table" and record["target_ref"].startswith("D-"):
            category = shared.CAT_DOC_VS_CODE
        if record["outcome"] in ("differs", "not stated"):
            differs = True
            for line in [s for s in record["sentences"] if "differs" in s or "not stated" in s or "only" in s] or record["sentences"][:1]:
                note(category, line, record["check_id"])
        elif record["outcome"] == "could not be compared":
            undecided = True
            note(shared.CAT_NOT_READ, record["sentences"][0], record["check_id"])
    for record in mine.get("rules", []):
        if record["outcome"] in ("not applied", "applied differently"):
            differs = True
            note(shared.CAT_CODE_DIFFERS, record["sentence"] + ". The rule as stated: " + quote(record["rule_as_stated"], record["target_ref"]), record["check_id"])
        elif record["outcome"] == "could not be decided":
            undecided = True
            note(shared.CAT_AI_UNUSABLE, record["sentence"], record["check_id"])
    for record in mine.get("pkgdoc", []):
        if record["outcome"] == "differs":
            differs = True
            note(shared.CAT_DATA_NOT_DESCRIBED if unit.get("data") else shared.CAT_PKGDOC_VS_CODE, record["detail"], record["check_id"])
    for record in mine.get("opinions", []):
        differs = True
        note(shared.CAT_AI_DISAGREE, "A second, oppositely framed question named a difference from %s: %s against %s" % (
            record["target_ref"], quote(record["quote_from_unit"], ref), quote(record["quote_from_passage"], record["target_ref"])))
    if kind in (shared.KIND_ROXYGEN, shared.KIND_HELP):
        return ("own checks", differs, undecided)
    is_linked = bool(linked(world, ref, "C-"))
    if is_linked or (differs and not is_linked and (code.get("plumbing") or unit.get("data"))):
        if differs:
            return shared.ST_DIFFERS, "a check or the judge reports a difference", "see the flagged item(s)"
        if undecided:
            return shared.ST_UNDECIDED, "a required check is undecided", "see the flagged item(s)"
        return shared.ST_TRACED, "linked and all required checks agree", "linked to %s" % ", ".join(linked(world, ref, "C-"))
    parent = world["by_ref"].get(unit.get("parent_ref") or "")
    parent_math = [r for r in facts.get(parent["ref"], {}).get("math", []) if r["outcome"] == "agrees"] if parent else []
    if kind == shared.KIND_FORMULA and parent and not differs and not undecided and any(
            r["through"] == ref or (r["through"] == parent["ref"] and not unit["inside"] == "") for r in parent_math):
        return shared.ST_TRACED, "covered by the check of the whole function", "covered by the check of function %s, which agrees" % parent["ref"]
    parent_plumbing = bool(parent and (parent.get("code") or {}).get("plumbing"))
    if (code.get("plumbing") or parent_plumbing) and not differs and not undecided:
        return shared.ST_SUPPORTING, "supporting code by syntax", code.get("plumbing_reason") or "a statement inside supporting code"
    if kind == shared.KIND_VIGNETTE and not shared.find_numbers(unit["text"]) and "=" not in unit["text"]:
        return shared.ST_SUPPORTING, "vignette prose without checkable statements", "vignette prose that states no number and no formula"
    problem = next((p for p in mine.get("problems", []) if p["target_corner"] == "canon"), None)
    if problem:
        note(shared.CAT_AI_UNUSABLE, "The AI's answer about the methodology could not be used: %s." % problem["reason"])
    else:
        category = shared.CAT_DATA_NOT_TRACED if unit.get("data") else shared.CAT_DOC_NOT_TRACED if kind == shared.KIND_VIGNETTE else shared.CAT_CODE_NOT_TRACED
        note(category, "No passage of the methodology was linked to this unit.")
    return shared.ST_NOT_TRACED, "not linked", "no link to the methodology"

def doc_unit_outcome(chunk, world, facts, raised):
    """The status rules for one documentation unit, top to bottom (plan 2.9)."""
    ref, mine = chunk["ref"], facts.get(chunk["ref"], {})
    def note(category, line, check_id=""):
        entry = raised.setdefault((ref, category), {"lines": [], "checks": []})
        entry["lines"].append(line)
        entry["checks"].append(check_id)
    unreadable = chunk["kind"] == "Figure" or chunk.get("not_read_reason") or (chunk["kind"] == "Equation" and not chunk["equation"]["readable"])
    if unreadable:
        reason = chunk.get("not_read_reason") or ("the content of a figure cannot be read" if chunk["kind"] == "Figure" else chunk["equation"]["not_readable_reason"])
        note(shared.CAT_NOT_READ, "This %s was not assessed: %s." % (chunk["kind"].lower(), reason))
        return shared.ST_NOT_ASSESSED, "content cannot be read", reason
    to_canon, to_model = linked(world, ref, "C-"), linked(world, ref, "M-")
    if not to_canon and (not chunk.get("checkable") or (ref in facts["states_nothing"] and not to_model)):
        return shared.ST_NARRATIVE, "states nothing checkable", "no formula, number, rule or definition"
    differs, undecided = False, False
    for target in ai_judged_difference(world, ref, "C-"):
        differs = True
        note(shared.CAT_DOC_VS_CANON, "The AI judged this passage inconsistent with %s." % target)
    for target in ai_judged_difference(world, ref, "M-"):
        differs = True
        note(shared.CAT_DOC_VS_CODE, "The AI judged this passage inconsistent with %s." % target)
    for record in mine.get("values", []):
        if record["outcome"] == "differs":
            differs = True
            for line in [s for s in record["sentences"] if "differs" in s or "only" in s]:
                note(shared.CAT_DOC_VS_CANON, line, record["check_id"])
    for unit_ref in to_model:                            # a package table that differs from this documentation table
        for record in facts.get(unit_ref, {}).get("values", []):
            if record["target_ref"] == ref and record["outcome"] == "differs":
                differs = True
                note(shared.CAT_DOC_VS_CODE, record["sentences"][0], record["check_id"])
    for record in mine.get("math", []):
        if record["outcome"] == "differs":
            differs = True
            note(shared.CAT_DOC_VS_CANON, record["sentence"], record["check_id"])
        elif record["outcome"] == shared.CHECK_UNDECIDED:
            undecided = True
            note(shared.CAT_MATH_UNDECIDED, record["sentence"], record["check_id"])
    for record in mine.get("opinions", []):
        differs = True
        note(shared.CAT_AI_DISAGREE, "A second, oppositely framed question named a difference from %s: %s against %s" % (
            record["target_ref"], quote(record["quote_from_unit"], ref), quote(record["quote_from_passage"], record["target_ref"])))
    through = [u for u in to_model if linked(world, u, "C-")]
    if to_canon or through:
        if differs:
            return shared.ST_DIFFERS, "a check or the judge reports a difference", "see the flagged item(s)"
        if undecided:
            return shared.ST_UNDECIDED, "a required check is undecided", "see the flagged item(s)"
        return shared.ST_TRACED, "linked and consistent", "linked to %s" % ", ".join(to_canon or ["the methodology through " + through[0]])
    problem = next((p for p in mine.get("problems", [])), None)
    note(shared.CAT_AI_UNUSABLE if problem else shared.CAT_DOC_NOT_TRACED, "The AI's answer could not be used: %s." % problem["reason"] if problem
         else "This passage states something checkable, and no passage of the methodology was linked to it.")
    return shared.ST_NOT_TRACED, "checkable and not linked", "no link to the methodology"

def lines_or(lines, fallback):
    return "\n".join(dict.fromkeys(lines)) if lines else fallback

def model_cells(unit, world, facts):
    """The assessment cells of one row of Mapping_Model_to_Canon_and_Doc. Every cell shows real
    content or "Not applicable" for this kind of unit."""
    mine, code, na = facts.get(unit["ref"], {}), unit.get("code"), shared.NOT_APPLICABLE
    is_code = unit["kind"] in (shared.KIND_FUNCTION, shared.KIND_FORMULA)
    math = [r for r in mine.get("math", [])]
    pairs = ["%s: `%s` (%s)" % (stated, c, how) for r in math for c, stated, how in r["alignment"]]
    tables = [s for r in mine.get("values", []) if r["what"] == "parameter table" for s in r["sentences"]]
    tests = ["Tested by %s (%s)" % (e["target"], citation(world["by_ref"][e["target"]]).split(", ", 1)[1])
             for e in world["graph"]["out"].get(unit["ref"], []) if e["kind"] == "tested_by"]
    documented = [r["detail"] for r in mine.get("pkgdoc", [])]
    block = next((e["source"] for e in world["graph"]["in"].get(unit["ref"], []) if e["kind"] == "documents"), None)
    if block:
        documented += [r["detail"] for r in facts.get(block, {}).get("pkgdoc", [])]
    documented += ["Described in %s" % ref for ref in linked(world, unit["ref"], "D-")]
    ai_notes = ["AI (second question), about %s: %s" % (r["target_ref"], quote(r["what_differs"])) for r in mine.get("opinions", [])]
    return {"math_check": lines_or([r["sentence"] for r in math], "No linked passage states a formula" if is_code else na),
            "parameter_completeness": lines_or(tables or pairs, na if not unit.get("data") else "No table was linked or matched"),
            "logic_consistency": lines_or([r["sentence"] for r in mine.get("rules", [])], "No linked passage states a floor or a cap" if is_code else na),
            "documentation_consistency": lines_or(documented, na),
            "hard_coded_numbers": lines_or([s for r in mine.get("values", []) if r["what"] == "number in code" for s in r["sentences"]],
                                           "No number other than the trivial ones" if is_code else na),
            "unit_test": lines_or(tests, "No test block calls this function") if unit["kind"] == shared.KIND_FUNCTION else na,
            "quality_notes_ai": lines_or(ai_notes, "No note")}

def doc_cells(chunk, world, facts, duplicates):
    """The assessment cells of one row of Mapping_Doc_to_Canon_and_Model."""
    mine, na = facts.get(chunk["ref"], {}), shared.NOT_APPLICABLE
    relations = ["%s %s" % (world["links"][(chunk["ref"], ref)]["relation"], ref) for ref in linked(world, chunk["ref"], "C-") if (chunk["ref"], ref) in world["links"]]
    relations += ["%s: %s" % (ref, (world["links"].get((ref, chunk["ref"])) or world["links"].get((chunk["ref"], ref)))["relation"]) for ref in linked(world, chunk["ref"], "M-")]
    relations += ["A second, oppositely framed question named a difference from %s" % r["target_ref"] for r in mine.get("opinions", [])]
    quality = [r["note"] for r in mine.get("unresolved", [])]
    if chunk.get("numbering_reconstructed"):
        quality.append("Section numbering was reconstructed by counting; Word does not store it")
    if chunk["ref"] in duplicates:
        quality.append("The same text also occurs as %s" % duplicates[chunk["ref"]])
    if chunk["kind"] == "Equation" and not chunk["equation"]["readable"]:
        quality.append("The equation could not be read: %s" % chunk["equation"]["not_readable_reason"])
    return {"value_check": lines_or([s for r in mine.get("values", []) for s in r["sentences"]], "No number to compare" if chunk.get("checkable") else na),
            "math_check": lines_or([r["sentence"] for r in mine.get("math", [])], na),
            "logic_consistency": lines_or(relations, na), "parameter_note_ai": na, "quality_notes": lines_or(quality, "No note")}

def build_items(raised, world, run_label):
    """One flagged item per unit and category; several observations of one category are listed
    inside one item. Item ids are given once, in a fixed order: concerns, unit, category."""
    order = sorted(raised, key=lambda key: (shared.CONCERNS.index(concerns_of(world["by_ref"][key[0]])), key[0], shared.CATEGORIES.index(key[1])))
    items = []
    for number, (ref, category) in enumerate(order, start=1):
        record, entry = world["by_ref"][ref], raised[(ref, category)]
        canon = [world["by_ref"][r] for r in linked(world, ref, "C-")[:2]]
        if record.get("heading_chain") is not None:
            doc_side, code_side = [record], [world["by_ref"][r] for r in linked(world, ref, "M-")[:1]]
        else:
            code_side, doc_side = [record], [world["by_ref"][r] for r in linked(world, ref, "D-")[:1]]
        name = "`%s`" % record["name"] if record.get("name") else " > ".join(record.get("heading_chain", [])[-1:]) or ref
        path = render_path(record, world)
        items.append(shared.FlaggedItem(
            item_id="RI-%s-%05d" % (run_label, number), category=category, concerns=concerns_of(record), unit_refs=tuple([ref] + entry.get("also", [])),
            item="%s: %s %s" % (category, record["kind"].lower(), name),
            observed="\n".join(dict.fromkeys(entry["lines"])) + "\n\nSupporting path:\n" + "\n".join(path),
            methodology_says="\n".join(quote(c["text"][:500], citation(c)) for c in canon),
            code_does="\n".join(quote(c["text"][:700], citation(c)) for c in code_side),
            documentation_says="\n".join(quote(c["text"][:500], citation(c)) for c in doc_side),
            suggested_next_step=NEXT_STEPS[category], evidence_path=tuple(path), from_checks=tuple(c for c in dict.fromkeys(entry["checks"]) if c)))
    return items

def check_identity(units, doc, statuses, items, world, package_info):
    """The four-part identity of plan 2.9 (part 4 is completed by the workbook builder). Any
    violation stops the run and says that this is a defect in AIVA. Enforces: R2"""
    defect = "%s This is a defect in AIVA, not in the model under review."
    expected = [u["ref"] for u in units] + [c["ref"] for c in doc]
    if sorted(s["unit_ref"] for s in statuses) != sorted(expected):
        raise AivaDefect(defect % "Part 1 of the coverage identity does not hold: not every unit has exactly one status record.")
    named = {ref for item in items for ref in item.unit_refs}
    not_clean = {s["unit_ref"] for s in statuses if not s["clean"]}
    if not_clean != (named & set(expected)) or any(not set(item.unit_refs) & set(world["by_ref"]) for item in items):
        raise AivaDefect(defect % "Part 2 of the coverage identity does not hold: units that are not clean and flagged items do not match (%s)."
                         % ", ".join(sorted(not_clean ^ (named & set(expected)))[:5]))
    for entry in (package_info[0]["files"] if package_info else []):
        members = [u for u in units if u["file"] == entry["file"]]
        covered = {n for u in members if u.get("lines") for n in range(u["lines"][0], u["lines"][1] + 1)}
        if not members or set(entry.get("nonblank_lines", [])) - covered:
            raise AivaDefect(defect % ("Part 3 of the coverage identity does not hold: %s is not fully covered by units." % entry["file"]))

def account_coverage(ctx):
    """Step 15, skill account-coverage: one status per unit by the ordered rules, the cells of
    the assessment columns, one flagged item per unit and category, the identity, and the
    totals that the workbook builder must reproduce by counting its rows. Enforces: R2, R10"""
    world = load_world(ctx)
    facts, raised, statuses = gather(ctx, world), {}, []
    outcomes = {u["ref"]: model_unit_outcome(u, world, facts, raised) for u in world["units"]}
    for unit in world["units"]:                          # roxygen blocks and help pages take the tracing of what they document
        if outcomes[unit["ref"]][0] != "own checks":
            continue
        _, differs, undecided = outcomes[unit["ref"]]
        target_ref = (unit.get("roxygen") or {}).get("documents_ref") or next(
            (e["target"] for e in world["graph"]["out"].get(unit["ref"], []) if e["kind"] == "documents"), None)
        target = outcomes.get(target_ref)
        if differs or undecided:
            outcomes[unit["ref"]] = (shared.ST_DIFFERS if differs else shared.ST_UNDECIDED, "its own checks", "see the flagged item(s)")
        elif target is None or target[0] == "own checks":
            outcomes[unit["ref"]] = (shared.ST_SUPPORTING, "documents no single object", "documents no single object of the package")
        else:
            outcomes[unit["ref"]] = (target[0], "takes the tracing of what it documents", "as %s, which it documents" % target_ref)
            for (ref, category), entry in raised.items():
                if ref == target_ref and target[0] in shared.NOT_CLEAN_STATUSES:
                    entry.setdefault("also", []).append(unit["ref"])
    by_hash, duplicates = {}, {}
    for chunk in world["doc"]:
        if chunk["kind"] == "Paragraph" and chunk["content_hash"] in by_hash:
            duplicates[chunk["ref"]] = by_hash[chunk["content_hash"]]
        by_hash.setdefault(chunk["content_hash"], chunk["ref"])
    doc_outcomes = {c["ref"]: doc_unit_outcome(c, world, facts, raised) for c in world["doc"]}
    for chunk in world["canon"]:                         # what the methodology shows only as a picture is never skipped
        unread = chunk["kind"] == "Equation" and not chunk["equation"]["readable"]
        if unread or chunk["kind"] == "Figure" or chunk.get("not_read_reason"):
            reason = chunk["equation"]["not_readable_reason"] if unread else chunk.get("not_read_reason") or "the content of a figure cannot be read"
            raised[(chunk["ref"], shared.CAT_NOT_READ)] = {"checks": [], "lines": [
                "This %s of the methodology could not be read (%s), so nothing can be checked against it by AIVA." % (chunk["kind"].lower(), reason)]}
    items = build_items(raised, world, ctx.options["run"]["run_id"].replace("Run_", ""))
    ids_by_unit = {}
    for item in items:
        for ref in item.unit_refs:
            ids_by_unit.setdefault(ref, []).append(item.item_id)
    for record, outcome, corner in [(u, outcomes[u["ref"]], "model") for u in world["units"]] + [(c, doc_outcomes[c["ref"]], "doc") for c in world["doc"]]:
        cells = model_cells(record, world, facts) if corner == "model" else doc_cells(record, world, facts, duplicates)
        statuses.append({"unit_ref": record["ref"], "corner": corner, "status": outcome[0], "clean": outcome[0] in shared.CLEAN_STATUSES,
                         "decided_by_rule": outcome[1], "reason_shown": outcome[2], "item_ids": ids_by_unit.get(record["ref"], []), "cells": cells})
    check_identity(world["units"], world["doc"], statuses, items, world, ctx.read("package_info"))
    coverage = {}
    for corner in ("model", "doc"):
        mine = [s for s in statuses if s["corner"] == corner]
        by_status = {status: sum(1 for s in mine if s["status"] == status) for status in shared.CLEAN_STATUSES + shared.NOT_CLEAN_STATUSES}
        coverage[corner] = {"total": len(mine), "by_status": by_status, "needs_attention": sum(1 for s in mine if not s["clean"])}
    pointed = {t for (s, t), e in world["links"].items() if t.startswith("C-") and e["relation"] in shared.LINKING_RELATIONS}
    coverage["canon"] = {"total": len(world["canon"]), "pointed_to": len(pointed)}
    return shared.StepResult({"unit_status": statuses, "flagged_items": items, "coverage": [coverage]},
                             {"units": len(statuses), "units needing attention": sum(1 for s in statuses if not s["clean"]), "flagged items": len(items)}, [])
