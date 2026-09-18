"""
AIVA 0.0.1 - aiva0_shared.py - the shared file. Every reviewer reads this one first.

WHAT THIS FILE DOES
  It holds what all five bundles have in common: the fixed wording AIVA may use
  (Appendix B of the build plan), the shape of every record written to _audit,
  the way content is hashed so a citation can be re-checked, the way numbers and
  symbols are brought to one form, AIVA's small neutral expression tree, and the
  two objects every pipeline step receives and returns.

WHAT IT TAKES IN AND PRODUCES
  Nothing is read from or written to disk here. Functions take text or records
  and return text, records or hashes.

WHICH SHEETS SHOW ITS RESULTS
  All of them, indirectly: every status, category, relation and kind shown in
  Output.xlsx is one of the constants below.

DESIGN RULES ENFORCED HERE
  R1  wording: the fixed vocabulary, and has_banned_wording() used by the lint.
  R4  provenance and re-verifiable citations: Provenance, content_hash().
  R5  determinism: canonical_json() sorts keys; chain_records() leaves out
      time stamps so the same content always gives the same fingerprint.
  R9  no domain concept: nothing below names a field of business.
  R10 plain language: plain_number() shows whole numbers as whole numbers.

HOW TO SANITY-CHECK IT
  Run `python -m unittest engine/tests/test_aiva0_shared.py`. Then, in a notebook
  cell: content_hash("a  b") == content_hash("a b") must be True, and
  parse_number("10 basis points")["value"] must be "0.001".
"""
import dataclasses
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional

ENGINE_VERSION = "0.0.1"
GENESIS_HASH = "0" * 64

# ---------------------------------------------------------------- vocabulary (Appendix B)
RELATION_WORDING = {  # the word allowed in a prompt -> the wording shown in the workbook
    "implements": "Implements", "partly implements": "Partly implements",
    "deviates from": "Differs from", "merely related": "Same topic (not implemented here)",
    "describes": "Describes", "consistent with": "Consistent with",
    "inconsistent with": "Differs from"}
LINKING_RELATIONS = ("Implements", "Partly implements", "Differs from", "Describes", "Consistent with")
HOW_PARSED = "Parsed from the files"
HOW_AI = "AI judgement ({confidence}%)"
HOW_SYMBOLIC = "Symbolic check: agrees"
HOW_NUMERIC_AGREES = "Numerical check: agrees ({n} points)"
HOW_NUMERIC_DIFFERS = "Numerical check: differs"
HOW_VALUE_AGREES, HOW_VALUE_DIFFERS = "Value check: agrees at stated precision", "Value check: differs"
HOW_TABLE, HOW_PERSON = "Table matched by headers and row keys", "Recorded by a person"
CHECK_UNDECIDED, NOT_APPLICABLE, NOT_RUN_YET = "Could not be decided", "Not applicable", "Not run yet"

ST_TRACED, ST_SUPPORTING = "Traced to methodology", "Supporting code (justified)"
ST_UNIT_TEST, ST_NARRATIVE = "Unit test", "Narrative - nothing to check"
ST_DIFFERS, ST_UNDECIDED = "Traced - differences flagged", "Traced - check undecided"
ST_NOT_TRACED, ST_NOT_ASSESSED = "Not traced - for review", "Not assessed - for manual review"
CLEAN_STATUSES = (ST_TRACED, ST_SUPPORTING, ST_UNIT_TEST, ST_NARRATIVE)
NOT_CLEAN_STATUSES = (ST_DIFFERS, ST_UNDECIDED, ST_NOT_TRACED, ST_NOT_ASSESSED)

ITEM_OPEN = "Open"
DECISION_WORDS = ("Requires action", "No action needed")
DECISION_WITHDRAWN = "Withdrawn"

