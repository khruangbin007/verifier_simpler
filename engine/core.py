"""
Verifier 0.0.2 - core.py - what every other module stands on. For every reviewer.

WHAT THIS FILE DOES
  Three layers, in one file because each is small and all three are needed before a single
  document is read.
  The contracts: every record kind a run writes (a chunk, a model unit, a link, a check, a
  flagged item), the vocabulary of statuses and categories, the words the tool never uses, the
  hash chain that makes a ledger tamper-evident, and the step context every step is handed.
  The reading floor: the machinery for asking a model a question (a prompt in its parts, a
  token estimate, a budget, strict parsing of an answer that is never repaired), the baseline
  decisions about a document's shape (which tag is what, which shape is a table, what level a
  heading sits at, which lines are page furniture), the content account that proves nothing was
  lost or added when a file was read, and the shape digest and validators that let a model help
  slice a file it has never seen - by choosing among options code has already checked, never
  by writing text.
  The front door: what a file IS, from its content; which files of an Inputs folder are documents
  at all; how a spreadsheet, Markdown, delimited rows, RTF or LaTeX become markup the walker
  already reads; and the plain words a format the tool does not read is refused in.

WHAT IT TAKES IN AND PRODUCES
  In: bytes and file names; prompt templates; tag rules; the model's replies as text.
  Out: record objects; a format name; text; prompts and budgets; parsed answers or refusals; the
  content account of a file; the digest of a file's shape and the overlay an answer becomes.

WHICH SHEETS SHOW ITS RESULTS
  None directly. Everything here reaches Output.xlsx through reading.py and review.py; the
  content account and what was not read reach Model_Package_Info.

DESIGN RULES ENFORCED HERE
  R1  no rating and no policy word: the banned list lives here and every sheet is linted
  R2  a file that cannot be read is named, never a silence
  R3  a reply is parsed strictly, never repaired; a refused answer leaves the built-in reading
  R4  every ledger record carries the hash of the one before it
  R6  the format comes from the content, never from the name alone
  R7  nothing in a file is executed; a reply is data
  R13 reading conserves content: every piece of a file ends in a named class, and a model can
      choose how a file is sliced but never lose or add a word

HOW TO SANITY-CHECK IT
  Run tests/test_core.py, tests/test_reading_floor.py and tests/test_formats.py. Feed a file
  the tool does not read (a slide deck, a legacy .doc) to cell 3 and check that Model_Package_Info
  names it with a next step and that its content account says so.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional
from xml.sax.saxutils import escape
import csv
import dataclasses
import hashlib
import io
import json
import os
import re
import unicodedata
import zipfile

# ================================================================================================
# ---------------------------------------------------------------- from verifier0_shared
ENGINE_VERSION = "0.0.2"
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
ST_EXCLUDED = "Not in scope (a person's decision)"
SCOPE_WORDS = ("to use", "to not use")             # what a person writes beside a unit when confirming the outline
CLEAN_STATUSES = (ST_TRACED, ST_SUPPORTING, ST_UNIT_TEST, ST_NARRATIVE, ST_EXCLUDED)
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
    "it uses operations the tool cannot evaluate", "too few valid sample points")
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
    """Return the first word in `text` that the tool's own wording may not use, or "". Enforces: R1"""
    found = _BANNED_RE.search(text or "")
    return found.group(0) if found else ""

# ---------------------------------------------------------------- data contracts (plan 2.3)
@dataclass(frozen=True)
class TableData:
    """A table kept whole: header cells, body rows, and which column identifies a row."""
    header: tuple = (); rows: tuple = (); row_key: str = ""; column_types: tuple = ()

@dataclass(frozen=True)
class EquationData:
    """An equation as found: its source form, whether the tool could read it, and its tree."""
    source_form: str = ""; linear: str = ""; readable: bool = False
    not_readable_reason: str = ""; expression: Optional[dict] = None; image_sha256: str = ""

@dataclass(frozen=True)
class Chunk:
    """One citable unit of a document: a paragraph, a table, a figure or an equation."""
    ref: str; corner: str; source_file: str; kind: str; level: int; heading_chain: tuple
    numbering: str; para_no: Optional[int]; text: str; locator: str; content_hash: str
    table: Optional[TableData] = None; equation: Optional[EquationData] = None
    refs_out: tuple = (); checkable: Optional[bool] = None; numbering_reconstructed: bool = False
    caption: str = ""; not_read_reason: str = ""; para_label: str = ""   # para_label: the number the document itself gives ("36.")

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
    """Which run and step produced a record, at which version, and from which AI exchange if any."""
    run_id: str; step_id: str; step: str; step_version: str; engine_version: str = ENGINE_VERSION
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
    """Something the tool could not line up, raised for a person. It carries no rating."""
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
# A number as prose writes it. Thousands may be grouped with commas in groups of exactly three
# ("1,000", "250,000.5"): that grouping is unambiguous, so it is read as one number. A comma
# between other digit counts ("1,5") is not a grouping and stays two numbers, because in some
# writing it is a decimal comma and guessing which would be guessing. Space grouping ("1 000") is
# not read either, since "section 3 100 samples" would fuse. Enforces: R3
_NUMBER_RE = re.compile(
    r"(?<![\w.])(?P<num>[-\u2212]?(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?)"
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
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:[eE][-+]?\d+)?", text):
        text = text.replace(",", "")                 # the thousands grouping is how it was written, not part of the value
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
    """the tool's neutral tree for a formula. op is one of: num, sym, add, sub, mul, div,
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
    """The tree in the tool's linear notation, the form shown to analysts and to the AI."""
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


# ================================================================================================
# ---------------------------------------------------------------- from verifier0r_reading
# ---------------------------------------------------------------- prompt machinery (from verifier3_mapping)