CONCERNS = ("Model code", "Parameter data", "Package documentation", "Model documentation")
CAT_CODE_DIFFERS, CAT_CODE_NOT_TRACED = "Code differs from methodology", "Code not traced to methodology"
CAT_MATH_UNDECIDED, CAT_VALUE_DIFFERS = "Mathematical check undecided", "Value differs from methodology"
CAT_NUMBER_NOT_TRACED, CAT_DATA_NOT_TRACED = "Hard-coded number not traced", "Parameter data not traced"
CAT_DATA_NOT_DESCRIBED = "Parameter data not described"
CAT_PKGDOC_VS_CODE = "Package documentation differs from code"
CAT_PKGDOC_VS_CANON = "Package documentation differs from methodology"
CAT_DOC_NOT_TRACED, CAT_DOC_VS_CODE = "Documentation statement not traced", "Documentation differs from code"
CAT_DOC_VS_CANON = "Documentation differs from methodology"
CAT_NOT_READ, CAT_AI_UNUSABLE = "Item could not be read or assessed", "AI answer could not be used"
CAT_AI_DISAGREE = "AI answers disagree"
CATEGORIES = (CAT_CODE_DIFFERS, CAT_CODE_NOT_TRACED, CAT_MATH_UNDECIDED, CAT_VALUE_DIFFERS,
              CAT_NUMBER_NOT_TRACED, CAT_DATA_NOT_TRACED, CAT_DATA_NOT_DESCRIBED,
              CAT_PKGDOC_VS_CODE, CAT_PKGDOC_VS_CANON, CAT_DOC_NOT_TRACED, CAT_DOC_VS_CANON,
              CAT_DOC_VS_CODE, CAT_NOT_READ, CAT_AI_UNUSABLE, CAT_AI_DISAGREE)

UNDECIDED_REASONS = (
    "the equation is an image", "the equation could not be read",
    "symbols could not be aligned", "the function could not be composed",
    "it uses operations AIVA cannot evaluate", "too few valid sample points")
REJECTION_REASONS = (
    "it could not be read", "it named a passage that was not shown",
    "it quoted words that are not in the text", "it accepted a planted control passage",
    "it contradicted itself")

KIND_FUNCTION, KIND_FORMULA, KIND_TOPLEVEL = "Function", "Formula statement", "Top-level statement"
KIND_TEST, KIND_TABLE, KIND_OBJECT = "Test block", "Parameter table", "Parameter object"
KIND_ROXYGEN, KIND_HELP, KIND_VIGNETTE = "Roxygen block", "Help page", "Vignette text"
KIND_COMPILED, KIND_NOT_READ, KIND_OTHER = "Compiled code", "File not read", "Other file"
UNIT_KINDS = (KIND_FUNCTION, KIND_FORMULA, KIND_TOPLEVEL, KIND_TEST, KIND_TABLE, KIND_OBJECT,
              KIND_ROXYGEN, KIND_HELP, KIND_VIGNETTE, KIND_COMPILED, KIND_NOT_READ, KIND_OTHER)
CHUNK_KINDS = ("Paragraph", "Table", "Figure", "Equation")
AI_WORDING_NOT_SHOWN = ("The AI's wording is not displayed here; the full text is in the audit records.")

# The lint (tests/test_layout_rules.py) skips this one assignment, which has to name the words.
# These terminologies CAN BE USED ONLY by HUMAN reviewers/validators. Machines cannot make these determinations.
BANNED_WORDING_PATTERNS = (
    r"\bfindings?\b", r"\berrors?\b", r"\bseverity\b", r"\bsevere\b", r"\bcritical\b",
    r"\bmajor\b", r"\bminor\b",
    r"\b(high|medium|low)[\s-]+(risk|priority|rating|impact)\b",
    r"\b(risk|priority|rating|impact)\s*[:=]?\s*(high|medium|low)\b")
_BANNED_RE = re.compile("|".join(BANNED_WORDING_PATTERNS), re.IGNORECASE)

def has_banned_wording(text):
    """Return the first word in `text` that AIVA's own wording may not use, or "". Enforces: R1"""
    found = _BANNED_RE.search(text or "")
    return found.group(0) if found else ""

# ---------------------------------------------------------------- data contracts (plan 2.3)
@dataclass(frozen=True)
class TableData:
    """A table kept whole: header cells, body rows, and which column identifies a row."""
    header: tuple = (); rows: tuple = (); row_key: str = ""; column_types: tuple = ()

@dataclass(frozen=True)
class EquationData:
    """An equation as found: its source form, whether AIVA could read it, and its tree."""
    source_form: str = ""; linear: str = ""; readable: bool = False
    not_readable_reason: str = ""; expression: Optional[dict] = None; image_sha256: str = ""

@dataclass(frozen=True)
class Chunk:
    """One citable unit of a document: a paragraph, a table, a figure or an equation."""
    ref: str; corner: str; source_file: str; kind: str; level: int; heading_chain: tuple
    numbering: str; para_no: Optional[int]; text: str; locator: str; content_hash: str
    table: Optional[TableData] = None; equation: Optional[EquationData] = None
    refs_out: tuple = (); checkable: Optional[bool] = None; numbering_reconstructed: bool = False
    caption: str = ""; not_read_reason: str = ""

@dataclass(frozen=True)
class CodeDetail:
    """What the R reader learned about a function or a statement, without running it."""
    formals: tuple = (); calls: tuple = (); symbols_read: tuple = (); symbols_written: tuple = ()
    numbers: tuple = (); strings: tuple = (); exported: Optional[bool] = None
    expression: Optional[dict] = None; reads_data: tuple = (); plumbing: bool = False
    plumbing_reason: str = ""; composed: Optional[dict] = None; not_composed_reason: str = ""

@dataclass(frozen=True)
class ParameterDataDetail:
    """The profile of one stored data object. The cell values live in parameter_tables."""
    object_name: str; container_file: str; r_class: tuple = (); r_type: str = ""
    dims: tuple = (); attributes: dict = field(default_factory=dict); columns: tuple = ()
    row_keys: tuple = (); n_cells: int = 0; canonical_value_hash: str = ""
    decoded_by: str = ""; assessable: bool = True; not_assessable_reason: Optional[str] = None

@dataclass(frozen=True)
class RoxygenDetail:
    """A roxygen block: what it documents, its tags with their lines, and its formulas."""
    documents_ref: Optional[str] = None; documents_name: str = ""; tags: tuple = ()
    formulas: tuple = ()

@dataclass(frozen=True)
class HelpPageDetail:
    """A help page as read from its macro format."""
    rd_name: str = ""; aliases: tuple = (); title: str = ""; usage: str = ""; arguments: tuple = ()
    generated_from_ref: Optional[str] = None; in_step_with_source: Optional[bool] = None

@dataclass(frozen=True)
class ModelUnit:
    """One citable unit of the package (see UNIT_KINDS)."""
    ref: str; kind: str; file: str; lines: Optional[tuple]; name: str; inside: str; text: str
    parent_ref: Optional[str]; file_sha256: str; content_hash: str
    code: Optional[CodeDetail] = None; data: Optional[ParameterDataDetail] = None
    roxygen: Optional[RoxygenDetail] = None; helppage: Optional[HelpPageDetail] = None
    read_problem: Optional[str] = None

@dataclass(frozen=True)
class Provenance:
    """Which run, step and skill produced a record, and from which AI exchange if any."""
    run_id: str; step_id: str; skill: str; skill_version: str; engine_version: str = ENGINE_VERSION
    prompt_hash: Optional[str] = None; response_hash: Optional[str] = None; created_at: str = ""

@dataclass(frozen=True)
class Edge:
    """A recorded connection between two nodes of the graph. Never changed once written."""
    source: str; target: str; kind: str; how: str; provenance: Provenance
    relation: str = ""; confidence: Optional[int] = None
    evidence: dict = field(default_factory=dict); record_type: str = "edge"