# ---------------------------------------------------------------- the prompts
# Every question the tool asks, as the model sees it: a version line, the system half, the main half
# with [[UNIT]] and similar places the question builder fills. The text is exact - a question's id is
# the hash of its prompt, and recorded answers are found by that id - so a changed word here is a new
# version and asks new questions. Enforces: R3, R5, R9
PROMPTS = {
    'align-symbols': r'''VERSION 1
=== SYSTEM ===
You match symbols used in code to symbols used in an equation. Reply with JSON only. Use only the symbols shown. Each symbol may be used once.
=== MAIN ===
QUESTION TYPE: align-symbols
TASK: Which symbol of the code stands for which symbol of the equation?
[[UNIT]]
[[ABOUT]]
ANSWER FORMAT
{"alignment":[{"code":"symbol","equation":"symbol"}],"cannot_align":false}
If the symbols cannot be matched one to one, return {"alignment":[],"cannot_align":true}.
''',
    'check-rule': r'''VERSION 1
=== SYSTEM ===
You check whether code applies a rule that a passage states. Reply with JSON only. Quote exact words; do not paraphrase inside quotation fields. Do not rate importance.
=== MAIN ===
QUESTION TYPE: check-rule
TASK: Does the code apply the rule as stated?
[[UNIT]]
[[ABOUT]]
ANSWER FORMAT
{"outcome":"applied","quote_from_passage":"exact words of the rule","quote_from_unit":"exact words of the code that applies it, or empty"}
Allowed outcomes: applied, applied differently, not applied.
''',
    'extract-concepts': r'''VERSION 1
=== SYSTEM ===
You read short passages from a methodology, the code of the model it describes, and the model's documentation, and you list the concepts each passage uses: the named quantities, measures, ratios, factors, methods, categories and defined terms of the subject the documents are about, and every acronym among them. You copy each term exactly as the passage writes it. You never write a term the passage does not contain, never translate one, and never expand an acronym the passage itself does not expand. Reply with JSON only. Do not rate importance.
=== MAIN ===
QUESTION TYPE: extract-concepts
TASK: For each passage below, list the concepts it uses.
[[UNIT]]
ANSWER FORMAT
{"units": {"C-0001": [{"term": "discounted cash flow", "acronym": "DCF"}, {"term": "unit cost", "acronym": ""}]}}
Rules on your answer:
- every key of units must be the reference of a passage shown above;
- every term must appear word for word in that passage (upper and lower case may differ);
- an acronym, when you give one, must also appear word for word in that same passage, where it stands for that term;
- leave out ordinary words, names of people and organisations, dates, page numbers, and headings that name no concept;
- give an empty list for a passage that uses no concept.
''',
    'judge-concepts': r'''VERSION 1
=== SYSTEM ===
You compare pairs of terms used in one set of documents about one subject, and say how the two terms of each pair relate there. Each term comes with a sentence showing how the documents use it. You judge from those sentences and plain knowledge of the subject, and you never write a term of your own. Reply with JSON only. Do not rate importance.
=== MAIN ===
QUESTION TYPE: judge-concepts
[[UNIT]]
RELATIONS
same: the two terms name one concept here - an acronym and what it stands for, two spellings, or two names for one thing
narrower: the first term is a kind or a part of the second
broader: the second term is a kind or a part of the first
related: different concepts that belong together
different: unrelated
ANSWER FORMAT
{"pairs": {"P1": "same", "P2": "related"}}
Rules on your answer:
- every key of pairs must be a pair shown above, and every pair shown must be answered;
- every value must be one of the five relations listed above;
- say same only where the documents use the two terms for one concept; where in doubt, say related.
''',
    'interpret-code': r'''VERSION 1
=== SYSTEM ===
You explain what one piece of R code does, in plain words, for a reader who validates models and is not a programmer. You are shown the piece itself and where it sits in the whole package. Say only what the code shows; do not guess at intentions the code does not show. Reply with JSON only. Quote exact characters of the code; do not paraphrase inside the quotation field. Do not rate importance.
=== MAIN ===
QUESTION TYPE: interpret-code
TASK: Say what the piece of code does and what it is for within the package, in at most 80 words. Name what it takes in and what it produces. Where it applies a number, a limit or a condition, say so with the number exactly as written. Use what you are told about the package only to say what the piece is for; describe the piece, not the package.
[[UNIT]]
[[ABOUT]]
ANSWER FORMAT
{"interpretation":"plain words, at most 80 words","quote_from_unit":"exact characters of the piece of code that the interpretation chiefly rests on"}
''',
    'judge-doc-to-canon': r'''VERSION 1
=== SYSTEM ===
You compare one item with lettered passages. Reply with JSON only.
Use only the letters shown. "NONE" (an empty list of matches) is a valid and common answer.
Quote exact words; do not paraphrase inside quotation fields. Do not rate importance.
=== MAIN ===
QUESTION TYPE: judge-doc-to-canon
TASK: Which passages of the methodology, if any, does this passage of the documentation correspond to, and how?
[[UNIT]]
[[ABOUT]]
PASSAGES
[[PASSAGES]]
ANSWER FORMAT
{"matches":[{"letter":"A","relation":"consistent with","confidence":0-100,
             "quote_from_passage":"exact words from the passage","quote_from_unit":"exact words from the unit"}],
 "none_reason":""}
Allowed relation words: consistent with, inconsistent with, merely related.
If no passage corresponds, return {"matches":[],"none_reason":"one plain sentence"}.
If the unit states nothing that could be checked (no formula, number, rule or definition), add "states_nothing_checkable": true.
''',
    'judge-doc-to-model': r'''VERSION 1
=== SYSTEM ===
You compare one item with lettered passages. Reply with JSON only.
Use only the letters shown. "NONE" (an empty list of matches) is a valid and common answer.
Quote exact words; do not paraphrase inside quotation fields. Do not rate importance.
=== MAIN ===
QUESTION TYPE: judge-doc-to-model
TASK: Which units of the package, if any, does this passage of the documentation describe, and how?
[[UNIT]]
[[ABOUT]]
PASSAGES
[[PASSAGES]]
ANSWER FORMAT
{"matches":[{"letter":"A","relation":"describes","confidence":0-100,
             "quote_from_passage":"exact words from the passage","quote_from_unit":"exact words from the unit"}],
 "none_reason":""}
Allowed relation words: describes, inconsistent with.
If no passage corresponds, return {"matches":[],"none_reason":"one plain sentence"}.
''',
    'judge-unit-to-canon': r'''VERSION 1
=== SYSTEM ===
You compare one item with lettered passages. Reply with JSON only.
Use only the letters shown. "NONE" (an empty list of matches) is a valid and common answer.
Quote exact words; do not paraphrase inside quotation fields. Do not rate importance.
=== MAIN ===
QUESTION TYPE: judge-unit-to-canon
TASK: Which passages of the methodology, if any, does this unit of the package correspond to, and how?
[[UNIT]]
[[ABOUT]]
PASSAGES
[[PASSAGES]]
ANSWER FORMAT
{"matches":[{"letter":"A","relation":"implements","confidence":0-100,
             "quote_from_passage":"exact words from the passage","quote_from_unit":"exact words from the unit"}],
 "none_reason":""}
Allowed relation words: implements, partly implements, deviates from, merely related.
If no passage corresponds, return {"matches":[],"none_reason":"one plain sentence"}.
''',
    'judge-unit-to-doc': r'''VERSION 1
=== SYSTEM ===
You compare one item with lettered passages. Reply with JSON only.
Use only the letters shown. "NONE" (an empty list of matches) is a valid and common answer.
Quote exact words; do not paraphrase inside quotation fields. Do not rate importance.
=== MAIN ===
QUESTION TYPE: judge-unit-to-doc
TASK: Which passages of the documentation, if any, describe this unit of the package, and how?
[[UNIT]]
[[ABOUT]]
PASSAGES
[[PASSAGES]]
ANSWER FORMAT
{"matches":[{"letter":"A","relation":"describes","confidence":0-100,
             "quote_from_passage":"exact words from the passage","quote_from_unit":"exact words from the unit"}],
 "none_reason":""}
Allowed relation words: describes, consistent with, inconsistent with.
If no passage corresponds, return {"matches":[],"none_reason":"one plain sentence"}.
''',
    'map-table-columns': r'''VERSION 1
=== SYSTEM ===
You match the columns of one table to the columns of lettered tables. Reply with JSON only. Use only the letters and the column names shown.
=== MAIN ===
QUESTION TYPE: map-table-columns
TASK: Which lettered table, if any, states the same values as the package table, which column is which, and which column identifies a row?
[[UNIT]]
PASSAGES
[[PASSAGES]]
ANSWER FORMAT
{"table":"A","columns":[{"package":"column name","other":"column name"}],"key":{"package":"column name","other":"column name"}}
If no table corresponds, return {"table":"NONE","reason":"one plain sentence"}.
''',
    'package-plan': r'''VERSION 2
=== SYSTEM ===
THE READER'S PROCEDURE
1. Unpack the package - a tarball, a ZIP, or a source folder put in unpacked - refusing any member that breaks the limits; where it is not an R package, say so. 2. Work out which reader each member gets from where it lies and what it is; where the built-in tests give a member none, ask which existing reader should take it and apply the answer. 3. Parse R source into functions, objects and formula statements. 4. Decode stored data into tables of values. 5. Read help pages and vignettes. 6. Tie each roxygen block to what it documents. 7. Number every unit in a fixed order.

QUALITY RULES THE READER WORKS UNDER
- Every non-blank line of every member that holds text lies inside a unit, is refused with a reason, or is carried by a unit that says it could not be read. A member the tool cannot read as text is counted as one piece of its own.
- A reader chosen for a member changes only which existing reader takes it. It never changes how that reader works.
- Where a member's first lines show assignments and calls it is R code, wherever in the package it lies.

THE READER NEVER
- Never leave a member of the package out of the account in silence. An open account is written down, and the run goes on.
- Never write text of your own into an answer about a package. Name only paths you were shown as not placed, and give only readers from the list you were given.
- Never ask for a member to be skipped: there is no such reader. A file that cannot be made sense of becomes a unit that says so.
- Never let an answer reach the parsing of R code, the building of expression trees or the decoding of stored data. Reading code is a parse, not an opinion.
Never execute or evaluate anything from a package. Never import a package to inspect it.

You are given the list of files inside one R package, with how large each is and which reader the built-in tests already give it. For the files those tests leave unplaced you are shown the first few lines. Your task is to say WHICH EXISTING READER should take each unplaced file.
You choose from a fixed list only. You never write text of your own into an answer: every path you name must be one shown to you as not placed, and every reader you give must be one of the readers listed. Reply with JSON only. Do not rate importance.
=== MAIN ===
QUESTION TYPE: package-plan
TASK: Give every file marked NOT PLACED one of the readers below.
THE FILES IN THE PACKAGE
[[UNIT]]
READERS YOU MAY USE
r-source: R code, to be parsed into functions and objects. Use for a file of R code wherever it lies, including a folder the tests do not expect.
r-data: stored data to be decoded into a table of values.
help-page: a written help page for an object (an .Rd page).
vignette: a longer written piece mixing prose and code.
table-file: a table of values stored as text, such as comma- or tab-separated rows.
prose: plain writing with no code and no table in it. Use this when none of the others fits.
WHAT TO LOOK FOR
R code usually shows assignments with <- and calls with round brackets. A help page shows braces after a backslash. A vignette opens with a block between two lines of three dashes, or holds fenced code. A table file shows the same separator repeated on every line, with a first line of column names.
ANSWER FORMAT
{"readers":{"inst/extra/helpers.R":"r-source","inst/extdata/floors.csv":"table-file"},"why":{"inst/extra/helpers.R":"a short reason in plain words"}}
Rules on your answer:
- every key of readers must be a path shown to you above as NOT PLACED;
- every file marked NOT PLACED must appear in readers: leave none out;
- every value of readers must be one of the six readers listed above;
- there is no reader that means skip, ignore or leave unread. A file you cannot make sense of is given "prose", and the reader will say plainly that it could not read it;
- every key of why, if you give any, must also be a path marked NOT PLACED.
''',
    'read-formula-from-prose': r'''VERSION 1
=== SYSTEM ===
You read a formula that a paragraph states in words. Reply with JSON only. Use only names that occur in the paragraph. Write the formula with + - * / ^ ( ) and the functions max, min, exp, ln, sqrt.
=== MAIN ===
QUESTION TYPE: read-formula-from-prose
TASK: Write the formula that this paragraph states, as one line of the form name = expression.
[[UNIT]]
ANSWER FORMAT
{"formula":"name = expression","no_formula_stated":false}
If the paragraph states no formula, return {"formula":"","no_formula_stated":true}.
''',
    'second-opinion': r'''VERSION 1
=== SYSTEM ===
You look for differences between one item and lettered passages. Reply with JSON only. Use only the letters shown. Quote exact words; do not paraphrase inside quotation fields. Naming no difference is a valid and common answer. Do not rate importance.
=== MAIN ===
QUESTION TYPE: second-opinion
TASK: Identify any difference between what the unit does or states and what the passages state.
[[UNIT]]
[[ABOUT]]
PASSAGES
[[PASSAGES]]
ANSWER FORMAT
{"differences":[{"letter":"A","quote_from_passage":"exact words","quote_from_unit":"exact words","what_differs":"one plain sentence"}]}
If there is no difference, return {"differences":[]}.
''',
    'slice-rules': r'''VERSION 2
=== SYSTEM ===
THE READER'S PROCEDURE
1. Detect the format from the content, looking inside a ZIP to tell a Word file from a spreadsheet or a slide deck; refuse a format the tool does not read in plain words with a next step, and never decode binary data as text; convert Markdown, delimited rows, spreadsheets, RTF and LaTeX to markup the walker already reads. 2. Repair what must be repaired and record each repair. 3. Work out what each tag of the file is for; where the built-in rules are unsure, ask what the shape of the file means and apply the answer under everything the rules already know. 4. Read blocks in document order. 5. Infer levels where nesting is flat. 6. Keep each table whole. 7. Read equation markup into linear notation and an expression tree. 8. Hash every chunk.

QUALITY RULES THE READER WORKS UNDER
- Every smallest piece of text in the file ends in one named class: kept in a unit, kept in a unit's other fields, read into another form, left out under a named rule, or reported as not read. What is in none of them is counted and located on Model_Package_Info.
- Nothing a unit shows may come from anywhere but the file or a transform named in the code.
- A heading names the block around it: it usually occurs about as often as that block, holds short text of its own, and opens it. A paragraph holds longer text and does not open the block around it. A tag that holds other tags is a container or a heading, never a paragraph: reading it as a paragraph would make the file say twice what it says once.
- Where the words of a file are already read correctly and only its shape is in doubt, change the shape and leave the words exactly where they are.
A table is never split and never merged with its neighbours. A figure or equation that cannot be read is still a chunk. Reading order is stable.

THE READER NEVER
- Never close the account over a file that yielded nothing and said nothing: a large file with no text and no reason is a file that was not opened.
- Never leave a piece of the file out of the account in silence. An open account is written down, and the run goes on.
- Never write text of your own into an answer about a file's shape. Name only tags you were shown, and give only families from the list you were given. There is no way to tell the reader to skip a tag, and no answer may leave a word of the file out of a unit.
- Never overrule what a person wrote in Inputs/tag_rules.yaml, a schema the tool already ships, or a table whose rows were counted. Speak where the reader guessed, and nowhere else.
Never execute or evaluate anything from an input. Never skip a block silently. Never keep a document-type declaration.

You are given the SHAPE of one document: a list of the tags it uses and how each behaves, with a few short samples. You never see the document. Your task is to say what each tag is FOR, so that a reader can slice the document into citable units.
You choose from fixed lists only. You never write text of your own into an answer: every tag you name must be one shown to you, and every family you give must be one of the families listed. Reply with JSON only. Do not rate importance.
=== MAIN ===
QUESTION TYPE: slice-rules
TASK: Give each tag a family, and say which tags are headings of the blocks around them.
THE SHAPE OF THE FILE
[[UNIT]]
FAMILIES YOU MAY USE
heading: names the section around it, and everything below it belongs under it
container: holds other blocks and little or no text of its own
paragraph: a statement, a sentence or a run of prose
list_container: holds items; list_item: one item of such a list
These five are the whole list. Tables, rows, cells, captions, figures, equations and inline marks are worked out by the reader itself and are not yours to give; where a tag is one of those it is marked ALREADY READ AS and you should leave it alone.
WHAT TO LOOK FOR
A heading usually occurs about as often as the container it names, holds short text of its own, and is the FIRST CHILD of that container. A paragraph holds longer text and is not the first child. A container holds other tags and little or no text of its own.
A tag marked ALREADY READ AS is one the reader already knows for certain; leave it exactly as it is. A tag marked GUESSED AS is one the reader worked out on the spot and is unsure of: that is where your answer is wanted. A tag marked neither is one the reader has nothing at all to say about.
ANSWER FORMAT
{"families":{"tagname":"heading","othertag":"paragraph"},"levels":{"tagname":1},"why":{"tagname":"a short reason in plain words"}}
Rules on your answer:
- every key of families, levels and why must be a tag shown to you above;
- every value of families must be one of the five families listed above;
- a tag shown as holding other tags may only be heading, container or list_container: reading it as a paragraph would say its contents twice;
- every value of levels must be a whole number from 1 to 9, and levels may name only tags you called heading;
- "ignore" is not a family you may use, and there is no way to tell the reader to skip a tag;
- give a family for every tag you are shown, including ones already read.
''',
}