@dataclass(frozen=True)
class Candidate:
    """A passage the search stage proposes for a unit, with the reason in plain words."""
    unit_ref: str; target_ref: str; target_corner: str; rank: int; fused_score: float
    signals: dict; reason: str; path: tuple = (); suggestion_only: bool = False
    search_pass: int = 1

@dataclass(frozen=True)
class FlaggedItem:
    """Something AIVA could not line up, raised for a person. It carries no rating."""
    item_id: str; category: str; concerns: str; unit_refs: tuple; item: str; observed: str
    methodology_says: str = ""; code_does: str = ""; documentation_says: str = ""
    suggested_next_step: str = ""; evidence_path: tuple = (); from_checks: tuple = ()

@dataclass(frozen=True)
class Determination:
    """A named person's recorded decision on one flagged item."""
    item_id: str; decision: str; reviewer: str; role: str; rationale: str
    recorded_at: str; recorded_by: str; workbook_sha256: str

@dataclass
class StepContext:
    """What every step function receives. It never contains the access token."""
    settings: dict; options: dict; read: Callable; ask: Optional[Callable]
    work_dir: str; note: Callable; provenance: Optional[Provenance] = None

@dataclass
class StepResult:
    """What every step function returns: records by kind, counts, and plain notes."""
    records: dict = field(default_factory=dict); counts: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)

# ---------------------------------------------------------------- canonical JSON and hashes
def to_plain(value):
    """Turn dataclasses, tuples and Decimals into plain JSON-ready values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    return value

def canonical_json(value):
    """One JSON text per content: sorted keys, no spare white space. Enforces: R5"""
    return json.dumps(to_plain(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
def sha256_bytes(data):
    """SHA-256 of bytes, in hexadecimal."""
    return hashlib.sha256(data).hexdigest()
def sha256_text(text):
    """SHA-256 of a text in UTF-8, in hexadecimal."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
def swhid_content(data):
    """The ISO/IEC 18670 content identifier of a file; the same value Git computes."""
    return "swh:1:cnt:" + hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

def normalise_text(text):
    """Unicode NFC, one kind of line ending, runs of white space collapsed to one space."""
    text = unicodedata.normalize("NFC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", text).strip()

def content_hash(text):
    """The hash that makes a citation re-verifiable. It ignores white-space and
    line-ending differences and nothing else. Enforces: R4"""
    return sha256_text(normalise_text(text))

def make_ref(prefix, number):
    """make_ref("C", 9) gives "C-0009". Numbers follow reading order."""
    return "%s-%04d" % (prefix, number)

def strip_volatile(value, volatile):
    """A copy of a record without the named keys, at any depth (time stamps, run id)."""
    if isinstance(value, dict):
        return {k: strip_volatile(v, volatile) for k, v in value.items() if k not in volatile}
    if isinstance(value, list):
        return [strip_volatile(v, volatile) for v in value]
    return value

def chain_records(prev_hash, records, volatile=()):
    """Give each record the hash of the one before it and its own hash. The last hash
    then identifies the whole list: changing, removing or re-ordering any record
    changes it. Keys named in `volatile` are left out of the hash. Enforces: R4, R5"""
    chained = []
    for record in records:
        body = {k: v for k, v in to_plain(record).items() if k not in ("prev_hash", "record_hash")}
        body["prev_hash"] = prev_hash
        body["record_hash"] = sha256_text(canonical_json(strip_volatile(body, volatile)))
        prev_hash = body["record_hash"]
        chained.append(body)
    return chained
def verify_chain(records, volatile=()):
    """Re-compute a chain. Returns (True, -1, "") or (False, position, plain reason)."""
    prev_hash = GENESIS_HASH
    for position, record in enumerate(records):
        if record.get("prev_hash") != prev_hash:
            return False, position, "record %d does not follow the record before it" % (position + 1)
        body = {k: v for k, v in record.items() if k != "record_hash"}
        if sha256_text(canonical_json(strip_volatile(body, volatile))) != record.get("record_hash"):
            return False, position, "record %d has been changed" % (position + 1)
        prev_hash = record["record_hash"]
    return True, -1, ""
def chain_head(records):
    """The hash of the last record of a chain, or the fixed starting value for an empty one."""
    return records[-1]["record_hash"] if records else GENESIS_HASH

# ---------------------------------------------------------------- numbers
_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<num>[-\u2212]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    r"(?P<unit>\s?%|\s?(?:basis points?|bps?)\b|(?:st|nd|rd|th)\s+percentile\b)?")
_LABEL_BEFORE_RE = re.compile(
    r"(?:table|section|sections|equation|eq\.|figure|fig\.|annex|appendix|chapter|paragraph|"
    r"page|step|version|level)\s*\(?$", re.IGNORECASE)

def parse_number(as_written, unit=""):
    """Bring one written number to a decimal value and keep how it was written.
    Percent, basis points, scientific notation and "99.9th percentile" are converted
    first; `decimals` counts decimals after that conversion, because the value rule
    (plan 2.8) compares at the precision the methodology states."""
    text = as_written.replace("\u2212", "-").strip()
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    mantissa = re.split(r"[eE]", text)[0]
    decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
    exponent = int(re.split(r"[eE]", text)[1]) if re.search(r"[eE]", text) else 0
    kind = unit.strip().lower()
    shift = 2 if (kind == "%" or kind.endswith("percentile")) else 0
    if kind.startswith("basis") or kind.startswith("bp"):
        shift, kind = 4, "bp"
    if kind.endswith("percentile"):
        kind = "percentile"
    return {"value": plain_decimal(value.scaleb(-shift)), "as_written": as_written.strip() + unit.rstrip(),
            "decimals": max(0, decimals - exponent + shift), "unit": kind}