def load_prompt(question_type):
    """A prompt template: its version line, its SYSTEM part and its MAIN part with slots."""
    text = PROMPTS[question_type]
    version, rest = text.split("\n", 1)
    system, main = rest.split("=== MAIN ===\n", 1)
    return {"version": version.strip(), "system": system.replace("=== SYSTEM ===\n", "").strip(), "main": main.strip()}

def estimate_tokens(prose, code=""):
    """No tokenizer can be installed, so tokens are estimated from characters, on the safe
    side: one token per 3.2 characters of prose and per 2.5 characters of code and numbers."""
    return int(len(prose) / 3.2 + len(code) / 2.5) + 1

def prompt_budget(settings, system_prompt):
    """Tokens available for the main prompt: the smaller of the target size (long prompts are
    answered badly) and what the cap leaves after all reserves."""
    room = settings["token_cap"] - settings["answer_reserve"] - settings["thinking_reserve"] - estimate_tokens(system_prompt)
    return min(int(settings["prompt_target_tokens"]), int(room * (1 - settings["safety_margin"])))

def cut_text(text, limit, keep_words=()):
    """Cut a long text to `limit` characters around the first of `keep_words` it contains (the
    matched region), marking the cuts; lines stay whole where possible."""
    if len(text) <= limit:
        return text
    lowered = text.lower()
    hits = [lowered.find(word.lower()) for word in keep_words if word and lowered.find(word.lower()) >= 0]
    centre = min(hits) if hits else 0
    start = max(0, min(centre - limit // 3, len(text) - limit))
    piece = text[start:start + limit]
    return ("[... cut ...] " if start else "") + piece + (" [... cut ...]" if start + limit < len(text) else "")

# ---------------------------------------------------------------- answer machinery (from verifier3_mapping)
def last_json_object(text):
    """The last balanced {...} object in a text, or None. Braces inside strings are skipped."""
    end = text.rfind("}")
    while end >= 0:
        depth, in_string, position = 0, False, end
        while position >= 0:
            char = text[position]
            if char == '"' and (position == 0 or text[position - 1] != "\\"):
                in_string = not in_string
            elif not in_string:
                depth += 1 if char == "}" else -1 if char == "{" else 0
                if depth == 0:
                    return text[position:end + 1]
            position -= 1
        end = text.rfind("}", 0, end)
    return None

def strict_json(text):
    """Strict parsing: no repair of malformed JSON, and a repeated key is refused."""
    def no_repeats(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("repeated key")
        return dict(pairs)
    return json.loads(text, object_pairs_hook=no_repeats)

# ---------------------------------------------------------------- element helpers (from verifier1_documents)
def local_name(tag):
    """'{namespace}oMath' and 'm:oMath' both become 'omath'."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()

def attribute(element, name):
    """The value of an attribute, whatever namespace prefix it carries."""
    for key, value in element.attrib.items():
        if local_name(key) == name:
            return value
    return ""

def child_named(element, name):
    """The first child with this local tag name, or None."""
    for child in element:
        if local_name(child.tag) == name:
            return child
    return None

# ---------------------------------------------------------------- baseline slicing (from verifier1_documents)
def attribute_text(element, names, digits_too=False):
    """The first of the named attributes that holds text worth reading, with its name. A bare
    number is no heading, so it is passed over unless digits_too."""
    for name in names:
        value = (element.get(name) or "").strip()
        if value and (digits_too or not value.isdigit()):
            return value, name
    return "", ""

BLOCK_FAMILIES = ("heading", "container", "list_container", "paragraph", "list_item", "table")

def written_numbering(element, rules):
    """The numbering an element carries in an attribute, exactly as the document wrote it
    (num="36." gives "36."): more faithful than any count the tool could make, skipped numbers included."""
    return attribute_text(element, rules["numbering_attributes"], digits_too=True)[0]

def table_rows(element, rules):
    """The rows of a table: the children that hold cells, looked for directly below the table
    and below the wrappers the rules know (thead, tbody, tgroup)."""
    known = rules["family_of"]
    holders = [element] + [part for part in element if known.get(local_name(part.tag)) == "table_part"]
    return [row for holder in holders for row in holder
            if local_name(row.tag) and len(row) and known.get(local_name(row.tag)) in (None, "row")]

def discover_table_shape(element, rules, is_table):
    """Give a family to every tag used inside a table, whatever the tags are called. Everything
    in a row is a cell. Two kinds are told apart by name, since only the name says what they are
    for: a tag holding the table's number or title (<tablenumber>, <tabletitle>) is the caption,
    one holding a column heading (<tablecolhead>) a header cell. A tag nobody anticipated
    (<tablesub>, <tabletext>) is simply a cell and keeps its text.
    An element the rules already name as a table (is_table) needs no more than that: real tables
    have rows of differing width (a note below, a heading that spans). An element NOT known to be
    a table has to make the case by its shape, and two guards keep the skeleton of a document,
    which repeats twice over as a table does, from being read as one: a cell holds words and
    never a block, and most rows are the same width. Returns (row tags, {tag: family}) or None."""
    known, rows = rules["family_of"], table_rows(element, rules)
    cells = [cell for row in rows for cell in row if local_name(cell.tag)]
    if not cells:
        return None
    if not is_table:
        widths = [sum(1 for cell in row if local_name(cell.tag)) for row in rows]
        usual = max(set(widths), key=widths.count)
        if (len(rows) < 2 or len({local_name(row.tag) for row in rows}) > 1 or usual < 2 or widths.count(usual) * 2 <= len(rows)
                or any(known.get(local_name(cell.tag)) for cell in cells)
                or any(known.get(local_name(below.tag)) in BLOCK_FAMILIES for cell in cells for below in cell)):
            return None
    families = {}
    for name in {local_name(cell.tag) for cell in cells}:
        if any(word in name for word in rules["caption_tag_words"]):
            families[name] = "caption"
        else:
            families[name] = "header_cell" if any(word in name for word in rules["header_tag_words"]) else "cell"
    return {local_name(row.tag) for row in rows}, families

def discover_families(root, rules, report):
    """Work out a family for each tag this document uses that the rules do not name, from the
    way the tag behaves here. The rules always win, so a schema the tool already knows is read
    exactly as before; discovery only speaks where they are silent. It looks, in order, for: a
    table; an element carrying its own heading in an attribute; one holding other blocks (a
    container); one holding text (a paragraph). Every decision is recorded with its reason in
    plain words, shown on Model_Package_Info, and can be overridden in Inputs/tag_rules.yaml.
    Enforces: R9"""
    known, found = rules["family_of"], {}

    def note(tag, family, reason):
        if tag not in known and tag not in found:
            found[tag] = family
            report[tag] = {"family": family, "reason": reason, "count": 1 if tag == name else 0}

    # A tag that sits in running text, never holding a block of its own, is read inline: its
    # words belong to the sentence around it, not to a paragraph of their own.
    def readable_elements(element):
        """Every element the walker will actually read. Discovery stops where the walker
        stops: the inside of an equation or a figure is read by its own reader, and what the
        rules ignore is never read at all, so neither is catalogued here."""
        yield element
        if known.get(local_name(element.tag)) in ("equation", "figure", "ignore"):
            return
        for child in element:
            if local_name(child.tag):
                yield from readable_elements(child)

    elements = list(readable_elements(root))
    inline_looking = set()
    for element in elements:
        for child in element:
            if (child.tail or "").strip() or (element.text or "").strip():
                inline_looking.add(local_name(child.tag))

    for element in elements:
        name = local_name(element.tag)
        if not name:
            continue
        if name in report:
            report[name]["count"] += 1
        # Table shape is looked for under a known table too: the element may be named in the
        # rules while the row and cell tags inside it are not.
        if known.get(name) == "table" or name not in known:
            shape = discover_table_shape(element, rules, known.get(name) == "table")
            if shape:
                row_tags, families = shape
                note(name, "table", "holds rows of cells")
                for row_tag in sorted(row_tags):
                    note(row_tag, "row", "holds the cells of <%s>" % name)
                reasons = {"caption": "holds the number or the title of <%s>" % name,
                           "header_cell": "holds a column heading of <%s>" % name,
                           "cell": "sits in a row of <%s>" % name}
                for tag in sorted(families):
                    note(tag, families[tag], reasons[families[tag]])
                continue
        if name in known or name in found:
            continue
        blocks_below = any(local_name(child.tag) and known.get(local_name(child.tag)) not in ("inline", "ignore")
                           for child in element)
        heading, attribute = attribute_text(element, rules["heading_attributes"])
        if heading and blocks_below:
            note(name, "container", "carries its own heading in the %s attribute" % attribute)
        elif blocks_below:
            note(name, "container", "holds other blocks")
        elif name in inline_looking and not len(element):
            note(name, "inline", "appears inside running text")
        elif (element.text or "").strip() or len(element):
            note(name, "paragraph", "holds text")
        else:
            note(name, "paragraph", "empty")
    return found

def first_numbering(text, rules):
    """The numbering at the start of a heading as written, and the name of its scheme."""
    for scheme in rules["numbering_schemes"]:
        match = re.match(scheme["pattern"], text)
        if match:
            return match.group(0).strip(), scheme["name"]
    return "", ""

def infer_levels(blocks, rules):
    """Give every heading its level. When the file nests its sections, the nesting decides.
    When nesting is flat, numbering decides: a dotted number gives its depth directly
    (relative to the level of plain numbers); any other scheme seen for the first time is one
    level deeper than the heading before it, and a scheme seen before returns to its level."""
    headings = [b for b in blocks if b["type"] == "heading"]
    hints = sorted({b["level_hint"] for b in headings if b["level_hint"] is not None})
    nested = len(hints) > 1
    scheme_level, current, run_hint, run_schemes = {}, 0, None, {}
    for block in headings:
        written, scheme = first_numbering(block["text"], rules)
        if block["numbering"] and not scheme:
            written, scheme = first_numbering(block["numbering"] + " ", rules)
        block["numbering"] = block["numbering"] or written
        if nested:                                       # a flat-numbered stretch inside a nested file (an annex)
            if block["level_hint"] != run_hint:
                run_hint, run_schemes = block["level_hint"], {}
            if scheme and scheme != "dotted":
                run_schemes.setdefault(scheme, len(run_schemes))
            block["level"] = hints.index(block["level_hint"]) + 1 + run_schemes.get(scheme, 0)
        elif scheme == "dotted":
            depth = block["numbering"].strip(".").count(".") + 1
            block["level"] = scheme_level.get("number", 1) + depth - 1
        elif scheme:
            if scheme not in scheme_level:
                scheme_level[scheme] = current + 1
            block["level"] = scheme_level[scheme]
        else:
            block["level"] = max(1, current) if current else 1
        current = block["level"]
    return blocks

def without_page_furniture(lines, pages, state, file_name):
    """Leave out what a page carries only because it is a page: the running title, the footer
    with its date and page number, the logo. Such a line sits in the top or bottom margin and
    comes back on most pages, the same but for its digits. It is not part of what the document
    says, and left in it cuts a list or a sentence in two wherever a page ends. What was left
    out is reported, so nothing goes missing unseen: this is the "declared drop" class of the
    content account, and the note is what declares it. Enforces: R2, R13"""
    same = lambda entry: (entry["edge"], re.sub(r"\d+", "#", entry["text"]))
    on_pages = {}
    for entry in lines:
        if entry["edge"] and "text" in entry:
            on_pages.setdefault(same(entry), set()).add(entry["page"])
    furniture = {key for key, found in on_pages.items() if pages >= 3 and len(found) >= max(3, pages // 2)}
    for entry in lines:                              # a declared drop: named, counted, and shown in the account
        if entry.get("edge") and "text" in entry and same(entry) in furniture:
            state.dropped.append(entry["text"])
    for edge, text in sorted(furniture):
        state.notes.append("%s: left out as a page header or footer, because it repeats in the %s margin of %d of %d pages: '%s'"
                           % (file_name, edge, len(on_pages[(edge, text)]), pages, text))
    return [entry for entry in lines if not (entry["edge"] and "text" in entry and same(entry) in furniture)]

# ---------------------------------------------------------------- the fidelity ledger
# Enforces: R13. A reader may decide HOW a file is sliced. It may not add a word the file does
# not contain, and it may not lose a word the file does contain. Neither is taken on trust: the
# smallest countable pieces of the file are counted independently of the reader that read it,
# and every one of them has to end in a named class.

ATOM_CLASSES = ("in unit text", "relocated", "rewritten", "declared drop", "not read", "unaccounted")

# An atom found in one of these places is not expected word for word in a unit, and why.
# "rewritten" is the class R1 added to the plan's four: an equation is not lost and not carried
# either - it is READ into the tool's linear notation, which is a third thing and is named as one.
EXPLAINED_BY_PLACE = {
    "equation": ("rewritten", "read into the tool's linear notation; what it was read from is named in the unit's equation"),
    "attribute": ("declared drop", "an attribute the rules do not read: an identifier, a style, a namespace or a file name"),
    "style or script": ("declared drop", "the content of a style or script element, which is not what the document says"),
    "page without a text layer": ("not read", "a page that carries no text layer, which the tool cannot count without reading the picture"),
    "tracked change": ("declared drop", "an unaccepted deletion, which is not what the document says: it is what somebody proposed the document should stop saying"),
    "header": ("declared drop", "the running header of a page, which the page carries because it is a page"),
    "footer": ("declared drop", "the running footer of a page, which the page carries because it is a page"),
    "comment": ("declared drop", "a comment somebody left on the document, which is not what the document says"),
    "whole file not read": ("not read", "a file in a format the tool does not read, named with its reason and a next step"),
}

# Below this many bytes a file may honestly hold no text; above it, a reader that found none at
# all and said nothing has probably not opened it. The account refuses to close over that.
VACUOUS_BYTES = 1024

def tokens(text):
    """The countable pieces of a text: runs without white space, after the same normalisation
    every chunk's text goes through. White space is not counted, because folding a list joins
    its items with a space and collapsing runs of space is a declared transform."""
    return [piece for piece in normalise_text(text or "").split(" ") if piece]

def bag(text):
    """The tokens of a text as counts, so that a word appearing twice must be found twice."""
    found = {}
    for piece in tokens(text):
        found[piece] = found.get(piece, 0) + 1
    return found

def bag_of(texts):
    """The tokens of several texts as one set of counts."""
    total = {}
    for text in texts:
        for piece, count in bag(text).items():
            total[piece] = total.get(piece, 0) + count
    return total

def minus(left, right):
    """What is left of `left` after taking away as much of `right` as it holds."""
    rest = {}
    for piece, count in left.items():
        keep = count - right.get(piece, 0)
        if keep > 0:
            rest[piece] = keep
    return rest

def atom(place, locator, text):
    """One countable piece of an input: where in the file it came from, and what it says."""
    return {"place": place, "locator": locator, "text": text}

MARKUP_METADATA = ("style", "script")

def atoms_of_markup(root, file_name, rules=None):
    """Every text node and every tail under every element, and every attribute value, each with
    the place it was found in. Place matters to the account: text inside an equation is read
    into the tool's linear notation rather than kept word for word, an attribute the rules do not
    read is metadata about the document rather than something the document says, and the
    content of a style or script element is not prose at all. Naming the place is what lets
    each of those be explained by a rule instead of counted as a loss."""
    families = (rules or {}).get("family_of", {})
    carriers = set((rules or {}).get("heading_attributes", ())) | set((rules or {}).get("numbering_attributes", ()))
    found, position = [], 0
    def walk(element, inside):
        nonlocal position
        position += 1
        name = local_name(element.tag)
        family = families.get(name) or inside
        where = "%s element %d <%s>" % (file_name, position, name)
        place = "equation" if family == "equation" else "style or script" if name in MARKUP_METADATA else "body"
        if (element.text or "").strip():
            found.append(atom(place, where, element.text))
        for child in element:
            walk(child, family if family in ("equation", "figure") else "")
            if (child.tail or "").strip():
                found.append(atom(place, where + " (tail)", child.tail))
        for attribute_name, value in sorted(element.attrib.items()):
            if value.strip():
                found.append(atom("attribute" if local_name(attribute_name) not in carriers else "body",
                                  "%s @%s" % (where, local_name(attribute_name)), value))
    walk(root, "")
    return found

DOCX_PARTS = (("word/document.xml", "body"), ("word/footnotes.xml", "footnote"), ("word/endnotes.xml", "endnote"),
              ("word/comments.xml", "comment"))
WORD_TEXT = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
WORD_DELETED = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}delText"

def atoms_of_docx(archive, parse, file_name):
    """Every run of text in a Word file, wherever Word put it. Text boxes sit inside the body
    part and are counted with it; footnotes, endnotes, comments, headers and footers are parts
    of their own and are counted here even where the reader does not yet read them, so that
    they show as unaccounted rather than vanishing without a word."""
    found = []
    named = list(DOCX_PARTS) + [(name, "header" if "header" in name else "footer")
                                for name in sorted(archive.namelist())
                                if name.startswith("word/header") or name.startswith("word/footer")]
    for part, place in named:
        if part not in archive.namelist():
            continue
        try:
            root = parse(archive.read(part))
        except Exception:                                # a part that will not parse is counted and named here
            found.append(atom(place, "%s %s" % (file_name, part), ""))
            continue
        for position, node in enumerate(root.iter(), start=1):
            if node.tag in (WORD_TEXT, WORD_DELETED) and (node.text or "").strip():
                kind = "tracked change" if node.tag == WORD_DELETED else place
                found.append(atom(kind, "%s %s run %d" % (file_name, part, position), node.text))
    return found

def atoms_of_pdf(document, file_name):
    """Every word the text layer of every page yields. A page with no text layer is counted as
    one atom with no text, so that a scanned page is visible in the account as a page that
    carries something the tool cannot count rather than as a page that carries nothing."""
    found = []
    for number, page in enumerate(document.pages, start=1):
        text = page.extract_text() or ""
        found.append(atom("body" if text.strip() else "page without a text layer", "%s p.%d" % (file_name, number), text))
    return found

def atoms_of_plain_text(text, file_name):
    """Every non-blank line of a plain text file."""
    return [atom("body", "%s line %d" % (file_name, number), line)
            for number, line in enumerate(text.split("\n"), start=1) if line.strip()]

# Transforms that put a word into a unit without taking it from an atom, or move it out of a
# unit's text into another of its fields. Each is named here, once. The account closes BECAUSE
# of this list: take an entry away and the words it explains are reported as injected or lost.
# Enforces: R13
DECLARED_MARKS = (
    ("list marker", "the mark that shows an item of a folded list: '-', or the number the document gave it"),
    ("reconstructed numbering", "a heading number Word produces automatically and does not store, counted back by the tool and marked as reconstructed"),
    ("linear form of an equation", "an equation written out in the tool's linear notation; the markup it was read from is kept in the equation's source form"),
    ("words read from a picture", "what OCR made of a picture, shown to help a person and never evidence"),
    ("the heading above a Word file's notes", "footnotes and endnotes are parts of their own and are read after the body, under a heading the tool gives them"),
)
DECLARED_RELOCATIONS = (
    ("heading chain", "a heading is not a unit of its own: its text is carried by every unit below it"),
    ("caption", "the caption of a table or a figure is kept in the unit's caption, not in its text"),
    ("table cells", "the cells of a table are kept in the unit's table, and shown in its display form"),
    ("equation source", "the markup an equation was read from is kept in the unit's equation"),
    ("numbering as written", "the number a document gives a paragraph is kept in the unit's label"),
)

def kept_and_relocated(chunks):
    """Two bags: what the units say in their text, and what they keep in their other fields.

    A relocated text is CARRIED, not copied: one heading of the file appears in the heading
    chain of every unit below it, and the file holds it once. So the fields that repeat by
    design - the heading chain and the section numbering - are counted once for each distinct
    text, while a caption, a table and an equation belong to their own unit and are counted
    every time they occur."""
    kept, moved, carried = [], [], set()
    for chunk in chunks:
        kept.append(chunk.get("text") or "")
        carried.update(chunk.get("heading_chain") or ())
        carried.add(chunk.get("numbering") or "")
        moved.append(chunk.get("caption") or "")
        moved.append(chunk.get("para_label") or "")
        table = chunk.get("table")
        if table:
            moved.extend(str(cell) for row in (list(table.get("header") or []),) + tuple(table.get("rows") or []) for cell in row)
        equation = chunk.get("equation")
        if equation:
            moved.append(equation.get("source_form") or "")
    return bag_of(kept), bag_of(moved + sorted(carried))


def marks_of_rendering(chunks):
    """Marks every reader makes, whatever the format: the form the tool renders a table, a figure or
    an equation in; the markup an equation was read from, whose tags are not words the document
    says; a number a document did not write that the tool counted back; and the place label the tool
    gives a paragraph of a PDF ("p.4 2") so that a person can find it again. Enforces: R13"""
    found = []
    for chunk in chunks:
        if chunk.get("kind") in ("Table", "Figure", "Equation"):
            found.append(chunk.get("text") or "")
        equation = chunk.get("equation")
        if equation:
            found.append(equation.get("source_form") or "")
            found.append(equation.get("linear") or "")
        found.append(chunk.get("numbering") or "")
        found.append(chunk.get("para_label") or "")
        if chunk.get("numbering_reconstructed"):
            found.extend(chunk.get("heading_chain") or ())
    return found

def account(file_name, atoms, chunks, dropped=(), marks=(), file_bytes=0):
    """The content account of one file. Every atom ends in exactly one class, and every token a
    unit shows comes from an atom or from a named mark. What a unit does not show word for word
    is explained by WHERE it was found (EXPLAINED_BY_PLACE) before it is called a loss, so that
    an equation read into linear notation and an identifier in an attribute are each named
    rather than swept into the same silence. Returns the counts, what could not be placed with
    where it was found, and what could not be explained. Enforces: R13"""
    source = bag_of([one["text"] for one in atoms if one["place"] not in EXPLAINED_BY_PLACE])
    kept, moved = kept_and_relocated(chunks)
    dropped_bag = bag_of(dropped)
    found = {"file": file_name, "in unit text": 0, "relocated": 0, "rewritten": 0, "declared drop": 0, "not read": 0}
    left = dict(source)
    for name, taken in (("in unit text", kept), ("relocated", moved), ("declared drop", dropped_bag)):
        used = minus(left, minus(left, taken))
        found[name] = sum(used.values())
        left = minus(left, used)
    for one in atoms:                                # what its place explains, and under which rule
        if one["place"] in EXPLAINED_BY_PLACE:
            name = EXPLAINED_BY_PLACE[one["place"]][0]
            found[name] = found[name] + max(1, len(tokens(one["text"])))
    refused = any(one["place"] == "whole file not read" for one in atoms)
    for chunk in chunks:
        if chunk.get("not_read_reason") and not refused:
            found["not read"] += 1
    placed = dict(kept)
    for extra_bag in (moved, dropped_bag):
        for piece, count in extra_bag.items():
            placed[piece] = placed.get(piece, 0) + count
    added = minus(minus(placed, source), bag_of(marks))
    found["atoms"] = sum(source.values()) + sum(found[name] for name in ("rewritten", "declared drop", "not read"))
    found["unaccounted"] = sum(left.values())
    found["injected"] = sum(added.values())
    found["where unaccounted"] = sorted(one["locator"] for one in atoms
                                        if one["place"] not in EXPLAINED_BY_PLACE
                                        and any(piece in left for piece in tokens(one["text"])))[:12]
    found["what unaccounted"] = sorted(left)[:24]
    found["what injected"] = sorted(added)[:24]
    # A file that is large, yielded no text at all, and was neither refused nor said to be
    # unreadable has probably not been opened. Until 0.0.2 such a file closed its account, because
    # an account over nothing balances. That is the one place the identity held while everything
    # was lost, so it is the one place it now refuses to close. Enforces: R13
    found["vacuous"] = (not refused and file_bytes > VACUOUS_BYTES and not sum(source.values())
                        and not any(chunk.get("not_read_reason") for chunk in chunks))
    found["file_bytes"] = file_bytes
    found["closed"] = found["unaccounted"] == 0 and found["injected"] == 0 and not found["vacuous"]
    return found

def account_lines(found):
    """The account of one file in the plain words an analyst reads on Model_Package_Info.
    Enforces: R10, R13"""
    lines = ["%d smallest pieces of text counted: %d kept in a unit, %d kept in a unit's other fields, "
             "%d read into another form, %d left out under a named rule, %d in a part that could not be read."
             % (found["atoms"], found["in unit text"], found["relocated"], found["rewritten"],
                found["declared drop"], found["not read"])]
    if found.get("vacuous"):
        lines.append("The file is %d KB and yielded no text at all, and no reader said it could not read it: "
                     "it has probably not been opened. Check the file itself." % max(1, found["file_bytes"] // 1024))
    if found.get("held as text only"):
        lines.append("%d of the lines inside a unit are held only as running text, in files the tool could not read as "
                     "code, data or a help page: they are kept, and nothing in them can be linked or checked."
                     % found["held as text only"])
    if found["closed"]:
        lines.append("Content account closed: nothing was lost and nothing was added.")
    if found["unaccounted"]:
        lines.append("%d piece(s) of text were read from the file but are in no unit and under no rule, "
                     "first at: %s." % (found["unaccounted"], "; ".join(found["where unaccounted"][:3]) or "not located"))
    if found["injected"]:
        lines.append("%d piece(s) of text are shown in a unit but were not found in the file: %s."
                     % (found["injected"], ", ".join(found["what injected"][:6])))
    return lines


def account_of_package(files, units, refused, is_text_file):
    """The content account of a package tarball. The atom of a package is a line: every
    non-blank line of every member that holds text has to lie inside a unit, be refused with a
    reason, or be named as not read. A member the tool cannot read as text (a compiled object, a
    picture, stored data in a binary form) is counted as one atom of its own, because its lines
    cannot be counted without reading it. Extends the line coverage that read-package already
    kept for parsed R files to every member of the tarball. Enforces: R13"""
    inside, not_read, atoms, unaccounted, fenced, text_only = 0, 0, 0, [], 0, 0
    covered = {}
    for unit in units:
        lines = unit.get("lines")
        if unit.get("file") and lines:
            covered.setdefault(unit["file"], set()).update(range(int(lines[0]), int(lines[1]) + 1))
    for path in sorted(files):
        if not is_text_file(path):
            atoms += 1
            if any(unit.get("file") == path for unit in units):
                inside += 1
            else:
                not_read += 1
            continue
        try:
            lines = files[path].decode("utf-8", "replace").split("\n")
        except Exception:
            atoms += 1
            not_read += 1
            continue
        numbers = [number for number, line in enumerate(lines, start=1) if line.strip()]
        # A fence that opens or closes a block of code in a vignette separates content from
        # content and says nothing itself. It is a declared drop, named here, rather than a
        # line that lies in no unit for no stated reason. Enforces: R13
        fences = {number for number in numbers if lines[number - 1].strip().startswith("```")}
        numbers = [number for number in numbers if number not in fences]
        atoms += len(numbers) + len(fences)
        fenced += len(fences)
        held = covered.get(path, set())
        whole_file = any(unit.get("file") == path and not unit.get("lines") for unit in units)
        if any(unit.get("file") == path and unit.get("kind") == "Other file" for unit in units):
            text_only += len(numbers)
        for number in numbers:
            if number in held or whole_file:
                inside += 1
            elif any(unit.get("file") == path and unit.get("read_problem") for unit in units):
                not_read += 1
            else:
                unaccounted.append("%s line %d" % (path, number))
    found = {"file": "the package", "atoms": atoms + len(refused), "in unit text": inside, "relocated": 0,
             "rewritten": 0, "declared drop": len(refused) + fenced, "not read": not_read,
             "unaccounted": len(unaccounted), "injected": 0, "where unaccounted": sorted(unaccounted)[:12],
             "what unaccounted": [], "what injected": [], "held as text only": text_only}
    found["closed"] = found["unaccounted"] == 0
    return found


# ---------------------------------------------------------------- the shape digest and the rules it asks for
# What a model is shown about a file it must help slice: its STRUCTURE and a few short samples,
# never the file. The digest is built by code from plain facts, is bounded, and is recorded, so
# a reviewer can see exactly what was put in front of the model. Enforces: R3, R7

DIGEST_SAMPLE_CHARS = 120
DIGEST_SAMPLES = 3
# The families a PROPOSAL may use, and why it is only these five. Each keeps the words of the
# element it is given to wherever that element sits: a heading's text goes into the chain of
# everything below it and, where nothing sits below it, into a unit of its own; a paragraph's
# and a list item's into a unit; a container's children are walked.
#
# The families left out fall into two groups. Table, row, cell, header_cell, caption, figure
# and equation rest on counting the shape of the file rather than on anybody's opinion, and
# their readers may put text somewhere other than a unit or drop it where a shape does not hold
# up. "inline" is left out for a different reason, and the property test found it rather than
# anyone reasoning it out: an inline mark keeps its words only when it sits inside something
# that has running text, so the same answer is safe in one place and loses words in another.
# A family whose safety depends on where a tag sits is not a family a proposal may give.
# This is what makes "no answer can lose a word" true by construction rather than by hope.
# Enforces: R13
SLICE_FAMILIES = ("heading", "container", "paragraph", "list_container", "list_item")

def walk_with_depth(element, depth):
    """Every element under one element, with how deep it sits."""
    yield depth, element
    for child in element:
        for found in walk_with_depth(child, depth + 1):
            yield found

def digest_row(row):
    """One tag's behaviour, cut to what a prompt can carry."""
    lengths = row["text_lengths"]
    return {"tag": row["tag"], "count": row["count"],
            "depth": "%d-%d" % (min(row["depths"]), max(row["depths"])),
            "inside": sorted(row["inside"])[:6], "holds": sorted(row["holds"])[:8],
            "with_text": row["with_text"], "mean_text": int(sum(lengths) / len(lengths)) if lengths else 0,
            "attributes": sorted(row["attributes"])[:6], "first_child": row["first_child"],
            "known_as": row["known_as"] or "", "guessed_as": row["guessed_as"], "samples": row["samples"]}

def markup_digest(root, rules, file_name):
    """One row per tag the file uses, with how it behaves here: how often it occurs, how deep it
    sits, what it sits inside and what sits inside it, how often it carries text of its own, how
    long that text runs, what attributes it has, how often it is the first child, and three
    short samples. A tag the rules already name is marked as known, so that a proposal can be
    told from a repetition of what the tool already does. Enforces: R7"""
    # What the tool ships or the analyst wrote is KNOWN and is not the model's business. What
    # discovery worked out on the spot is a GUESS, and saying which is which is the whole point:
    # a proposal is wanted exactly where code guessed, and nowhere else.
    settled = set(rules.get("shipped_tags") or ()) | set(rules.get("analyst_tags") or ())
    families, rows, order = rules.get("family_of", {}), {}, []
    parents = {id(child): element for element in root.iter() for child in element}
    for depth, element in walk_with_depth(root, 0):
        name = local_name(element.tag)
        if not name:
            continue
        row = rows.get(name)
        if row is None:
            row = rows[name] = {"tag": name, "count": 0, "depths": set(), "inside": set(), "holds": set(),
                                "with_text": 0, "text_lengths": [], "attributes": set(), "first_child": 0,
                                "samples": [], "known_as": "", "guessed_as": ""}
            family = families.get(name) or ""
            # Settled: what the tool ships, what the analyst wrote, and what discovery PROVED by
            # counting the rows. A guess is only what discovery's fallback net produced, and a
            # guess is the only thing a proposal is wanted about.
            if name in settled or family in PROVEN_BY_SHAPE:
                row["known_as"] = family
            else:
                row["guessed_as"] = family
            order.append(name)
        row["count"] += 1
        row["depths"].add(depth)
        parent = parents.get(id(element))
        if parent is not None:
            row["inside"].add(local_name(parent.tag))
            if len(parent) and parent[0] is element:
                row["first_child"] += 1
        row["holds"].update(local_name(child.tag) for child in element if local_name(child.tag))
        row["attributes"].update(local_name(key) for key in element.attrib)
        own = normalise_text(element.text or "")
        if own:
            row["with_text"] += 1
            row["text_lengths"].append(len(own))
            if len(row["samples"]) < DIGEST_SAMPLES:
                row["samples"].append(own[:DIGEST_SAMPLE_CHARS])
    return {"file": file_name, "kind": "markup", "tags": [digest_row(rows[name]) for name in order]}

def digest_text(digest):
    """The digest as the lines a prompt shows. Structure only: counts, places and short samples."""
    lines = []
    for row in digest["tags"]:
        parts = ["<%s> x%d depth %s" % (row["tag"], row["count"], row["depth"])]
        if row["known_as"]:
            parts.append("ALREADY READ AS: %s" % row["known_as"])
        elif row["guessed_as"]:
            parts.append("GUESSED AS: %s" % row["guessed_as"])
        if row["inside"]:
            parts.append("inside: %s" % ", ".join(row["inside"]))
        if row["holds"]:
            parts.append("holds: %s" % ", ".join(row["holds"]))
        parts.append("has own text %d of %d times, averaging %d characters" % (row["with_text"], row["count"], row["mean_text"]))
        if row["first_child"]:
            parts.append("is the first child %d times" % row["first_child"])
        if row["attributes"]:
            parts.append("attributes: %s" % ", ".join(row["attributes"]))
        lines.append(" | ".join(parts))
        for sample in row["samples"]:
            lines.append("    sample: %s" % sample)
    return "\n".join(lines)

def slice_rules_question(digest, rules, prompt, settings):
    """One question about the shape of one file. The reader's own procedure and prohibitions are
    the first thing in the prompt's system half, so what the reader is contracted to do is what the
    model is told to do, and a changed contract is a new prompt version and a new question.
    Enforces: R3, R5"""
    system = prompt["system"].strip()
    main = prompt["main"].replace("[[UNIT]]", digest_text(digest))
    return {"question_type": "slice-rules", "unit_ref": digest["file"], "system_prompt": system,
            "main_prompt": main, "letters": {}, "planted": [], "passage_texts": {}, "unit_text": "",
            "strip_patterns": list(settings["strip_patterns"]),
            "tags_shown": [row["tag"] for row in digest["tags"]],
            "holds_other_tags": {row["tag"]: bool(row["holds"]) for row in digest["tags"]},
            "estimated_tokens": estimate_tokens(main),
            "too_large": estimate_tokens(main) > prompt_budget(settings, system),
            "question_id": sha256_text(prompt["version"] + "\n" + system + "\n" + main)}

def validate_slice_rules(question, answer, rejected):
    """The answer is a choice among things code has already put in front of the model: a tag it
    was shown, a family from the fixed list, a depth from 1 to 9. There is no field through
    which prose can reach a unit, so a wrong answer can mislabel a tag and can never add a word
    to a document or take one out of it. "ignore" is refused outright, because it is the one
    family that would let an answer lose content. Enforces: R3, R7, R13"""
    shown = set(question["tags_shown"])
    families = answer.get("families")
    if not isinstance(families, dict) or not families:
        raise rejected(REJECTION_REASONS[0])
    holds = question.get("holds_other_tags") or {}
    for tag, family in families.items():
        if tag not in shown:
            raise rejected(REJECTION_REASONS[1])
        if family == "ignore" or family not in SLICE_FAMILIES:
            raise rejected(REJECTION_REASONS[0])
        # A tag that holds other tags is not a paragraph, an item or an inline mark. Reading it
        # as one would take the words of everything inside it into a unit AND read those things
        # again below, so the document would say twice what it says once. Code counted what each
        # tag holds; a proposal does not get to contradict the count. Enforces: R13
        if holds.get(tag) and family in ("paragraph", "list_item"):
            raise rejected(REJECTION_REASONS[4])
    levels = answer.get("levels") or {}
    if not isinstance(levels, dict):
        raise rejected(REJECTION_REASONS[0])
    for tag, level in levels.items():
        if tag not in shown or families.get(tag) != "heading":
            raise rejected(REJECTION_REASONS[1])
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 9:
            raise rejected(REJECTION_REASONS[0])
    why = answer.get("why") or {}
    if not isinstance(why, dict) or any(tag not in shown for tag in why):
        raise rejected(REJECTION_REASONS[1])

# Families discovery does not guess at: it counts the widths of the rows and refuses to call
# something a table unless the counting holds up. A proposal may not overturn them.
PROVEN_BY_SHAPE = ("table", "table_part", "row", "header_cell", "cell")

def overlay_from_answer(answer, rules, analyst_tags, discovered=None):
    """The answer as an overlay on the tag rules, in the one order that matters:

        what the ANALYST wrote in Inputs/tag_rules.yaml   wins over
        what the tool SHIPS                                   wins over
        what discovery PROVED by counting the shape       wins over
        what the MODEL proposes                           wins over
        what discovery GUESSED with its fallback net

    So the model never overrides a person, never overrides a schema the tool already knows, and
    never overrides a table whose rows were counted. It speaks where code only guessed, which
    is exactly where the reading was weak. Returns (families to apply, levels, why)."""
    shipped, discovered = set(rules.get("shipped_tags") or ()), discovered or {}
    families, levels, why = {}, {}, {}
    for tag, family in (answer.get("families") or {}).items():
        if tag in analyst_tags or tag in shipped or discovered.get(tag) in PROVEN_BY_SHAPE:
            continue
        families[tag] = family
        if family == "heading" and tag in (answer.get("levels") or {}):
            levels[tag] = answer["levels"][tag]
        if tag in (answer.get("why") or {}):
            why[tag] = answer["why"][tag]
    return families, levels, why

# ---------------------------------------------------------------- asking about the shape of a file
def reading_doubts(root, state, discovered):
    """Where the built-in rules themselves say they are unsure. Only these ask a question; a
    file the rules read confidently costs no call at all and comes out exactly as before."""
    doubts = []
    if state.unknown_tags:
        doubts.append("%d tag(s) are not named by the rules" % len(state.unknown_tags))
    headings = [tag for tag, family in state.rules["family_of"].items() if family == "heading"]
    if discovered and not headings:
        doubts.append("the file has a shape the rules do not know and no tag in it is read as a heading")
    return doubts

def guided_rules(root, file_name, state, discovered):
    """Ask the model what the tags of an unfamiliar file are for, and apply what it says.

    Nothing here can add a word to a document or take one out of it: the answer is a choice
    among tags code has already shown and families from a fixed list, and it is refused if it
    names anything else. A refused, failed or absent answer leaves the built-in reading exactly
    as it was, so the worst case is the reader without guidance. Enforces: R3, R13"""
    if state.ask is None or state.settings.get("agentic_reading") == "off":
        return
    if not reading_doubts(root, state, discovered):
        return
    digest = markup_digest(root, state.rules, file_name)
    state.digests.append(digest)
    prompt = load_prompt("slice-rules")
    question = slice_rules_question(digest, state.rules, prompt, state.settings)
    if question["too_large"]:
        state.notes.append("%s: its shape is too large to ask about, so the built-in rules read it." % file_name)
        return
    found = state.ask([question]).get(question["question_id"])
    answer = (found or {}).get("answer")
    if not answer:
        state.notes.append("%s: read by the built-in rules; a guided reading was not available." % file_name)
        return
    families, levels, why = overlay_from_answer(answer, state.rules, set(state.rules.get("analyst_tags") or ()), discovered)
    changed = {tag: family for tag, family in families.items() if discovered.get(tag) != family}
    state.rules["family_of"].update(families)
    state.guided.update(families)
    for tag in sorted(changed):
        state.notes.append("%s: <%s> read as %s on the model's proposal, where the built-in rules read it as %s%s"
                           % (file_name, tag, changed[tag], discovered.get(tag) or "nothing in particular",
                              " (%s)" % why[tag] if tag in why else ""))


# ---------------------------------------------------------------- asking how to read a package
# A tarball laid out in an unusual way loses content in a quieter way than a document does: a
# file of R code under inst/ rather than R/ is not parsed, and its two thousand first characters
# become one unit of running text while the rest of it reaches nothing. The question here picks
# WHICH EXISTING READER takes a member. It never touches the R tokenizer, the parser, the
# expression trees or the decoder of stored data: a model's reading of code is an assertion
# ABOUT the code, not a parse OF it. Enforces: R7, R13

PACKAGE_READERS = ("r-source", "r-data", "help-page", "vignette", "table-file", "prose")
MANIFEST_SAMPLE_LINES = 5

def manifest_digest(files, placed, decode, package_name=""):
    """Every member of the tarball: where it lies, how large it is, and which reader the
    built-in tests give it. A member they give none is shown with its first few lines, because
    that is what tells a reader of R code from a licence. Nothing else of the file is shown."""
    rows = []
    for path in sorted(files):
        data = files[path]
        row = {"path": path, "bytes": len(data), "extension": os.path.splitext(path)[1].lower(),
               "folder": path.split("/")[0] if "/" in path else "", "placed_as": placed.get(path) or "", "first_lines": []}
        if not row["placed_as"]:
            text = decode(data)
            if text is not None:
                row["first_lines"] = [line[:120] for line in text.split("\n")[:MANIFEST_SAMPLE_LINES] if line.strip()]
        rows.append(row)
    return {"file": package_name or "the package", "kind": "package", "members": rows}

def manifest_text(digest):
    """The manifest as the lines a prompt shows."""
    lines = []
    for row in digest["members"]:
        parts = ["%s (%d bytes)" % (row["path"], row["bytes"])]
        if row["placed_as"]:
            parts.append("ALREADY READ AS: %s" % row["placed_as"])
        else:
            parts.append("NOT PLACED: the built-in tests give it no reader")
        lines.append(" | ".join(parts))
        for sample in row["first_lines"]:
            lines.append("    line: %s" % sample)
    return "\n".join(lines)

def package_plan_question(digest, prompt, settings):
    """One question about one tarball, asked only where members were left unplaced."""
    system = prompt["system"].strip()
    main = prompt["main"].replace("[[UNIT]]", manifest_text(digest))
    unplaced = [row["path"] for row in digest["members"] if not row["placed_as"]]
    return {"question_type": "package-plan", "unit_ref": digest["file"], "system_prompt": system,
            "main_prompt": main, "letters": {}, "planted": [], "passage_texts": {}, "unit_text": "",
            "strip_patterns": list(settings["strip_patterns"]), "unplaced": unplaced,
            "estimated_tokens": estimate_tokens(main),
            "too_large": estimate_tokens(main) > prompt_budget(settings, system),
            "question_id": sha256_text(prompt["version"] + "\n" + system + "\n" + main)}

def validate_package_plan(question, answer, rejected):
    """A reader for every member left unplaced, each named from the fixed list, and for no other
    member. There is no reader that means "skip": a member the tool cannot make sense of becomes a
    unit that says so, never a gap. Enforces: R3, R13"""
    unplaced = set(question["unplaced"])
    readers = answer.get("readers")
    if not isinstance(readers, dict) or not readers:
        raise rejected(REJECTION_REASONS[0])
    for path, reader in readers.items():
        if path not in unplaced:
            raise rejected(REJECTION_REASONS[1])
        if reader not in PACKAGE_READERS:
            raise rejected(REJECTION_REASONS[0])
    missing = unplaced - set(readers)
    if missing:
        raise rejected(REJECTION_REASONS[4])
    why = answer.get("why") or {}
    if not isinstance(why, dict) or any(path not in unplaced for path in why):
        raise rejected(REJECTION_REASONS[1])


# ================================================================================================
# ---------------------------------------------------------------- from verifier1f_formats
# ---------------------------------------------------------------- what a file is
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*", b"RIFF")
MARKDOWN_NAMES = (".md", ".markdown", ".mdown", ".mkd")
DELIMITED_NAMES = (".csv", ".tsv", ".tab")
LATEX_NAMES = (".tex", ".ltx")

# A format the tool does not read, what it is in plain words, and what to do about it.
NOT_READ = {
    "pptx": "a slide deck, which the tool does not read; save it as PDF and put the PDF in its place",
    "odf": "an OpenDocument file, which the tool does not read; save it as .docx and put that in its place",
    "epub": "an e-book, which the tool does not read; save it as PDF and put the PDF in its place",
    "zip": "an archive of other files; unpack it into the folder so that each file is read on its own",
    "gzip": "a compressed file; unpack it into the folder so that the file inside it is read",
    "ole": "in an old Microsoft Office format (.doc, .xls or .ppt), which the tool does not read; "
           "save it as .docx, .xlsx or PDF and put that in its place",
    "image": "a picture, and the tool does not read words from a picture on its own; if it holds text, "
             "save it as a PDF with a text layer",
    "binary": "binary data rather than a document",
}

# The name a format goes by in what the analyst reads.
FORMAT_NAMES = {"pdf": "PDF", "docx": "Word", "xlsx": "spreadsheet", "svg": "SVG picture", "mhtml": "web archive", "html": "web page",
                "xml": "XML", "markdown": "Markdown", "delimited": "delimited rows", "rtf": "RTF",
                "latex": "LaTeX", "text": "plain text"}

def looks_binary(data):
    """Bytes that are not text: a NUL byte, or more than one in ten bytes a control character."""
    head = data[:4096]
    if b"\x00" in head:
        return True
    control = sum(1 for byte in head if byte < 32 and byte not in (9, 10, 12, 13))
    return bool(head) and control * 10 > len(head)

def sniff_zip(data):
    """What a ZIP archive holds, which is what it is. Enforces: R6"""
    try:
        names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    except (zipfile.BadZipFile, OSError):
        return "binary"
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    if "content.xml" in names:
        return "odf"
    if "META-INF/container.xml" in names:
        return "epub"
    return "zip"

def detect_format(data, file_name=""):
    """The format of a file from its content, whatever its name says. For the three text formats
    whose content cannot be told apart for certain - Markdown, delimited rows and LaTeX - the name
    is taken as a hint and the content has to agree with it. Enforces: R6"""
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        return sniff_zip(data)
    if data.startswith(OLE_MAGIC):
        return "ole"
    if head.startswith(b"{\\rtf"):
        return "rtf"
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if data.startswith(IMAGE_MAGIC):
        return "image"
    if looks_binary(data):
        return "binary"
    lowered, name = head.lower(), file_name.lower()
    if name.endswith(MARKDOWN_NAMES):
        return "markdown"                            # Markdown may open with an HTML comment or table; the name decides
    if lowered.startswith((b"mime-version:", b"from:", b"content-type:")) or b"multipart/related" in lowered[:1024]:
        return "mhtml"
    if lowered.startswith(b"<"):
        if re.match(rb"<(!doctype\s+html|html)\b", lowered):
            return "html"
        if re.search(rb"<svg[\s>]", lowered[:4096]) and not re.search(rb"<(body|para|section|document|p)\b", lowered[:4096]):
            return "svg"
        return "xml"
    sample = decode_text(data[:16384])
    if name.endswith(LATEX_NAMES) and re.search(r"\\[a-zA-Z]+", sample) or re.search(r"\\documentclass|\\begin\{document\}", sample):
        return "latex"
    if len(re.findall(r"(?m)^#{1,6} \S", sample)) >= 2:
        return "markdown"
    if name.endswith(DELIMITED_NAMES) and delimiter_of(sample):
        return "delimited"
    return "text"

def decode_text(data):
    """Bytes to text: a byte-order mark or a declared encoding decides, then UTF-8, then Latin-1."""
    declared = re.search(rb'(?:encoding|charset)=["\']?([\w-]+)', data[:2048])
    for encoding in ([declared.group(1).decode("ascii")] if declared else []) + ["utf-8-sig", "utf-8"]:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1")

# ---------------------------------------------------------------- which files of a folder are documents
LEFT_BEHIND = re.compile(r"^(~\$.*|\.~lock\..*#|thumbs\.db|desktop\.ini|ehthumbs\.db|.*\.tmp|.*\.bak|.*\.swp|\.ds_store)$", re.I)

def input_files(folder):
    """The documents of one Inputs corner, walking into its folders, in a fixed order; and every
    file left out, with why. An operating system's and an editor's leavings (a Word lock file,
    Thumbs.db) are left out, and so is the support folder a browser writes beside a saved web
    page, whose pictures and style sheets are part of the page and not documents of their own.
    Nothing is left out without being named. Enforces: R2"""
    found, skipped = [], []
    if not os.path.isdir(folder):
        return found, skipped
    for root, folders, names in os.walk(folder):
        pages = {os.path.splitext(name)[0].lower() for name in names if name.lower().endswith((".htm", ".html", ".mht", ".mhtml"))}
        for inner in sorted(folders):
            stem = re.sub(r"(_files|\.files|-files)$", "", inner, flags=re.I).lower()
            if stem != inner.lower() and stem in pages:
                skipped.append((os.path.relpath(os.path.join(root, inner), folder), "the support folder of a saved web page"))
        folders[:] = sorted(inner for inner in folders if not inner.startswith((".", "__"))
                            and not (re.sub(r"(_files|\.files|-files)$", "", inner, flags=re.I).lower() in pages
                                     and re.search(r"(_files|\.files|-files)$", inner, re.I)))
        for name in sorted(names):
            relative = os.path.relpath(os.path.join(root, name), folder)
            if name == "README.txt" and root == folder:
                continue
            if name.startswith(".") or LEFT_BEHIND.match(name):
                skipped.append((relative, "a file an operating system or an editor leaves behind"))
            else:
                found.append(os.path.join(root, name))
    return sorted(found, key=lambda path: os.path.relpath(path, folder).lower()), sorted(skipped)

# ---------------------------------------------------------------- formats the tool reads by converting them
# Each converter returns (markup, words): the markup is what the walker reads, and the words are
# the file with its syntax taken away by a rule named here, which is what the content account
# counts. The two are made by DIFFERENT code - the markup by reading the structure, the words by
# removing syntax - so that the account still sees the walker lose or add a word. It does trust
# the syntax rule, and says so. Enforces: R13

def element(tag, text):
    """One element of markup, its text escaped so that a < in a document is never a tag."""
    return "<%s>%s</%s>" % (tag, escape(text), tag)

def markdown_inline(text):
    """A line of Markdown without its inline marks: emphasis, code marks, and the target of a link
    or a picture, whose words are kept and whose address is not what the document says."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])", r"\1", text)
    return text.replace("`", "")

TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
LIST_MARK = re.compile(r"^\s*([-*+]|\d+[.)])\s+")

HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)

def markdown_to_markup(text):
    """Markdown as markup: # headings, paragraphs, lists, tables, fenced code and quotations. An
    HTML comment is left out by the same rule in the markup and in the words: it is a note to
    whoever edits the file, not what the document says."""
    text = HTML_COMMENT.sub("", text)
    out, paragraph, rows, fenced, items = [], [], [], None, []
    def flush():
        if paragraph:
            out.append(element("p", " ".join(paragraph)))
            paragraph.clear()
        if items:
            out.append("<ul>%s</ul>" % "".join(element("li", item) for item in items))
            items.clear()
        if rows:
            cells = [[markdown_inline(cell.strip()) for cell in row.strip().strip("|").split("|")] for row in rows]
            out.append("<table>%s</table>" % "".join(
                "<tr>%s</tr>" % "".join(element("th" if number == 0 else "td", cell) for cell in row)
                for number, row in enumerate(cells)))
            rows.clear()
    lines = text.split("\n")
    for position, line in enumerate(lines):
        if fenced is not None:
            if line.strip().startswith("```") or line.strip().startswith("~~~"):
                out.append(element("pre", "\n".join(fenced)))
                fenced = None
            else:
                fenced.append(line)
            continue
        if line.strip().startswith(("```", "~~~")):
            flush()
            fenced = []
            continue
        heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        underline = position + 1 < len(lines) and re.match(r"^(=+|-+)\s*$", lines[position + 1]) and line.strip() and not rows
        if heading or underline:
            flush()
            level = len(heading.group(1)) if heading else (1 if lines[position + 1].strip()[0] == "=" else 2)
            out.append(element("h%d" % min(level, 4), markdown_inline((heading.group(2) if heading else line).strip())))
            continue
        if re.match(r"^(=+|-+)\s*$", line) and position and out and out[-1].startswith("<h"):
            continue                                 # the underline of a heading already read
        if "|" in line and (rows or position + 1 < len(lines) and TABLE_RULE.match(lines[position + 1])):
            if not rows:
                flush()
            if not TABLE_RULE.match(line):
                rows.append(line)
            continue
        if LIST_MARK.match(line):
            if paragraph or rows:
                flush()
            items.append(markdown_inline(LIST_MARK.sub("", line).strip()))
            continue
        if not line.strip():
            flush()
            continue
        if items and line.startswith((" ", "\t")):
            items[-1] += " " + markdown_inline(line.strip())
            continue
        if rows or items:
            flush()
        paragraph.append(markdown_inline(re.sub(r"^\s*>\s?", "", line).strip()))
    if fenced is not None:
        out.append(element("pre", "\n".join(fenced)))
    flush()
    return "<document>%s</document>" % "".join(out)

def markdown_words(text):
    """The words of a Markdown file, with its syntax taken away by rule rather than by reading its
    structure: heading marks, list marks, table rules and bars, fence lines, quotation marks."""
    kept = []
    for line in HTML_COMMENT.sub("", text).split("\n"):
        if TABLE_RULE.match(line) or line.strip().startswith(("```", "~~~")) or re.match(r"^(=+|-+)\s*$", line):
            continue
        line = re.sub(r"^\s*#{1,6}\s+|\s+#+\s*$", " ", line)
        line = LIST_MARK.sub(" ", line)
        line = re.sub(r"^\s*>\s?", " ", line)
        kept.append(markdown_inline(line.replace("|", " ")))
    return "\n".join(kept)

def delimiter_of(text):
    """The separator of a file of delimited rows, where the first rows agree on one."""
    rows = [line for line in text.split("\n") if line.strip()][:6]
    if len(rows) < 2:
        return ""
    for separator in ("\t", ",", ";", "|"):
        counts = {row.count(separator) for row in rows}
        if len(counts) == 1 and counts.pop() >= 1:
            return separator
    return ""

def delimited_rows(text):
    """The rows of a file of delimited values, read by the rules of that format."""
    separator = delimiter_of(text) or ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=separator) if any(cell.strip() for cell in row)]

def delimited_to_markup(text, file_name):
    """Rows of values as a table, the first row naming the columns."""
    rows = delimited_rows(text)
    body = "".join("<tr>%s</tr>" % "".join(element("th" if number == 0 else "td", cell.strip()) for cell in row)
                   for number, row in enumerate(rows))
    return "<document><table><caption>%s</caption>%s</table></document>" % (escape(os.path.basename(file_name)), body)

def delimited_words(text, file_name):
    """The words of a file of delimited values: its name, which heads its table, and its cells."""
    return os.path.basename(file_name) + "\n" + "\n".join(" ".join(cell.strip() for cell in row) for row in delimited_rows(text))

def spreadsheet_to_markup(data):
    """A spreadsheet as one heading and one table for every sheet that holds anything. What a cell
    shows is its stored value: a formula is never worked out, only the value the spreadsheet saved
    with it is read. Enforces: R7"""
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts, words = [], []
    for sheet in book.worksheets:
        rows = [[("" if value is None else str(value)).strip() for value in row] for row in sheet.iter_rows(values_only=True)]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        parts.append(element("h1", sheet.title))
        parts.append("<table>%s</table>" % "".join(
            "<tr>%s</tr>" % "".join(element("th" if number == 0 else "td", cell) for cell in row)
            for number, row in enumerate(rows)))
        words.append(sheet.title)
        words.extend(" ".join(row) for row in rows)
    return "<document>%s</document>" % "".join(parts), "\n".join(words)

def rtf_to_text(text):
    """The words of an RTF file: its tables of fonts, colours and styles, its pictures and its
    control words taken away, a paragraph mark read as a new paragraph and an escaped character as
    that character."""
    text = re.sub(r"\{\\\*[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", text)
    for group in ("fonttbl", "colortbl", "stylesheet", "info", "pict", "listtable", "listoverridetable"):
        text = re.sub(r"\{\\%s[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}" % group, "", text)
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda found: bytes([int(found.group(1), 16)]).decode("cp1252", "replace"), text)
    text = re.sub(r"\\u(-?\d+)\??", lambda found: chr(int(found.group(1)) % 65536), text)
    text = re.sub(r"\\(par|line|sect|page)\b ?", "\n\n", text)
    text = re.sub(r"\\tab\b ?", " ", text)
    text = re.sub(r"\\([{}\\])", lambda found: "\x00" + found.group(1), text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "").replace("\x00", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()

LATEX_HEADINGS = (("part", 1), ("chapter", 1), ("section", 1), ("subsection", 2), ("subsubsection", 3), ("paragraph", 4))

def latex_body(text):
    """A LaTeX file without its comments and its preamble. What comes before \\begin{document} -
    the class of the document and the packages it loads - sets the document up and is not what it
    says, so it is left out by this rule, the same rule for the markup and for the words."""
    text = re.sub(r"(?<!\\)%.*", "", text)
    body = re.search(r"\\begin\{document\}(.*?)(\\end\{document\}|$)", text, re.S)
    return body.group(1) if body else text

def latex_words(text, whole=True):
    """The words of a LaTeX file: comments, environments and the names of commands taken away,
    the arguments of a command kept. Mathematics is kept as its words and symbols; it is not read
    as an equation here."""
    text = latex_body(text) if whole else text
    text = re.sub(r"\\(begin|end)\{[^}]*\}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", text)
    return re.sub(r"[{}$]", " ", text).replace("\\\\", " ")

def latex_to_markup(text):
    """LaTeX as markup: its sectioning commands as headings, its items as a list, and everything
    between as paragraphs of its words."""
    text = latex_body(text)
    pattern = r"\\(%s)\*?\{([^}]*)\}" % "|".join(name for name, _ in LATEX_HEADINGS)
    levels, out, cursor = dict(LATEX_HEADINGS), [], 0
    for found in list(re.finditer(pattern, text)) + [None]:
        chunk = text[cursor:found.start() if found else len(text)]
        for part in re.split(r"\n\s*\n", chunk):
            items = re.split(r"\\item\b", part)
            lead = latex_words(items[0], whole=False).strip()
            if lead:
                out.append(element("p", re.sub(r"\s+", " ", lead)))
            if len(items) > 1:
                out.append("<ul>%s</ul>" % "".join(element("li", re.sub(r"\s+", " ", latex_words(item, whole=False)).strip())
                                                  for item in items[1:] if latex_words(item, whole=False).strip()))
        if found:
            out.append(element("h%d" % levels[found.group(1)], re.sub(r"\s+", " ", latex_words(found.group(2), whole=False)).strip()))
            cursor = found.end()
    return "<document>%s</document>" % "".join(out)


SVG_NS = "http://www.w3.org/2000/svg"

def svg_texts(root):
    """Every piece of text an SVG holds as text, with where it is drawn: (x, y, text). Three places:
    a <text> (its <tspan>s split it only where they carry positions of their own; a <textPath> or an
    <a> inside it is read with it); and a <foreignObject>, where drawing tools put HTML - divs and
    paragraphs - instead of SVG text. A transform is not applied, so a moved group keeps the order
    it was written in."""
    found = []
    def number(value, fallback=0.0):
        try:
            return float(re.split(r"[ ,]", (value or "").strip())[0])
        except (ValueError, IndexError):
            return fallback
    for node in root.iter():
        name = local_name(node.tag)
        if name == "text":
            x, y = number(node.get("x")), number(node.get("y"))
            placed = [span for span in node.iter() if local_name(span.tag) == "tspan" and (span.get("x") or span.get("y") or span.get("dy"))]
            if not placed:
                words = normalise_text("".join(node.itertext()))
                if words:
                    found.append((x, y, words))
                continue
            lead = normalise_text(node.text or "")
            if lead:
                found.append((x, y, lead))
            line_y = y
            for span in placed:
                line_y = number(span.get("y"), line_y + number(span.get("dy"), 0.0))
                words = normalise_text("".join(span.itertext()))
                if words:
                    found.append((number(span.get("x"), x), line_y, words))
        elif name == "foreignobject":                    # local_name lower-cases: foreignObject
            words = normalise_text(" ".join(part for part in node.itertext() if part.strip()))
            if words:
                found.append((number(node.get("x")), number(node.get("y")), words))
    return found

def svg_embedded_pictures(root):
    """The raster pictures an SVG carries inside itself as data: URIs - what a chart exported as an
    image and wrapped in SVG looks like. Their words can only be read by OCR."""
    import base64
    pictures = []
    for node in root.iter():
        if local_name(node.tag) != "image":
            continue
        link = next((value for key, value in node.attrib.items() if local_name(key) == "href"), "")
        found = re.match(r"data:image/(png|jpe?g|gif|bmp|webp);base64,(.*)", link.strip(), re.S)
        if found:
            try:
                pictures.append(base64.b64decode(re.sub(r"\s", "", found.group(2))))
            except (ValueError, TypeError):
                continue
    return pictures

def svg_why_no_text(root):
    """Why an SVG gave no text, in words an analyst can act on. Enforces: R2"""
    if svg_embedded_pictures(root):
        return "the chart is a picture stored inside the SVG, so its words can only be read by OCR"
    glyphs = sum(1 for node in root.iter() if local_name(node.tag) == "use"
                 and any("glyph" in (value or "").lower() for key, value in node.attrib.items() if local_name(key) == "href"))
    shapes = sum(1 for node in root.iter() if local_name(node.tag) in ("path", "use"))
    if glyphs or shapes > 40:
        return ("its letters are drawn as shapes rather than stored as text, so they cannot be read as text; "
                "export the chart with its text kept as text, or add its data as a table in the methodology")
    return "it holds no text"

def svg_rows(texts, tolerance=None):
    """Texts grouped into rows by their y position, each row sorted by x. The tolerance is a
    share of the median line height, so a chart's labels and a table's cells both group."""
    if not texts:
        return []
    ys = sorted({round(y, 1) for _, y, _ in texts})
    gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a > 0.5]
    tolerance = tolerance or (max(2.0, sorted(gaps)[len(gaps) // 2] * 0.4) if gaps else 2.0)
    rows, current, last_y = [], [], None
    for x, y, words in sorted(texts, key=lambda t: (t[1], t[0])):
        if last_y is not None and y - last_y > tolerance:
            rows.append(sorted(current))
            current = []
        current.append((x, y, words))
        last_y = y
    if current:
        rows.append(sorted(current))
    return [[words for _, _, words in row] for row in rows]

def svg_to_markup(data, file_name):
    """An SVG as markup the walker reads: its <title> and <desc> as the caption; its text, where
    it stands in a grid of at least two rows of the same width, as a table with the first row
    as the header; otherwise as a figure whose words are the labels of the picture in reading
    order. An SVG holds text as text, so nothing is read from a picture by guesswork: every
    word comes from a <text> element. Enforces: R7, R13"""
    import xml.etree.ElementTree as ElementTree
    root = ElementTree.fromstring(data)
    caption = " ".join(normalise_text("".join(node.itertext())) for node in root
                       if local_name(node.tag) in ("title", "desc") and normalise_text("".join(node.itertext())))
    rows = svg_rows(svg_texts(root))
    widths = {len(row) for row in rows}
    words = [caption] + [" ".join(row) for row in rows]
    if len(rows) >= 2 and len(widths) == 1 and widths.pop() >= 2:
        body = "".join("<tr>%s</tr>" % "".join(element("th" if number == 0 else "td", cell) for cell in row)
                       for number, row in enumerate(rows))
        markup = "<document><table><caption>%s</caption>%s</table></document>" % (escape(caption or os.path.basename(file_name)), body)
        return markup, "\n".join(words), "a picture whose text stands in a grid, read as a table"
    labels = " ".join(" ".join(row) for row in rows)
    # no src: this markup IS the picture, so it must not send the reader looking for itself beside itself
    markup = "<document><figure alt=\"%s\"><caption>%s</caption></figure></document>" % (escape(labels), escape(caption))
    return markup, "\n".join(words), "a picture, read by its own text: %d label(s)" % sum(len(row) for row in rows)

def converted(found, data, file_name):
    """A file in a format read by converting it: (markup, words, what was done, in plain words)."""
    if found == "svg":
        return svg_to_markup(data, file_name)
    if found == "xlsx":
        markup, words = spreadsheet_to_markup(data)
        return markup, words, "read sheet by sheet, each sheet a heading over a table of its stored values"
    text = decode_text(data)
    if found == "markdown":
        return markdown_to_markup(text), markdown_words(text), "read as Markdown: its headings, lists and tables kept as such"
    if found == "delimited":
        return (delimited_to_markup(text, file_name), delimited_words(text, file_name),
                "read as a table of values, one row per line, the first line naming the columns")
    if found == "latex":
        return latex_to_markup(text), latex_words(text), "read as LaTeX: its sections as headings; its mathematics kept as words, not read as equations"
    plain = rtf_to_text(text)
    return ("<document>%s</document>" % "".join(element("p", part.strip()) for part in re.split(r"\n\s*\n", plain) if part.strip()),
            plain, "read as RTF: its control words, font tables and pictures left out")

CONVERTED = ("xlsx", "markdown", "delimited", "latex", "rtf", "svg")

def reason_for(problem):
    """Why a reader failed on a file, in words an analyst can act on. Enforces: R2"""
    name, said = type(problem).__name__, str(problem).lower()
    if isinstance(problem, IsADirectoryError):
        return "it is a folder, not a file"
    if isinstance(problem, PermissionError):
        return "the tool is not allowed to open it; check who may read the file"
    if "password" in said or "encrypt" in said or "decrypt" in said or "pdfminer" in name.lower():
        return "it is protected by a password; save an unprotected copy and put that in its place"
    if isinstance(problem, zipfile.BadZipFile) or name in ("ReadError", "CompressionError", "HeaderError", "EOFError"):
        return "it is damaged, or is not the archive its name says; save it again and put the new copy in its place"
    return "a reader failed on it (%s); the rest of the run went on without it" % name

# ---------------------------------------------------------------- the three Inputs folders of a project
INPUT_FOLDERS = (
    ("methodology", "1_Methodology", "Put the canonical methodology here: XML (also inside a .txt), .mhtml, .docx, "
     ".pdf, Markdown, .csv, .xlsx, .rtf or .tex. Folders are read too, in name order; anything the tool cannot read is named."),
    ("package", "2_Model_Package", "Put the R package here: its tarball (.tar.gz), a .zip of it, or its source folder."),
    ("documentation", "3_Model_Documentation", "Put the model documentation here (.docx is preferred; .pdf, .mhtml, "
     "XML, Markdown, .csv, .xlsx, .rtf and .tex are read too). Folders are read too, in name order."))

def list_input_files(inputs_dir):
    """The input files of a project, by corner, walking into folders; the folder each corner is
    read from, so that a file can be named by its path inside it; and every file each corner left
    out, with why. The optional glossary and tag rules sit beside the three folders. Enforces: R2"""
    inputs = {"glossary": None, "tag_rules": None, "roots": {}, "skipped": {}}
    for corner, folder, _ in INPUT_FOLDERS:
        inputs["roots"][corner] = os.path.join(inputs_dir, folder)
        inputs[corner], inputs["skipped"][corner] = input_files(inputs["roots"][corner])
    for key, name in (("glossary", "glossary.xlsx"), ("tag_rules", "tag_rules.yaml")):
        if os.path.exists(os.path.join(inputs_dir, name)):
            inputs[key] = os.path.join(inputs_dir, name)
    return inputs