def plain_decimal(value):
    """A Decimal as the shortest plain decimal text: no exponent, no trailing zeros."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text

def find_numbers(text):
    """All numbers written in a piece of prose, with their position. Numbers that only
    label something ("Table 3", "section 4.2"), years and list numbering are left out."""
    found = []
    for match in _NUMBER_RE.finditer(text or ""):
        before = text[:match.start()]
        number = match.group("num")
        if _LABEL_BEFORE_RE.search(before[-24:]):
            continue
        if re.fullmatch(r"(19|20)\d\d", number) and not match.group("unit"):
            continue
        if not before.strip() and re.match(r"\)|\.?\s+[A-Z]", text[match.end():match.end() + 4]):
            continue                      # "3.1 Floors" or "2) ..." at the start: numbering
        parsed = parse_number(number, match.group("unit") or "")
        if parsed is not None:
            parsed["position"] = match.start()
            found.append(parsed)
    return found

def plain_number(value, digits=6):
    """How a computed value is shown to an analyst: whole numbers stay whole, other
    values show at most six significant digits, never an exponent. Enforces: R10"""
    if isinstance(value, str):
        return value
    if value != value or value in (float("inf"), float("-inf")):
        return "not a number" if value != value else ("infinity" if value > 0 else "minus infinity")
    if float(value) == int(value) and abs(value) < 1e15:
        return str(int(value))
    text = "%.*g" % (digits, float(value))
    return plain_decimal(Decimal(text)) if "e" in text else text

# ---------------------------------------------------------------- symbols
GREEK = {"alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
         "epsilon": "\u03b5", "theta": "\u03b8", "kappa": "\u03ba", "lambda": "\u03bb",
         "mu": "\u03bc", "nu": "\u03bd", "pi": "\u03c0", "rho": "\u03c1", "sigma": "\u03c3",
         "tau": "\u03c4", "phi": "\u03c6", "omega": "\u03c9", "Phi": "\u03a6", "Sigma": "\u03a3",
         "Delta": "\u0394", "Omega": "\u03a9"}
_GREEK_BY_CHAR = {char: name for name, char in GREEK.items()}
_SUBSCRIPT_CHARS = str.maketrans("\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089"
                                 "\u1d62\u2c7c\u2096\u2099\u209c", "0123456789ijknt")

def normalise_symbol(symbol):
    """One form for a symbol however it was written: the Greek letter by name, by
    character or in LaTeX form; a subscript written PD_i, PD[i], PD_{i} or with a
    subscript character. Case is kept for single letters and folded for words."""
    text = unicodedata.normalize("NFC", symbol or "").strip().strip("$`")
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)
    subscript = ""
    match = re.fullmatch(r"(.+?)(?:_\{?([^{}]+)\}?|\[([^\]]+)\])", text)
    if match:
        text, subscript = match.group(1), match.group(2) or match.group(3)
    else:
        tail = re.search(r"[\u2080-\u2089\u1d62\u2c7c\u2096\u2099\u209c]+$", text)
        if tail and tail.start() > 0:
            text, subscript = text[:tail.start()], tail.group(0).translate(_SUBSCRIPT_CHARS)
    parts = []
    for part in (text, subscript):
        part = "".join(_GREEK_BY_CHAR.get(char, char) for char in part)
        if len(part) > 1 and part not in GREEK:
            part = part.lower()
        parts.append(part)
    return parts[0] + ("_" + parts[1] if parts[1] else "")

# ---------------------------------------------------------------- the expression tree
@dataclass(frozen=True)
class Expr:
    """AIVA's neutral tree for a formula. op is one of: num, sym, add, sub, mul, div,
    pow, neg, call, cmp, piecewise, eq. `name` is a symbol, a neutral function name
    (call) or a comparison sign (cmp); `value` is a decimal text (num)."""
    op: str; name: Optional[str] = None; value: Optional[str] = None; args: tuple = ()
    span: Optional[tuple] = None

def expr_from_dict(record):
    """Rebuild a tree that was read back from _audit as plain JSON."""
    if record is None:
        return None
    args = tuple(expr_from_dict(arg) for arg in record.get("args") or ())
    span = tuple(record["span"]) if record.get("span") else None
    return Expr(record["op"], record.get("name"), record.get("value"), args, span)

def expr_walk(expr):
    """Every node of a tree, parents before children."""
    yield expr
    for arg in expr.args:
        yield from expr_walk(arg)

def expr_symbols(expr):
    """The distinct symbols of a tree, in order of first appearance."""
    seen = []
    for node in expr_walk(expr):
        if node.op == "sym" and node.name not in seen:
            seen.append(node.name)
    return tuple(seen)

_INFIX = {"add": (" + ", 1), "sub": (" - ", 1), "mul": (" * ", 2), "div": (" / ", 2), "pow": ("^", 4)}

def expr_to_text(expr, parent_rank=0):
    """The tree in AIVA's linear notation, the form shown to analysts and to the AI."""
    if expr.op == "num":
        return expr.value
    if expr.op == "sym":
        return expr.name
    if expr.op == "neg":
        text, rank = "-" + expr_to_text(expr.args[0], 3), 3
    elif expr.op in _INFIX:
        sign, rank = _INFIX[expr.op]
        left = expr_to_text(expr.args[0], rank + (1 if expr.op == "pow" else 0))
        text = left + sign + expr_to_text(expr.args[1], rank + (0 if expr.op == "pow" else 1))
    elif expr.op == "call":
        return "%s(%s)" % (expr.name, ", ".join(expr_to_text(arg) for arg in expr.args))
    elif expr.op == "cmp":
        text, rank = (" %s " % expr.name).join(expr_to_text(arg, 1) for arg in expr.args), 0
    elif expr.op == "eq":
        return "%s = %s" % (expr_to_text(expr.args[0]), expr_to_text(expr.args[1]))
    elif expr.op == "piecewise":
        return "piecewise(%s)" % ", ".join(expr_to_text(arg) for arg in expr.args)
    else:
        return "?"
    return "(%s)" % text if rank < parent_rank else text
