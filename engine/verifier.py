"""
Verifier 0.0.4 - verifier.py - the whole engine, in one file. For every reviewer.

Reads a model's methodology, its package of code and data, and its documentation; maps how the model
computes what it returns, from each final output down to its rawest inputs; links what corresponds;
checks by code whether linked formulas, values and stated rules agree; and raises what it could not line
up as questions for a person. One deliverable: Output.xlsx. Everything a run does is recorded, and a run
replays from its record without a model.

The file is one piece of engineering in four parts, in dependency order:
  the contracts, the reading floor and the front door
  reading the methodology, the documentation and the model package
  the map: how the model computes what it returns
  the run: its folder, its record and Output.xlsx
"""
import bz2
import csv
import dataclasses
import datetime
import email
import getpass
import gzip
import hashlib
import html.entities
import html.parser
import io
import json
import lzma
import os
import subprocess
import re
import shutil
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import unicodedata
import xml.etree.ElementTree as ElementTree
try:
    import yaml
except ImportError:                 # cell 1 imports the engine to install what is missing, yaml among them
    yaml = None
import zipfile
import zlib
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional
from xml.sax.saxutils import escape


# ================================================================================================
# the contracts, the reading floor and the front door
# ================================================================================================
# ---------------------------------------------------------------- the contracts: what every record is, and the words the tool may use
ENGINE_VERSION = "0.0.3"

# ---------------------------------------------------------------- vocabulary (Appendix B)

UNDECIDED_REASONS = ("the equation is an image", "the equation could not be read")   # why an equation was not read

KIND_FUNCTION, KIND_FORMULA, KIND_TOPLEVEL = "Function", "Formula statement", "Top-level statement"
KIND_TEST, KIND_TABLE, KIND_OBJECT = "Test block", "Parameter table", "Parameter object"
KIND_ROXYGEN, KIND_VIGNETTE = "Roxygen block", "Vignette text"
KIND_COMPILED, KIND_NOT_READ, KIND_OTHER = "Compiled code", "File not read", "Other file"
UNIT_KINDS = (KIND_FUNCTION, KIND_FORMULA, KIND_TOPLEVEL, KIND_TEST, KIND_TABLE, KIND_OBJECT,
              KIND_ROXYGEN, KIND_VIGNETTE, KIND_COMPILED, KIND_NOT_READ, KIND_OTHER)
CHUNK_KINDS = ("Paragraph", "Table", "Figure", "Equation")

# This one assignment has to name the words the tool may never use; nothing else in the engine may.
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
    header: tuple = (); rows: tuple = (); row_key: str = ""

@dataclass(frozen=True)
class EquationData:
    """An equation as found: its source form, whether the tool could read it, and its tree."""
    source_form: str = ""; linear: str = ""; readable: bool = False
    not_readable_reason: str = ""; image_sha256: str = ""

@dataclass(frozen=True)
class Chunk:
    """One citable unit of a document: a paragraph, a table, a figure or an equation."""
    ref: str; corner: str; source_file: str; kind: str; level: int; heading_chain: tuple
    numbering: str; text: str; locator: str; content_hash: str
    table: Optional[TableData] = None; equation: Optional[EquationData] = None
    numbering_reconstructed: bool = False
    caption: str = ""; not_read_reason: str = ""; para_label: str = ""   # para_label: the number the document itself gives ("36.")

@dataclass(frozen=True)
class CodeDetail:
    """What the R reader learned about a function or a statement, without running it."""
    formals: tuple = (); calls: tuple = (); symbols_written: tuple = (); exported: Optional[bool] = None
    reads_data: tuple = ()

@dataclass(frozen=True)
class ParameterDataDetail:
    """The profile of one stored data object."""
    object_name: str; container_file: str; dims: tuple = (); columns: tuple = ()
    assessable: bool = True; not_assessable_reason: Optional[str] = None

@dataclass(frozen=True)
class RoxygenDetail:
    """A roxygen block: what it documents, and its tags with their lines."""
    documents_ref: Optional[str] = None; documents_name: str = ""; tags: tuple = ()


@dataclass(frozen=True)
class ModelUnit:
    """One citable unit of the package (see UNIT_KINDS)."""
    ref: str; kind: str; file: str; lines: Optional[tuple]; name: str; inside: str; text: str
    parent_ref: Optional[str]; file_sha256: str; content_hash: str
    code: Optional[CodeDetail] = None; data: Optional[ParameterDataDetail] = None
    roxygen: Optional[RoxygenDetail] = None
    read_problem: Optional[str] = None

@dataclass(frozen=True)
class Provenance:
    """Which run and step produced a record, at which version, and from which AI exchange if any."""
    run_id: str; step_id: str; step: str; step_version: str; engine_version: str = ENGINE_VERSION
    prompt_hash: Optional[str] = None; response_hash: Optional[str] = None



@dataclass
class StepContext:
    """What every step function receives. It never contains the access token."""
    settings: dict; options: dict; read: Callable
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

# ---------------------------------------------------------------- the prompts
# Every question the tool asks, as the model sees it: a version line, the system half, the main half
# with [[UNIT]] and similar places the question builder fills. The text is exact - a question's id is
# the hash of its prompt, and recorded answers are found by that id - so a changed word here is a new
# version and asks new questions. Enforces: R3, R5, R9


# ---------------------------------------------------------------- element helpers
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

# ---------------------------------------------------------------- baseline slicing: what a document's shape says
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
    "whole file not read": ("not read", "a file in a format the tool does not read, named with its reason and a next step")}

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


def account_of_package(files, units, refused, is_text_file, dropped=()):
    """The content account of a package tarball. The atom of a package is a line: every
    non-blank line of every member that holds text has to lie inside a unit, be refused with a
    reason, or be named as not read. A member the tool cannot read as text (a compiled object, a
    picture, stored data in a binary form) is counted as one atom of its own, because its lines
    cannot be counted without reading it. Extends the line coverage that read-package already
    kept for parsed R files to every member of the tarball. A member left out on purpose (dropped: a help
    page, generated from the roxygen comments in the R files, which are read) is a declared drop, every
    line of it. Enforces: R13"""
    inside, not_read, atoms, unaccounted, fenced, text_only, declared = 0, 0, 0, [], 0, 0, 0
    covered = {}
    for unit in units:
        lines = unit.get("lines")
        if unit.get("file") and lines:
            covered.setdefault(unit["file"], set()).update(range(int(lines[0]), int(lines[1]) + 1))
    for path in sorted(files):
        if path in dropped:                           # not read on purpose, under a named rule
            lines = sum(1 for line in files[path].decode("utf-8", "replace").split("\n") if line.strip())
            atoms, declared = atoms + lines, declared + lines
            continue
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
             "rewritten": 0, "declared drop": len(refused) + fenced + declared, "not read": not_read,
             "unaccounted": len(unaccounted), "injected": 0, "where unaccounted": sorted(unaccounted)[:12],
             "what unaccounted": [], "what injected": [], "held as text only": text_only}
    found["closed"] = found["unaccounted"] == 0
    return found


# ---------------------------------------------------------------- the shape digest and the rules it asks for
# What a model is shown about a file it must help slice: its STRUCTURE and a few short samples,
# never the file. The digest is built by code from plain facts, is bounded, and is recorded, so
# a reviewer can see exactly what was put in front of the model. Enforces: R3, R7

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


# Families discovery does not guess at: it counts the widths of the rows and refuses to call
# something a table unless the counting holds up. A proposal may not overturn them.


# ---------------------------------------------------------------- asking how to read a package
# A tarball laid out in an unusual way loses content in a quieter way than a document does: a
# file of R code under inst/ rather than R/ is not parsed, and its two thousand first characters
# become one unit of running text while the rest of it reaches nothing. The question here picks
# WHICH EXISTING READER takes a member. It never touches the R tokenizer, the parser, the
# expression trees or the decoder of stored data: a model's reading of code is an assertion
# ABOUT the code, not a parse OF it. Enforces: R7, R13


# ================================================================================================
# ---------------------------------------------------------------- the reading floor

# ---------------------------------------------------------------- the front door: what a file is, and how it becomes markup

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
    "binary": "binary data rather than a document"}

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


# ================================================================================================
# reading the methodology, the documentation and the model package
# ================================================================================================
# ---------------------------------------------------------------- the methodology and the documentation, read into units
class NotReadable(Exception):
    """A formula or a file that the tool cannot read. The message is a plain reason for the analyst."""

# ---------------------------------------------------------------- the linear-notation parser
SUPERSCRIPTS = {"\u207b\u00b9": "^-1", "\u00b2": "^2", "\u00b3": "^3", "\u00b9": "^1"}
SIGNS = {"\u2212": "-", "\u00d7": "*", "\u00b7": "*", "\u22c5": "*", "\u2217": "*", "\u00f7": "/",
         "\u2264": "<=", "\u2265": ">=", "**": "^", "\u2061": "", "\u2062": "*", "\u2009": " "}
_TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?P<percent>\s?%)?"
    r"|(?P<name>[^\W\d_][\w]*(?:\.[^\W\d_]\w*)*(?:_\{[^{}]+\}|\[[^\[\]]+\])?)"
    r"|(?P<sign><=|>=|[-+*/^(),=<>\u221a]))")

# ---------------------------------------------------------------- reference data of the reader
# The tag rules: which tag of a document is what (heading, paragraph, table, ...), the numbering
# schemes. An analyst's Inputs/tag_rules.yaml is laid
# over these for one project and always wins. Kept as YAML text and parsed on every call, so that a
# caller that changes the rules it was given changes only its own copy. Enforces: R9
TAG_RULES_YAML = r'''# tag_rules.yaml - which tag belongs to which family when the tool reads XML or HTML.
# Reviewer 1 owns this file. A project can override any part of it with Inputs/tag_rules.yaml
# (same layout; a family given there replaces the family given here).
# Tag names are compared in lower case and without their namespace prefix.
# A tag that is in no family is read as a paragraph (or, when it only wraps other blocks,
# as a container) and is reported on Model_Package_Info, so that it can be added here.
families:
  heading:        [h1, h2, h3, h4, h5, h6, title, heading, head-line, sectiontitle]
  container:      [html, body, div, section, sect, sect1, sect2, sect3, sect4, sect5, chapter, part,
                   article, document, doc, annex, appendix, subsection, subsubsection, main, document-root]
  paragraph:      [p, para, paragraph, text, blockquote, pre, dd, dt]
  list_container: [ul, ol, list, itemizedlist, orderedlist, dl]
  list_item:      [li, item, listitem]
  table:          [table, informaltable, tbl]
  table_part:     [thead, tbody, tfoot, tgroup, colgroup, col]
  row:            [tr, row]
  header_cell:    [th]
  cell:           [td, entry, cell]
  figure:         [img, image, figure, graphic, mediaobject, svg, object, chart, imagedata]
  equation:       [math, equation, omath, omathpara, formula, informalequation]
  caption:        [caption, figcaption, legend]
  inline:         [a, b, i, u, em, strong, span, font, sub, sup, br, code, tt, small, big, emphasis, xref, o:p]
  ignore:         [head, script, style, meta, link, toc, index, nav, xml]
# Attributes that hold the numbering of a heading as written ("3.1").
numbering_attributes: [number, num, label, n]
# Numbering schemes, tried in this order. The first one that matches the start of a heading
# names its scheme. "dotted" numbers give their depth directly; every other scheme gets the
# level at which it first appeared (one deeper than the heading before it).
numbering_schemes:
  - {name: annex,          pattern: '^(?:Annex|Appendix|Annexe|Anhang)\s+([A-Z0-9]+)[.:]?(?=\s|$)'}
  - {name: dotted,         pattern: '^(\d+(?:\.\d+)+)\.?(?=\s|$)'}
  - {name: number,         pattern: '^(\d+)[.)]?(?=\s|$)'}
  - {name: upper_roman,    pattern: '^([IVXLC]+)\.(?=\s|$)'}
  - {name: upper_letter,   pattern: '^([A-Z])[.)](?=\s|$)'}
  - {name: bracket_roman,  pattern: '^\(([ivxlc]+)\)(?=\s|$)'}
  - {name: bracket_letter, pattern: '^\(([a-z])\)(?=\s|$)'}
# Words that start a cross-reference as written ("see Table 3", "section 4.2").
cross_reference_labels: [Table, Figure, Section, Sections, Equation, Annex, Appendix, Paragraph, Chapter]
'''

# The notation of R's mathematical functions: how each is written in the tool's linear notation and
# which of its arguments are the operands. Shared with review.py, which reads it for its word lists.
R_FUNCTION_MAP_YAML = r'''# r_function_map.yaml - how names in R code and in written formulas map to the tool's neutral
# function names. Reviewers 1, 2 and 4 read this file.
#
# notation: names that the tool reads as a FUNCTION when a written formula shows name( ... ).
#   Any other name followed by "(" could be a product or a function; the tool does not guess and
#   marks the formula "could not be read".
notation:
  functions:
    N: normal_cdf
    "\u03a6": normal_cdf
    Phi: normal_cdf
    ln: log
    log: log
    exp: exp
    sqrt: sqrt
    max: max
    min: min
    abs: abs
    sum_over: sum_over
    piecewise: piecewise
  inverse:                      # name^-1( ... ) is read as the inverse function
    normal_cdf: normal_inverse
# r_functions: R function -> neutral name, with the argument order the tool relies on and the
#   domain in which the neutral function can be evaluated (used to draw valid sample points).
r_functions:
  pnorm:  {neutral: normal_cdf,     arguments: [q],      only_defaults: [mean, sd, lower.tail, log.p]}
  qnorm:  {neutral: normal_inverse, arguments: [p],      only_defaults: [mean, sd, lower.tail, log.p]}
  exp:    {neutral: exp,            arguments: [x]}
  log:    {neutral: log,            arguments: [x],      only_defaults: [base]}
  log1p:  {neutral: log1p,          arguments: [x]}
  expm1:  {neutral: expm1,          arguments: [x]}
  sqrt:   {neutral: sqrt,           arguments: [x]}
  abs:    {neutral: abs,            arguments: [x]}
  max:    {neutral: max,            variadic: true}
  min:    {neutral: min,            variadic: true}
  pmax:   {neutral: max,            variadic: true}
  pmin:   {neutral: min,            variadic: true}
  ifelse: {neutral: piecewise,      arguments: [test, "yes", "no"]}
  sum:    {neutral: sum_over,       variadic: true}
  round:  {neutral: round,          arguments: [x, digits], optional: 1}
  floor:  {neutral: floor,          arguments: [x]}
  ceiling: {neutral: ceiling,       arguments: [x]}
# domains: where each neutral function has a value (open intervals; null means unbounded).
domains:
  normal_cdf:     {argument: [null, null]}
  normal_inverse: {argument: [0, 1]}
  log:            {argument: [0, null]}
  log1p:          {argument: [-1, null]}
  sqrt:           {argument: [0, null]}
  exp:            {argument: [null, 50]}
'''

def load_notation():
    """The names the tool reads as functions in a written formula."""
    return yaml.safe_load(R_FUNCTION_MAP_YAML)["notation"]

def tokenize_formula(text):
    """Cut a written formula into numbers, names and signs. Anything else makes it unreadable."""
    for written, plain in list(SUPERSCRIPTS.items()) + list(SIGNS.items()):
        text = text.replace(written, plain)
    text = re.sub(r"_\{([^{}]*)\}", lambda found: "_" + re.sub(r"\W", "", found.group(1)), text)   # x_{i,j} -> x_ij
    tokens, position = [], 0
    text = text.strip()
    while position < len(text):
        match = _TOKEN_RE.match(text, position)
        if not match or match.end() == position:
            raise NotReadable("it contains '%s', which the tool does not read in a formula" % text[position:position + 12].strip())
        if match.group("number"):
            value = Decimal(match.group("number"))
            tokens.append(("number", plain_decimal(value / 100 if match.group("percent") else value)))
        elif match.group("name"):
            tokens.append(("name", match.group("name")))
        else:
            tokens.append(("sign", match.group("sign")))
        position = match.end()
    return tokens

class FormulaReader:
    """A small recursive-descent reader over the tokens of one formula. Order of strength, from
    weakest: equals, comparison, plus and minus, times and divide, a leading minus, power.
    Two terms side by side are read as a product only when `implicit_product` is set, which
    is done for equation markup (its extent is exact) and never for running text."""
    def __init__(self, tokens, notation, implicit_product=False):
        self.tokens, self.position, self.notation = tokens, 0, notation
        self.functions, self.implicit_product = notation.get("functions", {}), implicit_product

    def peek(self, offset=0):
        """The token at the reading position (or further on), without taking it."""
        index = self.position + offset
        return self.tokens[index] if index < len(self.tokens) else ("end", "")

    def take(self, sign=None):
        """Take the next token; with `sign`, insist that it is that sign."""
        token = self.peek()
        if sign is not None and token != ("sign", sign):
            raise NotReadable("a '%s' was expected where '%s' stands" % (sign, token[1] or "the end"))
        self.position += 1
        return token

    def statement(self):
        """A whole formula: an expression, or `left = right`."""
        left = self.comparison()
        if self.peek() == ("sign", "="):
            self.take()
            left = Expr("eq", args=(left, self.comparison()))
            if self.peek() == ("sign", "="):
                raise NotReadable("it has more than one equals sign")
        return left

    def comparison(self):
        """An expression, optionally compared with another one."""
        left = self.sum()
        if self.peek()[0] == "sign" and self.peek()[1] in ("<", ">", "<=", ">="):
            sign = self.take()[1]
            left = Expr("cmp", name=sign, args=(left, self.sum()))
        return left

    def sum(self):
        """Terms joined by + and -, from left to right."""
        left = self.product()
        while self.peek() in (("sign", "+"), ("sign", "-")):
            op = "add" if self.take()[1] == "+" else "sub"
            left = Expr(op, args=(left, self.product()))
        return left

    def product(self):
        """Factors joined by * and /, from left to right; juxtaposition only where the source allows it."""
        left = self.unary()
        while True:
            if self.peek() in (("sign", "*"), ("sign", "/")):
                op = "mul" if self.take()[1] == "*" else "div"
                left = Expr(op, args=(left, self.unary()))
            elif self.implicit_product and self.term_follows():
                left = Expr("mul", args=(left, self.power()))
            else:
                return left

    def term_follows(self):
        """Does another factor start here without a sign in between?"""
        kind, text = self.peek()
        return kind in ("number", "name") or (kind == "sign" and text in ("(", "\u221a"))

    def unary(self):
        """A leading minus or plus. It binds less tightly than a power, as in mathematics and in R."""
        if self.peek() == ("sign", "-"):
            self.take()
            return Expr("neg", args=(self.unary(),))
        if self.peek() == ("sign", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        """A base with an optional power (right-associative), an inverse-function mark or a percent sign."""
        base = self.atom()
        if self.peek() == ("sign", "^"):
            self.take()
            base = Expr("pow", args=(base, self.unary()))
        if self.term_follows() and not self.implicit_product:
            raise NotReadable("two terms stand side by side without a sign between them, which could "
                              "mean a product or something else; the tool does not guess")
        return base

    def minus_one_follows(self):
        """Is the next thing ^-1 or ^(-1) followed by an opening bracket? Returns tokens to skip."""
        shapes = ([("sign", "^"), ("sign", "-"), ("number", "1"), ("sign", "(")],
                  [("sign", "^"), ("sign", "("), ("sign", "-"), ("number", "1"), ("sign", ")"), ("sign", "(")])
        for shape in shapes:
            if [self.peek(i) for i in range(len(shape))] == shape:
                return len(shape) - 1
        return 0

    def atom(self):
        """A number, a symbol, a function call or a bracketed expression."""
        kind, text = self.take()
        if kind == "number":
            return Expr("num", value=text)
        if kind == "sign" and text == "(":
            inner = self.statement()
            self.take(")")
            return inner
        if kind == "sign" and text == "\u221a":
            return Expr("call", name="sqrt", args=(self.atom(),))
        if kind != "name":
            raise NotReadable("'%s' stands where a number or a symbol was expected" % (text or "the end"))
        function = self.functions.get(text) or self.functions.get(normalise_symbol(text))
        skip = self.minus_one_follows() if function else 0
        if skip:
            inverse = self.notation.get("inverse", {}).get(function)
            if not inverse:
                raise NotReadable("the inverse of '%s' is not a function the tool knows" % text)
            self.position += skip
            function = inverse
        if self.peek() == ("sign", "("):
            if not function:
                raise NotReadable("'%s(' could be a product or a function; the tool does not guess" % text)
            self.take()
            arguments = [self.statement()]
            while self.peek() == ("sign", ","):
                self.take()
                arguments.append(self.statement())
            self.take(")")
            return Expr("call", name=function, args=tuple(arguments))
        return Expr("sym", name=normalise_symbol(text))

def parse_formula(text, notation, implicit_product=False):
    """Read a formula written in linear notation into the tool's expression tree. Raises NotReadable
    with a plain reason; it never guesses and never executes anything. Enforces: R7"""
    tokens = tokenize_formula(text)
    if not tokens:
        raise NotReadable("it is empty")
    reader = FormulaReader(tokens, notation, implicit_product)
    tree = reader.statement()
    if reader.peek()[0] != "end":
        raise NotReadable("'%s' stands where the formula should have ended" % reader.peek()[1])
    return tree

def read_equation(source_form, linear, notation, image_sha256=""):
    """Build the EquationData of a chunk: readable with its tree, or not readable with the reason."""
    linear = normalise_text(linear)
    if not linear:
        reason = UNDECIDED_REASONS[0] if image_sha256 or source_form == "image" else "no formula text was found"
        return EquationData(source_form, "", False, reason, image_sha256)
    try:
        tree = parse_formula(linear, notation, implicit_product=source_form in ("omml", "mathml", "latex"))
    except NotReadable as problem:
        return EquationData(source_form, linear, False, str(problem), image_sha256)
    return EquationData(source_form, expr_to_text(tree), True, "", image_sha256)

_INLINE_FORMULA_RE = re.compile(r"(?<![\w.])([^\W\d_][\w.\[\]{}]*)\s*=\s*([^=;]+)")

def inline_formula(text, notation):
    """A formula written inside running text, such as "K = LGD * N(x)". The right-hand side ends
    at a semicolon, at ", where", or at the end of the sentence. When the notation is ambiguous
    the paragraph simply stays a paragraph (plan 2.8). Returns EquationData or None."""
    for match in _INLINE_FORMULA_RE.finditer(text or ""):
        right = re.split(r",?\s+(?:where|with|and where|for)\b|\.\s+[A-Z]|\.$|:\s", match.group(2))[0]
        right = right.strip().rstrip(".,")
        if not re.search(r"[-+*/^(\u00d7\u00b7\u2212]", right):
            continue                                  # "x = 5" or "a = b": a value, not a formula
        try:
            tree = parse_formula("%s = %s" % (match.group(1), right), notation)
        except NotReadable:
            continue
        return EquationData("inline", expr_to_text(tree), True, "", "")
    return None

# ---------------------------------------------------------------- equation markup -> linear notation
def bracketed(text):
    """Put brackets around a part unless it is one number, one symbol or one call."""
    text = text.strip()
    if re.fullmatch(r"[\w.]+|[\w.]+\([^()]*\)", text) or (text.startswith("(") and text.endswith(")") and
                                                         text.count("(") == 1):
        return text
    return "(%s)" % text

NARY_NAMES = {"\u2211": "sum_over", "\u220f": "product_over", "\u222b": "integral_over"}
MATH_PROPERTIES = ("rpr", "ctrlpr", "fpr", "dpr", "narypr", "radpr", "ssuppr", "ssubpr", "ssubsuppr", "funcpr",
                   "annotation", "omathparapr", "begchr", "endchr")

def math_to_linear(element):
    """Office Math (OMML) and MathML to linear notation, by the local names of the elements:
    fractions, powers, subscripts, roots, brackets and function application. A sum is marked
    as sum_over(...) and never expanded. Unknown elements contribute their text."""
    name = local_name(element.tag)
    def part(child_name):
        child = child_named(element, child_name)
        return math_children(child) if child is not None else ""
    if name in ("t", "mi", "mn", "mtext"):
        return (element.text or "").strip()
    if name == "mo":
        return " %s " % (element.text or "").strip()
    if name == "f":                                               # OMML fraction
        return "%s/%s" % (bracketed(part("num")), bracketed(part("den")))
    if name == "ssup":
        return "%s^%s" % (bracketed(part("e")), bracketed(part("sup")))
    if name == "ssub":
        return "%s_{%s}" % (part("e").strip(), part("sub").strip())
    if name == "ssubsup":
        return "%s_{%s}^%s" % (part("e").strip(), part("sub").strip(), bracketed(part("sup")))
    if name == "rad":
        degree = part("deg").strip()
        return "sqrt(%s)" % part("e") if degree in ("", "2") else "%s^(1/%s)" % (bracketed(part("e")), bracketed(degree))
    if name == "d":                                               # OMML brackets
        return "(%s)" % ", ".join(math_children(child) for child in element if local_name(child.tag) == "e")
    if name == "func":
        return "%s(%s)" % (part("fname").strip(), strip_outer_brackets(part("e")))
    if name == "nary":
        properties = child_named(element, "narypr")
        sign = child_named(properties, "chr") if properties is not None else None
        kind = NARY_NAMES.get(attribute(sign, "val"), "sum_over") if sign is not None else "integral_over"
        return "%s(%s, %s, %s)" % (kind, part("sub").strip() or "0", part("sup").strip() or "0", part("e"))
    children = list(element)
    if name == "mfrac" and len(children) == 2:
        return "%s/%s" % (bracketed(math_to_linear(children[0])), bracketed(math_to_linear(children[1])))
    if name == "msup" and len(children) == 2:
        return "%s^%s" % (bracketed(math_to_linear(children[0])), bracketed(math_to_linear(children[1])))
    if name == "msub" and len(children) == 2:
        return "%s_{%s}" % (math_to_linear(children[0]).strip(), math_to_linear(children[1]).strip())
    if name == "msubsup" and len(children) == 3:
        return "%s_{%s}^%s" % (math_to_linear(children[0]).strip(), math_to_linear(children[1]).strip(),
                               bracketed(math_to_linear(children[2])))
    if name == "msqrt":
        return "sqrt(%s)" % math_children(element)
    if name == "mroot" and len(children) == 2:
        return "%s^(1/%s)" % (bracketed(math_to_linear(children[0])), bracketed(math_to_linear(children[1])))
    if name == "mfenced":
        return "(%s)" % ", ".join(math_to_linear(child) for child in children)
    if name == "munderover" and len(children) == 3 and (children[0].text or "").strip() in NARY_NAMES:
        return "%s(%s, %s, " % (NARY_NAMES[children[0].text.strip()], math_to_linear(children[1]).strip(),
                                math_to_linear(children[2]).strip())
    if name in MATH_PROPERTIES:
        return ""                                                 # properties, not content
    return math_children(element)

def math_children(element):
    """The linear text of all children, in order. An open "sum_over(a, b, " from MathML takes
    the part that follows it as its body and is then closed."""
    pieces = [(element.text or "").strip() if not len(element) else ""]
    for child in element:
        piece = math_to_linear(child)
        if pieces[-1].endswith(", ") and pieces[-1].startswith(tuple(NARY_NAMES.values())):
            pieces[-1] = pieces[-1] + piece.strip() + ")"
        else:
            pieces.append(piece)
    return re.sub(r"\s+", " ", "".join(pieces)).strip()

def strip_outer_brackets(text):
    """Remove one pair of brackets that encloses the whole text."""
    text = text.strip()
    return text[1:-1] if text.startswith("(") and text.endswith(")") and text.count("(") == 1 else text

LATEX_WORDS = {"cdot": "*", "times": "*", "div": "/", "le": "<=", "leq": "<=", "ge": ">=", "geq": ">=",
               "ln": "ln", "log": "log", "exp": "exp", "max": "max", "min": "min", "left": "", "right": "",
               "quad": " ", "qquad": " ", ",": " ", ";": " ", "!": "", " ": " ", "displaystyle": ""}
LATEX_WRAPPERS = ("text", "mathrm", "mathit", "mathbf", "operatorname", "mbox", "textit", "textbf", "code")

def latex_group(source, position):
    """The content of the {...} group that starts at `position`, and the position after it."""
    if position >= len(source):
        raise NotReadable("a LaTeX command lacks its argument")
    if source[position] != "{":
        return source[position], position + 1
    depth, start = 0, position
    while position < len(source):
        depth += {"{": 1, "}": -1}.get(source[position], 0)
        position += 1
        if depth == 0:
            return source[start + 1:position - 1], position
    raise NotReadable("a LaTeX group is never closed")

def latex_to_linear(source):
    """The LaTeX subset found in roxygen \\eqn{} and \\deqn{} and in some XML, to linear notation:
    \\frac, \\sqrt, ^{}, _{}, Greek letters, \\cdot, \\times, \\left, \\right, text wrappers.
    An unknown command makes the formula unreadable; it is never skipped silently."""
    source, output, position = source.strip().strip("$"), [], 0
    while position < len(source):
        char = source[position]
        if char == "\\":
            match = re.match(r"\\([A-Za-z]+|.)", source[position:])
            word, position = match.group(1), position + match.end()
            if word == "frac":
                top, position = latex_group(source, position)
                bottom, position = latex_group(source, position)
                output.append("(%s)/(%s)" % (latex_to_linear(top), latex_to_linear(bottom)))
            elif word == "sqrt":
                degree = ""
                if source[position:position + 1] == "[":
                    end = source.index("]", position)
                    degree, position = source[position + 1:end], end + 1
                inner, position = latex_group(source, position)
                inner = latex_to_linear(inner)
                output.append("sqrt(%s)" % inner if degree in ("", "2") else "(%s)^(1/(%s))" % (inner, degree))
            elif word in LATEX_WRAPPERS:
                inner, position = latex_group(source, position)
                output.append(re.sub(r"\s+", "_", inner.strip()))
            elif word in GREEK:
                output.append(GREEK[word])
            elif word in LATEX_WORDS:
                output.append(LATEX_WORDS[word])
            else:
                raise NotReadable("it uses the LaTeX command '\\%s', which the tool does not read" % word)
        elif char == "^":
            inner, position = latex_group(source, position + 1)
            output.append("^(%s)" % latex_to_linear(inner))
        elif char == "_":
            inner, position = latex_group(source, position + 1)
            output.append("_{%s}" % latex_to_linear(inner).replace(" ", ""))
        elif char in "{}":
            output.append("(" if char == "{" else ")")
            position += 1
        else:
            output.append(char)
            position += 1
    return re.sub(r"\s+", " ", "".join(output)).strip()

# ---------------------------------------------------------------- format from content, and repairs
XML_ENTITIES = ("amp", "lt", "gt", "quot", "apos")

def repair_markup(text, file_name, repairs):
    """The repairs the tool makes before strict parsing. Each one is recorded with its position, its
    kind, and the text before and after, so that a reviewer can see exactly what was changed."""
    def record(kind, position, before, after):
        repairs.append({"file": file_name, "position": position, "kind": kind,
                        "before": before[:200], "after": after[:200]})
    def fix(pattern, kind, replacement, flags=0):
        nonlocal text
        def change(found):
            after = replacement(found) if callable(replacement) else replacement
            record(kind, found.start(), found.group(0), after)
            return after
        text = re.sub(pattern, change, text, flags=flags)
    fix(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "control character removed", "")
    fix(r"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", "document-type declaration removed", "", re.S | re.I)
    def entity(found):
        name = found.group(1)
        if name in XML_ENTITIES or name not in html.entities.name2codepoint:
            return found.group(0)
        return "&#%d;" % html.entities.name2codepoint[name]
    before_entities = text
    text = re.sub(r"&([A-Za-z][A-Za-z0-9]*);", entity, text)
    if text != before_entities:
        named = sorted(set(re.findall(r"&([A-Za-z][A-Za-z0-9]*);", before_entities)) - set(XML_ENTITIES))
        record("named characters replaced by their numbers", 0, ", ".join("&%s;" % n for n in named), "")
    fix(r'=""([^"<>=]*)""', "doubled quotes in an attribute", lambda found: '="%s"' % found.group(1))
    body = re.sub(r"<\?xml[^>]*\?>|<!--.*?-->", "", text, flags=re.S)
    roots, depth = 0, 0
    for tag in re.finditer(r"<(/?)([^\s<>/!?][^<>]*?)(/?)>", body):
        if tag.group(1):
            depth -= 1
        elif not tag.group(3):
            roots += 1 if depth == 0 else 0
            depth += 1
        else:
            roots += 1 if depth == 0 else 0
    if roots > 1:
        declaration = re.match(r"\s*<\?xml[^>]*\?>", text)
        start = declaration.end() if declaration else 0
        text = text[:start] + "<document-root>" + text[start:] + "</document-root>"
        record("several top elements wrapped in one", start, "%d top elements" % roots, "<document-root>")
    return text

VOID_TAGS = ("img", "br", "hr", "meta", "link", "input", "col", "area", "base", "wbr")
BLOCK_STARTS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "div", "li", "tr")
IMPLIED_END = dict({tag: ("p",) for tag in BLOCK_STARTS}, li=("li", "p"), tr=("tr", "td", "th", "p"), td=("td", "th", "p"), th=("td", "th", "p"))

class TolerantReader(html.parser.HTMLParser):
    """Builds the same kind of element tree as the strict XML parser, from start, end and text
    events of the standard library's HTML parser. It forgives what real exports contain: tags
    never closed, tags closed in the wrong order, attributes without quotes. Equation markup
    that Word's web export hides inside conditional comments is read too. (This is the one
    place where the tool subclasses: the standard parser offers no other way to receive events.)"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.builder, self.open_tags = ElementTree.TreeBuilder(), []
        self.builder.start("document-root", {})

    def handle_starttag(self, tag, attrs):
        """Open an element, first closing what HTML closes implicitly."""
        while self.open_tags and self.open_tags[-1] in IMPLIED_END.get(tag, ()):       # <p> ends an open <p>, as browsers read it
            self.builder.end(self.open_tags.pop())
        self.builder.start(tag, {name: value or "" for name, value in attrs})
        if tag in VOID_TAGS:
            self.builder.end(tag)
        else:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        """An element written as empty: opened and closed at once."""
        self.builder.start(tag, {name: value or "" for name, value in attrs})
        self.builder.end(tag)

    def handle_endtag(self, tag):
        """Close the nearest open element of this name; a stray end tag is recorded as a repair."""
        if tag not in self.open_tags:
            return                                       # an end tag that closes nothing is ignored
        while self.open_tags:
            closing = self.open_tags.pop()
            self.builder.end(closing)
            if closing == tag:
                return

    def handle_data(self, data):
        """Text between tags."""
        self.builder.data(data)

    def handle_comment(self, data):
        """Keep equation markup that Word's web export hides in conditional comments; drop other comments."""
        preserved = re.match(r"\[if[^\]]*msEquation[^\]]*\]>(.*)<!\[endif\]", data, re.S)
        if preserved and "omath" in preserved.group(1).lower():
            self.builder.start("verifier-preserved-equation", {})
            self.feed_inner(preserved.group(1))
            self.builder.end("verifier-preserved-equation")

    def feed_inner(self, markup):
        """Read preserved equation markup found inside a comment into the tree being built."""
        inner = TolerantReader()
        inner.feed(markup)
        for child in inner.finish():
            self.builder.start(child.tag, child.attrib)
            self.copy_children(child)
            self.builder.end(child.tag)

    def copy_children(self, element):
        """Copy an element read elsewhere into the tree being built."""
        if element.text:
            self.builder.data(element.text)
        for child in element:
            self.builder.start(child.tag, child.attrib)
            self.copy_children(child)
            self.builder.end(child.tag)
            if child.tail:
                self.builder.data(child.tail)

    def finish(self):
        """Close whatever is still open and return the root element."""
        self.close()
        while self.open_tags:
            self.builder.end(self.open_tags.pop())
        self.builder.end("document-root")
        return self.builder.close()

def parse_markup(text, file_name, repairs, tolerant_only=False):
    """Strict XML parsing first; when that still fails after the repairs, the tolerant reader.
    The path taken is recorded. Returns the root element."""
    repaired = repair_markup(text, file_name, repairs)
    if not tolerant_only:
        try:
            return ElementTree.fromstring(repaired.encode("utf-8"))
        except ElementTree.ParseError as problem:
            repairs.append({"file": file_name, "position": 0, "kind": "read with the tolerant reader",
                            "before": "strict reading stopped: %s" % problem, "after": ""})
    reader = TolerantReader()
    reader.feed(repaired)
    return reader.finish()

# ---------------------------------------------------------------- tag rules and the block walker
def load_tag_rules(override_path=None):
    """The shipped tag rules, with any part replaced by the project's own Inputs/tag_rules.yaml."""
    rules = yaml.safe_load(TAG_RULES_YAML)
    rules["shipped_tags"] = sorted(str(tag).lower() for tags in rules["families"].values() for tag in tags)
    analyst_families = {}
    if override_path:
        with open(override_path, encoding="utf-8") as handle:
            override = yaml.safe_load(handle) or {}
        analyst_families = override.get("families") or {}
        for key, value in override.items():
            if key == "families":
                rules["families"].update(value or {})
            else:
                rules[key] = value
    rules["analyst_tags"] = sorted(str(tag).lower() for tags in analyst_families.values() for tag in tags)
    rules["family_of"] = {}
    for family, tags in rules["families"].items():
        for tag in tags:
            rules["family_of"][str(tag).lower()] = family
    rules.setdefault("heading_attributes", ["name", "title", "heading", "label", "caption"])
    rules.setdefault("caption_tag_words", ["title", "number", "caption", "legend"])
    rules.setdefault("header_tag_words", ["head", "header"])
    return rules

# ---------------------------------------------------------------- discovering an unfamiliar schema
BLOCKS_INSIDE = ("paragraph", "list_item", "list_container", "heading", "container", "row", "cell", "header_cell")

def element_text(element, rules, skip=("figure", "equation", "ignore", "caption")):
    """The running text of an element without the text of figures, equations and captions in it.

    A child that is a block of its own - a list item inside a table cell, say - is separated by
    a space rather than run straight onto what came before it. Without that, two items of a
    list in one cell arrive as one word that the document does not contain ("renewable twice" +
    "no fine" giving "twiceno"), which is text the tool made up. Enforces: R13"""
    pieces = [element.text or ""]
    for child in element:
        if rules["family_of"].get(local_name(child.tag)) not in skip:
            if rules["family_of"].get(local_name(child.tag)) in BLOCKS_INSIDE and "".join(pieces).strip():
                pieces.append(" ")
            pieces.append(element_text(child, rules, skip))
        pieces.append(child.tail or "")
    return "".join(pieces)

def new_block(kind, text="", locator="", **more):
    """One block of a document before numbering: kind, text, where it was found, and what its kind needs."""
    block = {"type": kind, "text": normalise_text(text), "locator": locator, "level_hint": None,
             "numbering": "", "caption": "", "table": None, "equation": None, "reconstructed": False,
             "not_read_reason": ""}
    block.update(more)
    return block

def not_read_block(file_name, reason):
    """A whole file, or a part, that could not be read still becomes one block: the "not read"
    class of the content account, never a silent gap. Enforces: R2, R13"""
    return new_block("paragraph", "", file_name, not_read_reason=reason)

@dataclass
class WalkState:
    """What the walker carries along: the rules, the notation, images by name, the report of
    tags it met that are in no family, and what discovery made of those tags in this document."""
    rules: dict; notation: dict; images: dict; unknown_tags: dict; blocks: list
    skip_next_image: bool = False
    notes: list = field(default_factory=list)      # what was left out or read in a fallback way, in plain words
    atoms: list = field(default_factory=list)      # the smallest pieces of text the file holds, counted from the file itself
    dropped: list = field(default_factory=list)    # text left out under a named rule, kept so the account can show it
    lent_numbering: str = ""                       # a number a container carries for the heading inside it
    settings: dict = field(default_factory=dict)
    guided: dict = field(default_factory=dict)     # tag -> family, where the model's proposal was applied
    folder: str = ""                               # where the file being read stands, so a picture beside it can be found
    svgs: dict = field(default_factory=dict)       # the corner's SVG files, by lower-case name and by name without .svg
    consumed: set = field(default_factory=set)     # SVGs already read in place by a document of the corner (shared by the corner)
    file_name: str = ""
    lists: list = field(default_factory=list)      # the lists the walker is inside of: [numbered?, items so far]

    def __post_init__(self):
        """Each file reads with its own view of the rules, so a tag discovered in one file
        never changes how the next file is read."""
        self.rules = dict(self.rules)
        self.rules["family_of"] = dict(self.rules["family_of"])

    def family(self, tag):
        """The family of a tag: what the rules say, else what discovery made of it here."""
        return self.rules["family_of"].get(tag)

def walk_element(element, path, depth, state):
    """Turn one element and everything below it into blocks, in reading order."""
    name = local_name(element.tag)
    family = state.family(name)
    here = "%s/%s" % (path, name)
    if name == "verifier-preserved-equation":
        state.blocks.append(equation_block(element, here, state))
        state.skip_next_image = True                     # the picture that follows shows the same equation
        return
    if family == "ignore" or not name:
        return
    linked, named_by = (svg_reference(element, state), element) if state.svgs else (None, None)
    if not linked and state.svgs and state.family(name) == "figure":
        # a figure may name its picture one level down: <chart><file>Chart2.svg</file></chart>
        linked, named_by = next(((found, below) for below in element.iter() if below is not element
                                 for found in [svg_reference(below, state)] if found), (None, None))
    if linked:                                           # a chart or table drawn as an SVG beside the document: read it here, in place
        if named_by is not None and len(named_by) == 0 and (named_by.text or "").strip():
            state.dropped.append(named_by.text)          # the file name written as text is a reference, not what the document says
        caption = next((normalise_text(element_text(n, state.rules, skip=())) for n in element.iter()
                        if state.rules["family_of"].get(local_name(n.tag)) == "caption"), "") or element.get("alt") or element.get("title") or ""
        with open(linked, "rb") as handle:
            state.blocks.extend(svg_blocks(handle.read(), os.path.basename(linked), here, state, caption))
        state.consumed.add(linked)
        state.notes.append("%s: read in place, where %s refers to it." % (os.path.basename(linked), state.file_name or "the document"))
        return
    if family is None:                                   # discovery names every tag it reaches; this is the net under it
        family = "container" if len(element) else "paragraph"
    numbering = written_numbering(element, state.rules)
    if family == "heading":
        text = element_text(element, state.rules)
        digit = re.fullmatch(r"h([1-6])", name)
        state.blocks.append(new_block("heading", text, here, numbering=numbering or state.lent_numbering,
                                      level_hint=int(digit.group(1)) if digit else depth))
        state.lent_numbering = ""
    elif family in ("container", "list_container", "inline"):
        # A container that carries its own heading in an attribute (<section name="4. Market">)
        # gives that heading a block of its own, so the chain below it is not lost.
        heading, _ = attribute_text(element, state.rules["heading_attributes"]) if family == "container" else ("", "")
        if heading:
            state.blocks.append(new_block("heading", heading, here, numbering=numbering, level_hint=depth))
        if family == "list_container":                   # <ol>, or <list type="numbered">: its items are counted
            kind = " ".join([name] + [element.get(a) or "" for a in ("type", "style", "numeration", "class")]).lower()
            state.lists.append([bool(re.search(r"\bol\b|order|num|decimal|arabic|alpha|roman", kind)), 0])
        # A container often carries the number of the section (<section num="2.">) while the
        # heading it labels is a child of it (<title>). The number is lent to the first heading
        # the container produces, so that "2." belongs to "2. Volume per bed" and not to
        # nothing at all. Enforces: R13
        lent, state.lent_numbering = state.lent_numbering, numbering if family == "container" and numbering and not heading else ""
        walk_mixed(element, here, depth + (1 if family == "container" else 0), state)
        state.lent_numbering = lent
        if family == "list_container":
            state.lists.pop()
    elif family in ("paragraph", "list_item"):
        marker = ""
        if family == "list_item":
            inside = state.lists[-1] if state.lists else [False, 0]
            inside[1] += 1
            marker = "  " * max(0, len(state.lists) - 1) + ("%d. " % inside[1] if inside[0] else LIST_MARKER)
        walk_mixed(element, here, depth, state, own_kind="list_item" if family == "list_item" else "paragraph",
                   numbering=numbering, marker=marker)
    elif family == "table":
        state.blocks.append(table_block(element, here, state))
    elif family == "figure":
        if state.skip_next_image:
            state.skip_next_image = False
            return
        found = figure_block(element, here, state)
        state.blocks.extend(found if isinstance(found, list) else [found])   # an SVG beside the document may give a table
    elif family == "equation":
        state.blocks.append(equation_block(element, here, state))
    elif family == "caption" and state.blocks and state.blocks[-1]["type"] in ("figure", "table", "equation"):
        state.blocks[-1]["caption"] = normalise_text(element_text(element, state.rules, skip=()))

def walk_mixed(element, here, depth, state, own_kind=None, numbering="", marker=""):
    """An element that may hold both running text and blocks. Its own text becomes one
    paragraph; a formula that fills the paragraph alone becomes an Equation block instead."""
    block_families = ("heading", "container", "list_container", "paragraph", "list_item", "table",
                      "figure", "equation", "caption", None)
    children = [c for c in element if local_name(c.tag) and
                (state.family(local_name(c.tag)) in block_families or local_name(c.tag) == "verifier-preserved-equation")]
    inline_only = [c for c in children if state.family(local_name(c.tag)) is None and not len(c)
                   and own_kind]
    children = [c for c in children if c not in inline_only]
    text = normalise_text(element_text(element, state.rules, skip=("figure", "equation", "ignore", "caption",
                                 "table", "list_container")) if own_kind or not children else (element.text or ""))
    equations = [c for c in children if state.family(local_name(c.tag)) == "equation"]
    if own_kind and text and equations:                  # text around a formula: show the formula in place
        text = normalise_text(text + " " + " ".join(math_to_linear(c) for c in equations))
        children = [c for c in children if c not in equations]
    if text and (own_kind or not children):
        state.blocks.append(new_block(own_kind or "paragraph", text, here, numbering=numbering, marker=marker))
    for position, child in enumerate(children, start=1):
        if own_kind and state.family(local_name(child.tag)) in ("paragraph", "inline"):
            continue                                     # already part of the paragraph's own text
        walk_element(child, "%s[%d]" % (here, position), depth, state)
        if not own_kind and child.tail and child.tail.strip():
            state.blocks.append(new_block("paragraph", child.tail, here))

def table_block(element, here, state):
    """A table is always one block: header cells, body rows and its caption stay together.
    Whatever sits in a row is a cell unless it is the caption or is ignored, so a kind of cell
    that first turns up in the fortieth row still keeps its words. Tags holding the table's
    number and title beside empty cells are the caption, kept in the order written; the rows
    they leave empty are dropped, so the first row with content is the header. A table whose
    rows cannot be found keeps its words as running text and says so: a table that is present
    and empty misleads more than none."""
    family = lambda node: state.family(local_name(node.tag))
    found = [node for node in element.iter() if family(node) == "row"] or table_rows(element, state.rules)
    rows, captions = [], []
    in_a_row = {id(node) for row in found for node in row.iter()}
    for node in element.iter():
        # A caption may be named as one, or may simply sit beside the rows rather than in them
        # (<gridcaption> under <gridholder>). Either way its words belong to the table and are
        # kept: a table whose title is lost cannot be cited by its number. Enforces: R13
        beside = (node is not element and id(node) not in in_a_row and family(node) not in ("row", "table_part", "ignore")
                  and not any(child is not None and family(child) == "row" for child in node))
        part = normalise_text(element_text(node, state.rules, skip=())) if family(node) == "caption" or beside else ""
        if part and part not in captions:
            captions.append(part)
    for row in found:
        cells = [normalise_text(element_text(cell, state.rules, skip=())) for cell in row
                 if local_name(cell.tag) and family(cell) not in ("caption", "ignore")]
        if any(cells):
            rows.append(cells)
    block = table_from_rows(rows, here, ". ".join(captions))
    words = "" if rows else normalise_text(element_text(element, state.rules, skip=("ignore", "caption")))
    if words:
        block["display"] = words
        state.notes.append("The rows of the table at %s could not be told apart, so its words are shown as running text." % here)
    return block

def table_from_rows(rows, locator, caption=""):
    """The one-cell display form of a table. Short values are shown as a grid: cells joined by
    "; ", one row per line, header first. Sentences would be unreadable that way, so each cell
    goes on its own line under the heading of its column ("Very Strong: Airport that ..."); a row
    with one filled cell (a sub-heading, a note) is shown as it stands. The grid is kept either way."""
    width = max((len(row) for row in rows), default=0)
    rows = [list(row) + [""] * (width - len(row)) for row in rows]
    header, body = (rows[0], rows[1:]) if rows else ([], [])
    filled = [cell for row in body if sum(1 for cell in row if cell) > 1 for cell in row if cell]   # sub-headings and notes do not vote
    if filled and sum(len(cell) for cell in filled) > 60 * len(filled):
        lines = ["; ".join(cell for cell in header if cell)]
        for row in body:
            cells = [(header[i], cell) for i, cell in enumerate(row) if cell]
            lines.extend(("%s: %s" % pair if pair[0] and len(cells) > 1 else pair[1]) for pair in cells)
        display = "\n".join(lines)
    else:
        display = "\n".join("; ".join(row[:max((i for i, cell in enumerate(row) if cell), default=0) + 1]) for row in rows)
    first = [row[0] for row in body if row[0]] if width else []     # a first column of words keys the rows
    numeric = first and all(find_numbers(v) and len(find_numbers(v)) == 1 and
                            len(re.sub(r"[\d.,%\s+-]|bps?|basis points?", "", v)) == 0 for v in first)
    row_key = header[0] if header and width and not numeric else ""
    table = TableData(tuple(header), tuple(tuple(row) for row in body), row_key)
    return new_block("table", "", locator, table=table, caption=caption, display=display)

PICTURE_READER = []                     # the OCR engine, looked for once: [engine] or [None]
OCR_NOTE = "Words read from the picture by OCR (a machine reading: check it against the picture itself):"

def read_picture(data, state):
    """The words in a picture, read by OCR, as lines to show under the Figure; "" when there are
    none or no OCR package is installed (rapidocr-onnxruntime is optional; its models come inside
    the package, so nothing is fetched when it runs). The words help a person find the
    picture. They are never evidence: a machine misreads digits, so a Figure still ends
    "for manual review" whatever was read. A missing reader is said once per file. Enforces: R2"""
    if not PICTURE_READER:
        try:
            from rapidocr_onnxruntime import RapidOCR
            PICTURE_READER.append(RapidOCR())
        except Exception:                                # not installed, or its models cannot be loaded
            PICTURE_READER.append(None)
    missing = "The words inside pictures were not read: the optional OCR package rapidocr-onnxruntime is not installed."
    if PICTURE_READER[0] is None and missing not in state.notes:
        state.notes.append(missing)
    if PICTURE_READER[0] is None or len(data) < 2048 or not state.rules.get("read_pictures", True):
        return ""                                        # under 2 kB is an icon or a rule, not a picture with words
    try:
        found = sorted(PICTURE_READER[0](data)[0] or [], key=lambda item: (round(item[0][0][1] / 14), item[0][0][0]))
    except Exception:                                    # a form the reader cannot open (.emf, .wmf)
        unread = "The words inside one or more pictures were not read: the picture is in a form the reader cannot open."
        if unread not in state.notes:
            state.notes.append(unread)                   # the picture is still a unit; only its words are missing (R2)
        return ""
    rows = {}
    for box, words, _ in found:                          # what stands on one line of the picture stays on one line
        rows.setdefault(round(box[0][1] / 14), []).append(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", words))
    return "\n%s\n%s" % (OCR_NOTE, "\n".join("  ".join(row) for row in rows.values())) if rows else ""

def picture_words(page, box, state):
    """PDF: the part of the page that a picture covers, drawn at 150 dpi and read by OCR."""
    if box[2] - box[0] < 40 or box[3] - box[1] < 40:
        return ""
    try:
        drawn = io.BytesIO()
        area = (max(box[0], 0), max(box[1], 0), min(box[2], page.width), min(box[3], page.height))
        page.crop(area).to_image(resolution=150).original.save(drawn, "PNG")
    except Exception:
        return ""
    return read_picture(drawn.getvalue(), state)

def figure_block(element, here, state):
    """A figure: never read, kept with its caption or alternative text and the fingerprint of the image."""
    source = element.get("src") or element.get("href") or element.get("fileref") or ""
    inner = next((n for n in element.iter() if n is not element and (n.get("src") or n.get("fileref"))), None)
    if not source and inner is not None:
        source = inner.get("src") or inner.get("fileref") or ""
    label = element.get("alt") or element.get("title") or (inner.get("alt") if inner is not None else "") or ""
    caption = next((normalise_text(element_text(n, state.rules, skip=())) for n in element.iter()
                    if state.rules["family_of"].get(local_name(n.tag)) == "caption"), "")
    fingerprint = state.images.get(source) or state.images.get(source.replace("cid:", "")) or ""
    return new_block("figure", label or caption or source, here, caption=caption, image_sha256=fingerprint,
                     source=source)

LINK_ATTRIBUTE = re.compile(r"src|href|ref|file|data|path|url|image|graphic", re.I)

def svg_reference(element, state):
    """The SVG of this corner an element refers to, or None. A reference is either an attribute
    whose name says it links (src, href, xlink:href, fileref, data, a tool's own graphic= or
    image=), or an element's whole text when it names a file ending in .svg. A plain name is
    matched to a file of the corner in any case, and without .svg only when it came from a link
    attribute; a path is followed only if it stays inside the document's folder. Found on review:
    matching any short text without .svg took the heading <title>Floors</title> for floors.svg and
    replaced the heading with the chart. Enforces: R6"""
    values = [value for key, value in element.attrib.items() if LINK_ATTRIBUTE.search(local_name(key))]
    text = (element.text or "").strip() if len(element) == 0 else ""
    if text.lower().endswith(".svg") and len(text) < 200:
        values.append(text)
    for value in values:
        written = (value or "").strip().replace("\\", "/").split("?")[0].split("#")[0]
        if not written or ".." in written.split("/") or "://" in written or written.startswith("/"):
            continue
        if "/" in written and state.folder:
            resolved = os.path.normpath(os.path.join(state.folder, written)).lower()
            found = next((path for path in state.svgs.values() if os.path.normpath(path).lower() == resolved), None)
            if found:
                return found
        name = os.path.basename(written).lower()
        for key in ((name,) if name.endswith(".svg") else (name, name + ".svg")):
            if key in state.svgs:
                return state.svgs[key]
    return None

def svg_blocks(data, name, here, state, caption=""):
    """The units of one SVG, read by the text it holds: a table where its text stands in a grid, a
    figure of its labels otherwise. Where it holds no text, a picture stored inside it is read by
    OCR when that is installed; and a figure that still gives no words says why, instead of standing
    empty. The words counted are the SVG's own, so the content account closes. Enforces: R2, R13"""
    import xml.etree.ElementTree as ElementTree
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return [not_read_block(name, "the SVG file is damaged and could not be opened")]
    markup, words, _ = svg_to_markup(data, name)
    own_caption, labels = (words.split("\n", 1) + [""])[:2]
    state.atoms.extend(atoms_of_plain_text(labels if caption else words, name))
    blocks = walk_svg_markup(parse_markup(markup, name, [], False), here, state)
    for block in blocks:
        block["caption"] = caption or own_caption
        block["source"], block["image_sha256"] = name, sha256_bytes(data)
        if block["type"] == "figure" and not block["text"].strip():
            seen = "".join(read_picture(picture, state) for picture in svg_embedded_pictures(root)).strip()
            if seen:
                block["text"] = seen                     # words read from a picture: shown, never evidence
            else:
                block["not_read_reason"] = "the picture gave no words: %s" % svg_why_no_text(root)
    return blocks

def walk_svg_markup(root, here, state):
    """The blocks the SVG's markup gives: a table block, or one figure block carrying the
    picture's labels as its text."""
    blocks = []
    for node in root:
        family = state.rules["family_of"].get(local_name(node.tag))
        if family == "table":
            block = table_block(node, here, state)
            if block is not None:
                blocks.append(block)
        elif family == "figure":
            blocks.append(new_block("figure", node.get("alt") or "", here,
                                    caption=next((normalise_text("".join(c.itertext())) for c in node if local_name(c.tag) == "caption"), "")))
    return blocks


def equation_block(element, here, state):
    """An equation element: MathML or Office Math is converted; LaTeX or linear text is read as
    written; an equation that is only a picture stays an Equation chunk that could not be read."""
    markup = next((n for n in element.iter() if local_name(n.tag) in ("math", "omath")), None)
    picture = next((n for n in element.iter() if local_name(n.tag) in ("img", "image", "graphic", "imagedata")), None)
    if markup is not None:
        form = "mathml" if local_name(markup.tag) == "math" else "omml"
        equation = read_equation(form, math_to_linear(markup), state.notation)
    elif picture is not None and not normalise_text(element_text(element, state.rules)):
        source = picture.get("src") or picture.get("fileref") or ""
        equation = read_equation("image", "", state.notation, state.images.get(source, "") or sha256_text(source))
    else:
        written = normalise_text(element_text(element, state.rules, skip=("caption", "ignore")))
        try:
            linear = latex_to_linear(written) if "\\" in written else written
            equation = read_equation("latex" if "\\" in written else "inline", linear, state.notation)
        except NotReadable as problem:
            equation = EquationData("latex", written, False, str(problem), "")
    label = picture.get("alt") if picture is not None and picture.get("alt") else ""
    text = equation.linear or label or "Equation shown as a picture"
    return new_block("equation", text, here, equation=equation)

def blocks_from_markup(text, file_name, state, repairs, tolerant_only=False):
    """XML or HTML text to blocks: parse (repairing where needed), then walk the tree by the tag rules."""
    root = parse_markup(text, file_name, repairs, tolerant_only)
    discovered = discover_families(root, state.rules, state.unknown_tags)
    state.rules["family_of"].update(discovered)
    walk_element(root, "", 0, state)
    return state.blocks

# ---------------------------------------------------------------- MHTML (a web page saved as one file)
def blocks_from_mhtml(data, file_name, state, repairs):
    """Parts are read with the standard `email` package. The HTML part goes through the tolerant
    reader; every image part is fingerprinted so that a Figure chunk can name its content."""
    message = email.message_from_bytes(data)
    page = None
    for part in message.walk():
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if content_type == "text/html" and page is None:
            page = payload.decode(part.get_content_charset() or "utf-8", "replace")
        elif content_type.startswith("image/"):
            fingerprint = sha256_bytes(payload)
            for key in (part.get("Content-Location", ""), (part.get("Content-ID", "") or "").strip("<>")):
                if key:
                    state.images[key] = fingerprint
                    state.images[key.rsplit("/", 1)[-1]] = fingerprint
    if page is None:
        return [not_read_block(file_name, "the file holds no web page part")]
    blocks = blocks_from_markup(page, file_name, state, repairs, tolerant_only=True)
    return [block for block in title_block(page, file_name) + blocks]

def title_block(page, file_name):
    """The <title> of a web page, as a heading above everything in it. In a Word file exported
    to the web it is often the only place the document's own name survives, because the visible
    heading may be a styled paragraph carrying no heading level. Without this the title reaches
    no unit and can be cited by nothing. Enforces: R13"""
    found = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    text = normalise_text(re.sub(r"<[^>]+>", " ", found.group(1))) if found else ""
    return [new_block("heading", text, "%s title" % file_name, level_hint=1)] if text else []

# ---------------------------------------------------------------- .docx
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
           "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
           "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
           "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
           "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}

def word_value(element, path, attribute_name="val"):
    """The value of a Word property such as a style id or an outline level, or None."""
    found = element.find(path, WORD_NS)
    return found.get("{%s}%s" % (WORD_NS["w"], attribute_name)) if found is not None else None

def docx_paragraph_facts(paragraph, styles):
    """Heading level (from the style name or the outline level, following based-on styles) and
    whether Word numbers this paragraph automatically."""
    style_id = word_value(paragraph, "w:pPr/w:pStyle") or ""
    level = word_value(paragraph, "w:pPr/w:outlineLvl")
    numbering = paragraph.find("w:pPr/w:numPr", WORD_NS)
    name, hops = "", 0
    while style_id in styles and hops < 5:
        style = styles[style_id]
        name = name or (word_value(style, "w:name") or "")
        level = level if level is not None else word_value(style, "w:pPr/w:outlineLvl")
        numbering = numbering if numbering is not None else style.find("w:pPr/w:numPr", WORD_NS)
        style_id, hops = word_value(style, "w:basedOn") or "", hops + 1
    numbered = (word_value(numbering, "w:numId") or "", word_value(numbering, "w:ilvl") or "0") if numbering is not None else None
    if numbered and numbered[0] == "0":                  # Word writes numId 0 to switch numbering off
        numbered = None
    heading = re.fullmatch(r"[Hh]eading\s*(\d)", name)
    if heading:
        return int(heading.group(1)), numbered, name
    if level is not None and level.isdigit() and int(level) < 9:
        return int(level) + 1, numbered, name
    return None, numbered, name

def docx_number_formats(archive):
    """How each numbering of a Word file shows its items, by numbering id and level: "bullet",
    "decimal", "lowerLetter" ... Word keeps this apart from the text, in word/numbering.xml."""
    if "word/numbering.xml" not in archive.namelist():
        return {}
    root, key = safe_xml(archive.read("word/numbering.xml")), "{%s}" % WORD_NS["w"]
    shapes = {a.get(key + "abstractNumId"): {lvl.get(key + "ilvl"): word_value(lvl, "w:numFmt") for lvl in a.findall("w:lvl", WORD_NS)}
              for a in root.findall("w:abstractNum", WORD_NS)}
    return {n.get(key + "numId"): shapes.get(word_value(n, "w:abstractNumId"), {}) for n in root.findall("w:num", WORD_NS)}

def docx_paragraph_parts(paragraph):
    """The text of a paragraph with its formulas in place, its formulas, and its pictures."""
    pieces, formulas, pictures = [], [], []
    for node in paragraph.iter():
        name = local_name(node.tag)
        if name == "t" and node.tag.startswith("{%s}" % WORD_NS["w"]):
            pieces.append(node.text or "")
        elif name in ("tab", "br") and node.tag.startswith("{%s}" % WORD_NS["w"]):
            pieces.append(" ")
        elif name == "omath":
            formulas.append(node)
            pieces.append(" %s " % math_to_linear(node))
        elif name in ("drawing", "pict"):
            pictures.append(node)
    return "".join(pieces), formulas, pictures

def docx_figure(picture, related, locator, state):
    """A picture in a Word file as a figure block with the fingerprint of the embedded image,
    and the words in it where OCR is installed."""
    description = next((n.get("descr") or n.get("title") or n.get("name") or "" for n in picture.iter()
                        if local_name(n.tag) == "docpr"), "")
    fingerprint, words = "", ""
    for node in picture.iter():
        for key, value in node.attrib.items():
            if key.startswith("{%s}" % WORD_NS["r"]) and value in related:
                fingerprint, words = sha256_bytes(related[value]), read_picture(related[value], state)
    fingerprint = fingerprint or sha256_bytes(ElementTree.tostring(picture))
    said = (description or "Picture without a description") + words
    return new_block("figure", said, locator, image_sha256=fingerprint, display=said)

def safe_xml(data):
    """Parse one XML part of an Office file. Any document-type declaration is removed first,
    so no entity can be defined inside the file (no entity expansion, no outside fetch)."""
    text = re.sub(rb"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", b"", data, flags=re.S | re.I)
    return ElementTree.fromstring(text)

def note_blocks(archive, file_name):
    """The footnotes and endnotes of a Word file, which are parts of their own and are not in
    the run of paragraphs a plain reader walks. Real documentation puts definitions, caveats and
    parameter values in a footnote routinely, and a reader that takes the body and not the notes
    reports a statement as undocumented when its documentation is two lines below the text.
    They are read after the body, each saying which note it is. Enforces: R13"""
    found = []
    for part, kind in (("word/footnotes.xml", "footnote"), ("word/endnotes.xml", "endnote")):
        if part not in archive.namelist():
            continue
        try:
            root = safe_xml(archive.read(part))
        except ElementTree.ParseError:
            continue
        for note in root:
            if (note.get("{%s}type" % WORD_NS["w"]) or "") in ("separator", "continuationSeparator", "continuationNotice"):
                continue                                 # the rule Word draws above a footnote, not a note
            number = note.get("{%s}id" % WORD_NS["w"]) or "?"
            for position, paragraph in enumerate(note.findall("w:p", WORD_NS), start=1):
                text = normalise_text("".join(run.text or "" for run in paragraph.iter("{%s}t" % WORD_NS["w"])))
                if text:
                    found.append(new_block("paragraph", text, "%s %s %s paragraph %d" % (file_name, kind, number, position)))
    return found

def blocks_from_docx(data, file_name, state):
    """Body elements in document order, so that tables stay where they are. Heading numbers that
    Word produces automatically are not stored in the file; they are reconstructed by counting
    and marked as reconstructed."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        body = safe_xml(archive.read("word/document.xml")).find("w:body", WORD_NS)
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return [not_read_block(file_name, "the file is not a Word document that can be opened")]
    styles, related = {}, {}
    if "word/styles.xml" in archive.namelist():
        for style in safe_xml(archive.read("word/styles.xml")).findall("w:style", WORD_NS):
            styles[style.get("{%s}styleId" % WORD_NS["w"])] = style
    if "word/_rels/document.xml.rels" in archive.namelist():
        for relation in safe_xml(archive.read("word/_rels/document.xml.rels")):
            target = "word/" + relation.get("Target", "").lstrip("/")
            if relation.get("TargetMode") != "External" and target in archive.namelist():
                related[relation.get("Id")] = archive.read(target)
    blocks, counters, pending_caption = [], [0] * 9, ""
    notes = note_blocks(archive, file_name)
    formats, counts, page, on_page = docx_number_formats(archive), {}, 1, {}
    paged = b"lastRenderedPageBreak" in archive.read("word/document.xml")     # Word noted where its pages ended
    for position, element in enumerate(body, start=1):
        locator, name = "body element %d" % position, local_name(element.tag)
        if name == "tbl":
            rows = []
            for row in element.findall("w:tr", WORD_NS):
                rows.append([normalise_text(docx_paragraph_parts(cell)[0]) for cell in row.findall("w:tc", WORD_NS)])
            blocks.append(table_from_rows(rows, locator, pending_caption))
            pending_caption = ""
            continue
        if name != "p":
            continue
        level, numbered, style_name = docx_paragraph_facts(element, styles)
        text, formulas, pictures = docx_paragraph_parts(element)
        text = normalise_text(text)
        if style_name.lower() == "caption":
            if blocks and blocks[-1]["type"] in ("figure", "table", "equation") and not blocks[-1]["caption"]:
                blocks[-1]["caption"] = text
            else:
                pending_caption = text
            continue
        for picture in pictures:
            blocks.append(docx_figure(picture, related, locator, state))
        if level is not None and text:
            block = new_block("heading", text, locator, level_hint=level)
            if numbered and not first_numbering(text, state.rules)[0]:
                counters[level - 1] += 1
                counters[level:] = [0] * (9 - level)
                block["numbering"] = ".".join(str(c) for c in counters[:level] if c)
                block["reconstructed"] = True
            blocks.append(block)
        elif formulas and not normalise_text(re.sub(r"\s+", " ", text.replace(math_to_linear(formulas[0]), ""))):
            equation = read_equation("omml", math_to_linear(formulas[0]), state.notation)
            blocks.append(new_block("equation", equation.linear or text, locator, equation=equation))
        elif text:
            page += sum(1 for node in element.iter() if local_name(node.tag) == "lastrenderedpagebreak")
            shape = formats.get(numbered[0], {}).get(numbered[1], "") if numbered else ""
            if numbered and shape != "bullet" and "bullet" not in style_name.lower():
                counts[numbered] = counts.get(numbered, 0) + 1            # Word counts the items; the file does not hold the numbers
                counts.update({key: 0 for key in counts if key[0] == numbered[0] and key[1] > numbered[1]})
                written = chr(96 + counts[numbered]) if shape == "lowerLetter" and counts[numbered] < 27 else str(counts[numbered])
            if numbered and (shape == "bullet" or "list" in style_name.lower() or "bullet" in style_name.lower()):
                marker = "  " * int(numbered[1]) + (LIST_MARKER if shape == "bullet" or "bullet" in style_name.lower() else written + ". ")
                blocks.append(new_block("list_item", text, locator, marker=marker))
                continue
            on_page[page] = on_page.get(page, 0) + 1
            label = written + "." if numbered else "p.%d \u00b6%d" % (page, on_page[page]) if paged else ""
            blocks.append(new_block("paragraph", text, locator, numbering=label, reconstructed=bool(numbered)))
    if notes:
        blocks.append(new_block("heading", NOTES_HEADING, "%s notes" % file_name, level_hint=1))
        blocks.extend(notes)
    return blocks

# ---------------------------------------------------------------- .pdf
MATH_CHARACTERS = set("=+\u2212\u00d7\u00f7\u2211\u221a\u222b^/\u2264\u2265\u2248()") | set(GREEK.values())

BULLET = re.compile(r"^(?:[\u2022\u25aa\u25cf\u25e6\u2023\u2043\u2013\u2014*o-]|\(cid:\d+\))\s+(?=\S)")

def pdf_lines(document, file_name):
    """Every line, table and picture of a PDF in reading order, each with its page, its place on
    the page, and whether it sits in the top or bottom margin ("edge")."""
    lines = []
    for number, page in enumerate(document.pages, start=1):
        edge = lambda top, bottom: "top" if bottom < 0.12 * page.height else "bottom" if top > 0.88 * page.height else ""
        tables = page.find_tables()
        for table in tables:
            rows = [[normalise_text(cell or "") for cell in row] for row in table.extract()]
            lines.append({"page": number, "top": table.bbox[1], "table": rows, "edge": ""})
        for count, image in enumerate(page.images, start=1):
            mark = "%s page %d picture %d %s" % (file_name, number, count, image.get("srcsize"))
            lines.append({"page": number, "top": image["top"], "figure": sha256_text(mark), "text": "picture %s" % (image.get("srcsize"),),
                          "edge": edge(image["top"], image["bottom"]), "box": (image["x0"], image["top"], image["x1"], image["bottom"])})
        for line in page.extract_text_lines():
            inside = any(t.bbox[0] <= line["x0"] and line["top"] >= t.bbox[1] and line["bottom"] <= t.bbox[3] for t in tables)
            if inside or not line["text"].strip():
                continue
            sizes = sorted(char["size"] for char in line["chars"])
            bold = sum(1 for char in line["chars"] if "bold" in char.get("fontname", "").lower()) > len(line["chars"]) / 2
            lines.append({"page": number, "top": line["top"], "bottom": line["bottom"], "text": line["text"].strip(),
                          "size": sizes[len(sizes) // 2], "bold": bold, "edge": edge(line["top"], line["bottom"])})
    return sorted(lines, key=lambda entry: (entry["page"], entry["top"]))

def blocks_from_pdf(data, file_name, state):
    """PDF keeps no structure, so this reader is the weakest (the manual recommends .docx where
    both exist). With pdfplumber it works from where each line sits and how it is set: page
    headers and footers are left out; a heading is a short line set larger or bolder than the
    body, numbered or not; a line opening with a bullet is a list item; a sentence running over a
    page break is joined again; tables are single blocks; pictures are Figure blocks, read by OCR
    where installed; lines dense in mathematical characters are unread Equation blocks. A paragraph
    is labelled with its page and place ("p.4 \u00b62"), which is how a person finds it in a PDF.
    With only pypdf: text and numbering alone. With neither: one block that could not be read."""
    try:
        import pdfplumber
    except ImportError:
        return blocks_from_pdf_text_only(data, file_name, state)
    blocks, open_block, on_page = [], None, {}
    with pdfplumber.open(io.BytesIO(data)) as document:
        lines = without_page_furniture(pdf_lines(document, file_name), len(document.pages), state, file_name)
        sizes = sorted(entry["size"] for entry in lines if "size" in entry)
        body_size = sizes[len(sizes) // 2] if sizes else 10.0
        numbered = any("size" in entry and first_numbering(entry["text"], state.rules)[0] for entry in lines)
        for entry in lines:
            locator = "page %d" % entry["page"]
            if "table" in entry:
                blocks.append(table_from_rows(entry["table"], locator))
            elif "figure" in entry:
                words = picture_words(document.pages[entry["page"] - 1], entry["box"], state)
                said = "Picture on page %d" % entry["page"]
                blocks.append(new_block("figure", said + words, locator, image_sha256=entry["figure"], display=said + words))
            if "size" not in entry:
                open_block = None
                continue
            text, bullet = entry["text"], BULLET.match(entry["text"])
            dense = sum(1 for char in text if char in MATH_CHARACTERS) / max(1, len(text.replace(" ", "")))
            stands_out = entry["size"] > body_size * 1.08 or (entry["bold"] and entry["size"] >= body_size * 0.97)
            title = stands_out and not bullet and len(text) < 160 and (
                first_numbering(text, state.rules)[0] or (len(text.split()) <= 14 and text[-1] not in ".,;:"))
            near = open_block and entry["page"] == open_block["page"] and entry["top"] - open_block["bottom"] < 0.7 * entry["size"]
            over_the_page = open_block and entry["page"] == open_block["page"] + 1 and not title and not bullet \
                and open_block["block"]["type"] != "heading" and open_block["block"]["text"][-1:] not in ".:;?!" and text[:1].islower()
            if title and near and open_block["block"]["type"] == "heading":       # a heading set over two lines
                kind = None
            elif title:
                kind, more = "heading", {"level_hint": None if numbered else -int(round(entry["size"] * 2)) + (0 if entry["size"] > body_size * 1.08 else 1)}
            elif dense > 0.25 and len(text.split()) <= 12:
                kind, more = "equation", {"equation": EquationData("pdf", text, False, UNDECIDED_REASONS[1], "")}
            elif bullet:
                kind, more, text = "list_item", {"marker": LIST_MARKER}, text[bullet.end():]
            elif (near and open_block["block"]["type"] in ("paragraph", "list_item")) or over_the_page:
                kind = None
            else:
                on_page[entry["page"]] = on_page.get(entry["page"], 0) + 1
                kind, more = "paragraph", {"numbering": "p.%d \u00b6%d" % (entry["page"], on_page[entry["page"]])}
            if kind is None:
                open_block["block"]["text"] += " " + text
            else:
                blocks.append(new_block(kind, text, locator, **more))
                open_block = {"block": blocks[-1]} if kind != "equation" else None
            if open_block:
                open_block.update(page=entry["page"], bottom=entry["bottom"])
    return blocks

def blocks_from_pdf_text_only(data, file_name, state):
    """The fallback PDF reader: page texts as paragraphs, when the layout-aware reader cannot open the file."""
    try:
        import pypdf
    except ImportError:
        return [not_read_block(file_name, "no PDF reader is installed, so this file was not read")]
    blocks = []
    for page_number, page in enumerate(pypdf.PdfReader(io.BytesIO(data)).pages, start=1):
        for paragraph in re.split(r"\n\s*\n", page.extract_text() or ""):
            text = normalise_text(paragraph)
            if text:
                kind = "heading" if first_numbering(text, state.rules)[0] and len(text) < 100 else "paragraph"
                blocks.append(new_block(kind, text, "page %d" % page_number))
    return blocks

# ---------------------------------------------------------------- levels, references, chunks



KIND_OF_BLOCK = {"paragraph": "Paragraph", "list_item": "Paragraph", "table": "Table", "figure": "Figure",
                 "equation": "Equation"}
NOTES_HEADING = "Notes"                 # the heading the tool puts above a Word file's footnotes and endnotes
LIST_MARKER = "- "                      # how an item of a bulleted list is shown; a numbered one shows its number

def fold_lists(blocks):
    """A list belongs to the paragraph that introduces it: "We apply the following principles:"
    and its three bullets are one thought, and a bullet alone cannot be traced to anything. So
    the items of a list that follows a paragraph are folded into it, each on its own line behind
    its marker, and are not units. Done here, where blocks become chunks, so that it holds alike
    for XML, Word and PDF. A list that follows anything else (a heading, a table) has no
    paragraph to belong to; its items are whole statements and stay units of their own."""
    folded = []
    for block in blocks:
        into = folded[-1] if folded else None
        if block["type"] != "list_item" or into is None or into["type"] != "paragraph" or into["not_read_reason"]:
            folded.append(block)
        elif block["text"]:
            into["display"] = "%s\n%s%s" % (into.get("display") or into["text"], block.get("marker") or LIST_MARKER, block["text"])
            into["text"] = "%s %s" % (into["text"], block["text"])
    return folded

def blocks_to_chunks(blocks, corner, source_file, first_number, state):
    """Blocks to chunks. A heading is not a chunk of its own: it becomes part of the heading
    chain of everything below it. Paragraph numbers restart under every heading. Enforces: R2, R4"""
    prefix = "C" if corner == "canon" else "D"
    chunks, chain, levels, section_numbering = [], [], [], ""
    carried, empty = [], []                          # (heading block, anything under it yet), and those with nothing
    for block in fold_lists(infer_levels(blocks, state.rules)):
        if block["type"] == "heading":
            while levels and levels[-1] >= block["level"]:
                levels.pop()
                chain.pop()
                # A heading carries its words to the units below it. Where one is popped off the
                # chain with no unit ever placed under it, those words reach nothing at all, and
                # a file read as headings alone would say nothing. Such a heading becomes a unit
                # of its own, so that what it says is still there to be cited. Enforces: R13
                was, under = carried.pop()
                if not under:
                    empty.append(was)
            levels.append(block["level"])
            chain.append(block["text"])
            carried.append((block, False))
            section_numbering = block["numbering"]
            # The number belongs to the heading whether the document wrote it (num="1.") or Word
            # left it to be counted back. Without it a citation to "section 2" can be resolved
            # against nothing, and the number itself reaches no unit at all. Enforces: R13
            if block["numbering"] and not block["text"].startswith(block["numbering"]):
                chain[-1] = "%s %s" % (block["numbering"], block["text"])
            continue
        carried = [(was, True) for was, _ in carried]
        kind = KIND_OF_BLOCK[block["type"]]
        text = block.get("display") or block["text"]
        equation = block["equation"]
        if kind == "Paragraph" and equation is None:
            equation = inline_formula(text, state.notation)
        chunks.append(Chunk(
            ref=make_ref(prefix, first_number + len(chunks)), corner=corner, source_file=source_file,
            kind=kind, level=levels[-1] if levels else 0, heading_chain=tuple(chain), numbering=section_numbering,
            text=text, locator=block["locator"], content_hash=content_hash(text + block.get("image_sha256", "")),
            table=block["table"], equation=equation,
            numbering_reconstructed=bool(chain) and block_is_under_reconstructed(blocks, block),
            caption=block["caption"], not_read_reason=block["not_read_reason"],
            para_label=block["numbering"] if kind == "Paragraph" else ""))
    while carried:                                   # whatever is still on the chain when the file ends
        was, under = carried.pop()
        if not under:
            empty.append(was)
    for block in empty:
        chunks.append(Chunk(
            ref=make_ref(prefix, first_number + len(chunks)), corner=corner, source_file=source_file,
            kind="Paragraph", level=block["level"], heading_chain=(), numbering=block["numbering"],
            text=block["text"], locator=block["locator"],
            content_hash=content_hash(block["text"]), table=None, equation=None,
            numbering_reconstructed=False, caption="", not_read_reason="",
            para_label=block["numbering"]))
    return chunks

def block_is_under_reconstructed(blocks, block):
    """Was the numbering of the heading directly above this block reconstructed by counting?"""
    above = None
    for candidate in blocks:
        if candidate is block:
            break
        if candidate["type"] == "heading":
            above = candidate
    return bool(above and above["reconstructed"])


# ---------------------------------------------------------------- the two steps
def atoms_of_file(data, found, file_name, state, repairs):
    """The smallest pieces of text the file holds, counted straight from the file and NOT from
    the blocks the reader made of it. That independence is the whole point: an account drawn
    from the reader's own output could never show what the reader missed. Enforces: R13"""
    try:
        if found == "docx":
            return atoms_of_docx(zipfile.ZipFile(io.BytesIO(data)), safe_xml, file_name)
        if found == "pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as document:
                return atoms_of_pdf(document, file_name)
        if found == "mhtml":
            message = email.message_from_bytes(data)
            for part in message.walk():
                payload = part.get_payload(decode=True)
                if part.get_content_type() == "text/html" and payload is not None:
                    text = payload.decode(part.get_content_charset() or "utf-8", "replace")
                    return atoms_of_markup(parse_markup(repair_markup(text, file_name, []), file_name, [], tolerant_only=True), file_name, state.rules)
            return []
        if found in ("xml", "html"):
            text = repair_markup(decode_text(data), file_name, [])
            return atoms_of_markup(parse_markup(text, file_name, [], tolerant_only=found == "html"), file_name, state.rules)
        return atoms_of_plain_text(decode_text(data), file_name)
    except Exception:                          # an account that cannot be drawn is written down, never a stopped run
        state.notes.append("%s: the content account could not be drawn for this file." % file_name)
        return []

def read_file_blocks(path, file_name, state, repairs, max_bytes):
    """One input file to blocks, by the format found in its content. Enforces: R6"""
    if os.path.getsize(path) > max_bytes:
        return "too large", [not_read_block(file_name, "the file is larger than the size limit for one input file")]
    with open(path, "rb") as handle:
        data = handle.read()
    state.folder = os.path.dirname(os.path.abspath(path))
    found = detect_format(data, file_name)
    if found in NOT_READ:                    # said in plain words, with a next step; never decoded as text
        state.atoms = [atom("whole file not read", file_name, "")]
        return found, [not_read_block(file_name, "the file is " + NOT_READ[found])]
    if found == "svg":                               # read by the text it holds, as a table or a figure
        state.atoms = []
        return found, svg_blocks(data, file_name, file_name, state)
    if found in CONVERTED:                   # read through markup the walker already reads
        markup, words, how = converted(found, data, file_name)
        state.atoms = atoms_of_plain_text(words, file_name)
        state.notes.append("%s: %s." % (file_name, how))
        return found, blocks_from_markup(markup, file_name, state, repairs)
    state.atoms = atoms_of_file(data, found, file_name, state, repairs)
    if found == "pdf":
        return found, blocks_from_pdf(data, file_name, state)
    if found == "docx":
        return found, blocks_from_docx(data, file_name, state)
    if found == "mhtml":
        return found, blocks_from_mhtml(data, file_name, state, repairs)
    if found in ("xml", "html"):
        return found, blocks_from_markup(decode_text(data), file_name, state, repairs, tolerant_only=found == "html")
    blocks = [new_block("paragraph", part, "paragraph %d" % number)
              for number, part in enumerate(re.split(r"\n\s*\n", decode_text(data)), start=1) if part.strip()]
    return "plain text", blocks

def read_corner(ctx, corner, input_key, label):
    """Read every file of one corner, in file-name order, into chunks numbered in reading order."""
    options = ctx.options
    rules = load_tag_rules(options["inputs"].get("tag_rules"))
    notation = load_notation()
    chunks, repairs, info_rows, accounts, read_as_what = [], [], [], [], []
    root = (options["inputs"].get("roots") or {}).get(input_key)
    for left_out, why in (options["inputs"].get("skipped") or {}).get(input_key, []):
        info_rows.append({"group": label, "item": "%s: left out of the folder" % left_out, "value": "Not read: %s." % why})
    paths = options["inputs"][input_key]
    svgs = {}                                        # every SVG of the corner, by name and by name without .svg
    for path in paths:
        if path.lower().endswith(".svg"):
            svgs.setdefault(os.path.basename(path).lower(), path)
            svgs.setdefault(os.path.splitext(os.path.basename(path))[0].lower(), path)
    consumed = set()
    # documents first, pictures last: a chart an XML refers to is read in place, where the XML puts it,
    # and is not read a second time on its own; one nothing refers to is still read, on its own
    for path in [p for p in paths if not p.lower().endswith(".svg")] + [p for p in paths if p.lower().endswith(".svg")]:
        file_name = os.path.relpath(path, root).replace(os.sep, "/") if root else os.path.basename(path)
        if path in consumed:
            info_rows.append({"group": label, "item": file_name, "value": "Read in place, as part of the document that refers to it."})
            continue
        state = WalkState(dict(rules, read_pictures=ctx.settings.get("read_pictures", True)), notation, {}, {}, [])
        state.settings = ctx.settings
        state.svgs, state.consumed, state.file_name = svgs, consumed, file_name
        try:
            found, blocks = read_file_blocks(path, file_name, state, repairs, int(ctx.settings["max_file_mb"] * 1024 * 1024))
        except Exception as problem:                 # a file that breaks a reader is named, never a stopped run (R2)
            found, blocks = "unreadable", [not_read_block(file_name, reason_for(problem))]
            state.atoms, state.blocks = [atom("whole file not read", file_name, "")], []
        read_as_what.append((file_name, found, blocks[0].get("not_read_reason", "") if len(blocks) == 1 else ""))
        new_chunks = blocks_to_chunks(blocks, corner, file_name, len(chunks) + 1, state)
        chunks.extend(new_chunks)
        plain = [to_plain(chunk) for chunk in new_chunks]
        for tag in sorted(state.guided):
            info_rows.append({"group": label, "item": "%s: how it was read" % file_name,
                              "value": "<%s> was read as %s on the model's proposal." % (tag, state.guided[tag])})
        found_account = account(file_name, state.atoms, plain, state.dropped,
                                        marks_of_rendering(plain)
                                        + [LIST_MARKER] * (len(plain) + 1) + [NOTES_HEADING],
                                        os.path.getsize(path) if os.path.isfile(path) else 0)
        accounts.append(found_account)
        info_rows.extend({"group": label, "item": "%s: content account" % file_name, "value": line}
                         for line in account_lines(found_account))
        counts = {}
        for chunk in new_chunks:
            counts[chunk.kind] = counts.get(chunk.kind, 0) + 1
        summary = ", ".join("%d %s" % (counts[kind], kind.lower() + ("s" if counts[kind] != 1 else ""))
                            for kind in CHUNK_KINDS if kind in counts) or "nothing could be read"
        info_rows.append({"group": label, "item": file_name, "value": "Read as %s: %d units (%s)"
                          % (FORMAT_NAMES.get(found, found), len(new_chunks), summary)})
        info_rows.extend({"group": label, "item": "%s: reading note" % file_name, "value": note} for note in state.notes)
        for tag in sorted(state.unknown_tags):
            seen = state.unknown_tags[tag]
            because = ", because it %s" % seen["reason"] if seen.get("reason") else ""
            info_rows.append({"group": label, "item": "%s: unrecognised tag" % file_name, "value":
                              "Unrecognised tag '%s', %d times, read as %s%s. "
                              "It can be added to Inputs/tag_rules.yaml."
                              % (tag, seen["count"], seen.get("family") or seen.get("read_as"), because)})
    kind = "chunks_canon" if corner == "canon" else "chunks_doc"
    unreadable = sum(1 for chunk in chunks if chunk.kind == "Equation" and not chunk.equation.readable)
    messages = ["%d units read from %d file(s)." % (len(chunks), len(options["inputs"][input_key]))]
    read_as = {}
    for _, found, _ in read_as_what:
        if found in FORMAT_NAMES:
            read_as[FORMAT_NAMES[found]] = read_as.get(FORMAT_NAMES[found], 0) + 1
    if read_as:                                      # what each file was read as, and what was not read and why
        messages.append("Read as: %s." % ", ".join("%d %s" % (count, name) for name, count in sorted(read_as.items())))
    messages.extend("Not read: %s - %s." % (name, why) for name, found, why in read_as_what
                    if why and (found in NOT_READ or found == "unreadable"))
    skipped = (options["inputs"].get("skipped") or {}).get(input_key, [])
    if skipped:
        messages.append("%d file(s) in the folder were left out; Model_Package_Info lists them." % len(skipped))
    if unreadable:
        messages.append("%d equation(s) could not be read." % unreadable)
    open_accounts = [one for one in accounts if not one["closed"]]
    if open_accounts:
        messages.append("The content account is open on %d file(s); Model_Package_Info says what could not be placed."
                        % len(open_accounts))
    return StepResult({kind: chunks, "read_repairs": repairs, "info_rows": info_rows},
                             {"units": len(chunks), "repairs": len(repairs),
                              "content account open on": len(open_accounts)}, messages)

def read_methodology(ctx):
    """Step 02, read-methodology: the canonical methodology into chunks C-0001, C-0002, ..."""
    return read_corner(ctx, "canon", "methodology", "Methodology files")

def read_documentation(ctx):
    """Step 03, read-documentation: the model documentation into chunks D-0001, D-0002, ..."""
    return read_corner(ctx, "doc", "documentation", "Documentation files")


# ================================================================================================
# ---------------------------------------------------------------- the model package, read into units
TEXT_MEMBERS = (".r", ".txt", ".md", ".rd", ".rmd", ".csv", ".tsv", ".yaml", ".yml", ".json", ".html")
PARSER_NAME = "the tool R reader 0.0.1"

class NotParsed(Exception):
    """One R expression that the tool's reader could not read. The message is a plain reason."""

# ---------------------------------------------------------------- safe unpacking and inventory
ARCHIVE_NAMES = (".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".zip")

def is_archive(path):
    """Whether a file of the package folder is an archive holding the package, rather than one
    file of a package that was put there unpacked."""
    return path.lower().endswith(ARCHIVE_NAMES) or (os.path.getsize(path) > 0 and tarfile.is_tarfile(path))

def unpack_zip(zip_path, max_member_bytes):
    """A package delivered as a ZIP, under exactly the limits a tarball is read under: no absolute
    path, no path that climbs out, no link, nothing over the cap, and nothing protected by a
    password. The size checked is the one the archive declares, before anything is expanded.
    Enforces: R6"""
    files, refused = {}, []
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                refused.append((name, "its path leaves the package folder"))
            elif (member.external_attr >> 16) & 0o170000 == 0o120000:
                refused.append((name, "it is a link"))
            elif member.file_size > max_member_bytes:
                refused.append((name, "it is larger than the size limit for one file"))
            elif member.flag_bits & 0x1:
                refused.append((name, "it is protected by a password"))
            else:
                files[name] = archive.read(member)
    return files, refused

def loose_package(paths, root, max_member_bytes):
    """A package put in the folder unpacked - its source folder rather than a built tarball -
    read file by file, under the same size limit. People very often have the one and not the
    other, and until 0.0.2 a folder here stopped the run."""
    files, refused = {}, []
    for path in paths:
        name = os.path.relpath(path, root).replace(os.sep, "/") if root else os.path.basename(path)
        if os.path.getsize(path) > max_member_bytes:
            refused.append((name, "it is larger than the size limit for one file"))
        else:
            with open(path, "rb") as handle:
                files[name] = handle.read()
    return files, refused

def unpack_package(tar_path, max_member_bytes):
    """Read the tarball member by member, into memory, never onto disk by path. A member with
    an absolute path, a path that climbs out with "..", a link, or a size over the cap is
    refused and reported; everything else is returned as {path: bytes}. Enforces: R6"""
    if tar_path.lower().endswith(".zip") and zipfile.is_zipfile(tar_path):
        return unpack_zip(tar_path, max_member_bytes)
    files, refused = {}, []
    with tarfile.open(tar_path, "r:*") as archive:
        for member in archive:
            name = member.name.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
                refused.append((name, "its path leaves the package folder"))
            elif member.issym() or member.islnk():
                refused.append((name, "it is a link"))
            elif member.isfile() and member.size > max_member_bytes:
                refused.append((name, "it is larger than the size limit for one file"))
            elif member.isfile():
                files[name] = archive.extractfile(member).read()
            elif not member.isdir():
                refused.append((name, "it is not a regular file"))
    return files, refused

def strip_top_folder(files):
    """R tarballs hold one top folder named after the package; paths are shown without it."""
    tops = {path.split("/", 1)[0] for path in files if "/" in path}
    if len(tops) == 1 and all("/" in path for path in files):
        return {path.split("/", 1)[1]: data for path, data in files.items()}
    return dict(files)

def read_description(text):
    """The fields of DESCRIPTION (name: value, continuation lines start with white space)."""
    fields, current = {}, None
    for line in text.split("\n"):
        if line[:1] in (" ", "\t") and current:
            fields[current] += " " + line.strip()
        elif ":" in line:
            current, value = line.split(":", 1)
            fields[current.strip()] = value.strip()
    return fields


def is_exported(name, namespace):
    """Is `name` exported by this NAMESPACE (by name, by pattern or as an S3 method)? None when there is no NAMESPACE."""
    if namespace is None:
        return None
    return name in namespace["exports"] or any(re.search(pattern, name) for pattern in namespace["patterns"])

# ---------------------------------------------------------------- the R tokenizer



# ---------------------------------------------------------------- the R parser
@dataclass
class Node:
    """One node of the syntax tree. kind is one of: num, str, name, call, index, binary,
    unary, dollar, ns, function, block, if, for, while, repeat, paren, missing.
    For a call, args[0] is what is called and `names` holds the argument names ("" when the
    argument is positional). For a function, `names` are the formals, args[:-1] their
    defaults (kind "missing" when there is none) and args[-1] the body."""
    kind: str; value: str = ""; args: tuple = (); names: tuple = (); line: int = 0; end_line: int = 0

ASSIGNMENT_SIGNS = ("<-", "<<-", "=", "->", "->>")


# ---------------------------------------------------------------- R code, read by flowR
# flowR reads the package's R code; its syntax tree is turned into the tool's Node, the shape every reader of
# R code here expects. One flowR run reads a whole package, and every source is read once per session.
PARSED = {}                               # R source text -> its top-level expressions

def flowr_answer(folder, target, queries, work, *flags):
    """flowR's answer to `queries` about `target` - an R file or a folder of them - read from a file: a pipe
    can lose the end of a large answer. An answer too large to read safely is refused before it is read."""
    answer = os.path.join(work, "answer.json")
    with open(answer, "w", encoding="utf-8") as sink:
        subprocess.run([os.path.join(folder, "flowr"), "--no-ansi", *flags, "--default-engine", "tree-sitter",
                        "--engine.r-shell.disabled", "--engine.tree-sitter.wasm-path", os.path.join(folder, "tree-sitter-r.wasm"),
                        "--engine.tree-sitter.tree-sitter-wasm-path", os.path.join(folder, "tree-sitter.wasm"), "--execute",
                        ":query* %s file://%s" % (json.dumps(queries, separators=(",", ":")), target)], stdout=sink, stderr=subprocess.DEVNULL, cwd=work, timeout=900)
    if os.path.getsize(answer) > FLOWR_ANSWER_MAX:
        raise ValueError("flowR's answer is %d MB, too large to read safely" % (os.path.getsize(answer) // 2 ** 20))
    with open(answer, encoding="utf-8") as handle:
        said = handle.read()
    if "{" not in said:
        raise RuntimeError("flowR gave no answer for the package's R code.")
    return json.JSONDecoder().raw_decode(said[said.index("{"):])[0]

def flowr_files(found):
    """The syntax tree of every file in a flowR answer, by path."""
    tree = found["normalized-ast"].get("normalized", found["normalized-ast"]).get("ast")
    return {os.path.normpath(entry["filePath"]): entry["root"] for entry in tree.get("files", [])}

def top_level(root, text):
    """The top-level expressions of one file; one flowR could not give in the tool's shape is 'not read'. Enforces: R2"""
    found = []
    for child in (root or {}).get("children", []):
        try:
            found.append(flowr_node(child))
        except (KeyError, ValueError, TypeError, IndexError) as problem:
            span = (child.get("info") or {}).get("fullRange") or child.get("location") or [1, 0, text.count("\n") + 1, 0]
            found.append(("not read", span[0], span[2], "its syntax tree could not be used (%s)" % problem))
    return found

def flowr_package(files, folder=None):
    """ONE flowR run over the package's R files and NAMESPACE: every R file's syntax tree is kept for
    parse_r_source, and the NAMESPACE is returned as flowR reads it - exported names and export patterns -
    or None when the package has none."""
    folder = folder or flowr_ready()
    with tempfile.TemporaryDirectory(prefix="pkg-") as work:
        root, texts = os.path.join(work, "package"), {}
        for path, data in files.items():
            if path == "NAMESPACE" or path.lower().endswith(".r"):
                target = os.path.normpath(os.path.join(root, path))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                texts[target] = decode_text(data)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write(texts[target])
        try:
            found = flowr_answer(folder, root, [{"type": "files"}, {"type": "normalized-ast"}], work)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):  # too large for one answer: each source is read when asked for
            for path in list(texts):
                if path.lower().endswith(".r"):
                    os.remove(path)
            found = flowr_answer(folder, root, [{"type": "files"}], work)
            found["normalized-ast"] = {"normalized": {"ast": {"files": []}}}
    for path, tree in flowr_files(found).items():
        if path in texts and path.lower().endswith(".r"):
            PARSED[texts[path]] = top_level(tree, texts[path])
    namespace = next((entry["content"]["current"] for entry in found["files"]["files"] if "namespace" in entry.get("roles", [])), None)
    return {"exports": set(namespace["exportedSymbols"]), "patterns": list(namespace["exportedPatterns"])} if namespace else None

def parse_r_sources(sources, folder=None):
    """Read in ONE flowR run every source not read yet this session."""
    todo = [text for text in dict.fromkeys(sources) if text not in PARSED]
    if not todo:
        return
    folder = folder or flowr_ready()
    with tempfile.TemporaryDirectory(prefix="src-") as work:
        root = os.path.join(work, "sources")
        os.makedirs(root)
        names = {}
        for number, text in enumerate(todo):
            names[os.path.normpath(os.path.join(root, "s%05d.R" % number))] = text
            with open(os.path.join(root, "s%05d.R" % number), "w", encoding="utf-8") as handle:
                handle.write(text)
        try:
            trees = flowr_files(flowr_answer(folder, root, [{"type": "normalized-ast"}], work))
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            if len(todo) == 1:
                raise
            for text in todo:                         # too large for one answer: one source at a time
                parse_r_sources([text], folder)
            return
    for path, text in names.items():
        PARSED[text] = top_level(trees[path], text) if path in trees else [("not read", 1, text.count("\n") + 1, "flowR gave no syntax tree for it")]

def parse_r_source(source):
    """The top-level expressions of one R source, as flowR reads them; one that cannot be read becomes
    ("not read", first line, last line, reason) and the rest are still read. Enforces: R2, R7"""
    parse_r_sources([source])
    return PARSED[source]

ARITHMETIC_SIGNS = ("+", "-", "*", "/", "^", "%%", "%/%")
COMPARISON_SIGNS = ("==", "!=", "<", ">", "<=", ">=")
CONSTANT_NAMES = ("TRUE", "FALSE", "NULL", "NA", "NA_integer_", "NA_real_", "NA_character_", "Inf", "NaN",
                  "T", "F", "break", "next", "...")

def flowr_node(n):
    """One flowR node as the tool's Node. Kinds and argument order are those Node documents."""
    kind = n["type"]
    token = kind in ("RSymbol", "RLogical", "RNumber", "RString", "RBreak", "RNext")
    rng = (n.get("location") if token else None) or (n.get("info") or {}).get("fullRange") or n.get("location") or [0, 0, 0, 0]
    line, end = rng[0], rng[2]
    conv = flowr_node
    if kind == "RExpressionList":
        grouping = [g for g in (n.get("grouping") or []) if isinstance(g, dict)]
        children = tuple(conv(c) for c in n.get("children", []))
        if grouping:
            opening, closing = grouping[0], grouping[-1]
            line, end = opening["location"][0], closing["location"][2]
            if opening.get("lexeme") == "(":
                return Node("paren", args=children[:1], line=line, end_line=end)
            return Node("block", args=children, line=line, end_line=end)
        return children[0] if len(children) == 1 else Node("block", args=children, line=line, end_line=end)
    if kind == "RSymbol":
        content = n.get("content", n.get("lexeme", ""))
        if isinstance(content, list):                    # pkg::name comes as [name, package, internal]
            return namespaced(content[1], ":::" if len(content) > 2 and content[2] else "::", str(content[0]), line, end)
        name = str(content)
        written = str(n.get("lexeme", ""))
        if n.get("namespace") or "::" in written:
            return namespaced(n.get("namespace") or written.split(":")[0], ":::" if ":::" in written else "::", name, line, end)
        return Node("name", name, line=line, end_line=end)
    if kind == "RLogical":
        return Node("name", "TRUE" if n.get("content") else "FALSE", line=line, end_line=end)
    if kind == "RNumber":
        return Node("num", n.get("lexeme", ""), line=line, end_line=end)
    if kind == "RString":
        return Node("str", (n.get("content") or {}).get("str", ""), line=line, end_line=end)
    if kind in ("RBreak", "RNext"):
        return Node("name", "break" if kind == "RBreak" else "next", line=line, end_line=end)
    if kind in ("RBinaryOp", "RPipe"):
        op = "|>" if kind == "RPipe" else "^" if n["operator"] == "**" else n["operator"]
        left, right = conv(n["lhs"]), conv(n["rhs"])
        return Node("binary", op, (left, right), line=left.line, end_line=max(end, right.end_line))
    if kind == "RUnaryOp":
        return Node("unary", n["operator"], (conv(n["operand"]),), line=line, end_line=end)
    if kind == "RFunctionDefinition":
        names, defaults = [], []
        for p in n.get("parameters", []):
            names.append(str(p["name"].get("content", p["name"].get("lexeme", ""))))
            default = p.get("defaultValue")
            defaults.append(conv(default) if default else Node("missing", line=p["name"]["location"][0]))
        return Node("function", args=tuple(defaults) + (conv(n["body"]),), names=tuple(names), line=line, end_line=end)
    if kind in ("RFunctionCall", "RAccess"):
        arguments, names = [], []
        for a in (n.get("arguments") if kind == "RFunctionCall" else n.get("access")) or []:
            if not isinstance(a, dict) or a.get("type") != "RArgument" or a.get("value") is None:
                arguments.append(Node("missing", line=line)); names.append(
                    str(a["name"].get("content", a["name"].get("lexeme", ""))) if isinstance(a, dict) and a.get("name") else "")
                continue
            arguments.append(conv(a["value"]))
            names.append(str(a["name"].get("content", a["name"].get("lexeme", ""))) if a.get("name") else "")
        if kind == "RAccess":
            target, op = conv(n["accessed"]), n["operator"]
            if op in ("$", "@"):
                field = arguments[0] if arguments else Node("missing")
                field = Node(field.kind, field.value, line=field.line) if field.kind in ("name", "str") else field
                return Node("dollar", op, (target, field), line=target.line, end_line=end)
            return Node("index", op, (target,) + tuple(arguments), tuple(names), line=target.line, end_line=end)
        if n.get("infixSpecial"):
            return Node("binary", n["functionName"]["content"], tuple(arguments), line=arguments[0].line,
                        end_line=max([end] + [a.end_line for a in arguments]))
        if n.get("named"):
            written = str(n.get("lexeme", ""))
            callee = conv(n["functionName"])
            if "::" in written and callee.kind == "name":
                callee = namespaced(written.split(":")[0], ":::" if ":::" in written else "::", callee.value, callee.line, callee.end_line)
        else:
            callee = conv(n["calledFunction"])
        return Node("call", "(", (callee,) + tuple(arguments), tuple(names), line=callee.line, end_line=end)
    if kind == "RIfThenElse":
        parts = [conv(n["condition"]), conv(n["then"])] + ([conv(n["otherwise"])] if n.get("otherwise") else [])
        return Node("if", args=tuple(parts), line=line, end_line=end)
    if kind == "RForLoop":
        return Node("for", str(n["variable"].get("content", "")), (conv(n["vector"]), conv(n["body"])), line=line, end_line=end)
    if kind == "RWhileLoop":
        return Node("while", args=(conv(n["condition"]), conv(n["body"])), line=line, end_line=end)
    if kind == "RRepeatLoop":
        return Node("repeat", args=(conv(n["body"]),), line=line, end_line=end)
    raise ValueError("flowR node %s is not one the tool reads" % kind)


def namespaced(package, sign, name, line, end):
    """pkg::name as the tool's parser made it: the package, then the name, which carries no end line."""
    return Node("ns", sign, (Node("name", package, line=line, end_line=line), Node("name", name, line=line)), line=line, end_line=end)

def walk(node):
    """Every node of a tree, parents first."""
    yield node
    for child in node.args:
        yield from walk(child)

def callee_name(node):
    """The name of the function a call node calls: f(...) and pkg::f(...) both give "f"."""
    target = node.args[0]
    if target.kind == "ns":
        target = target.args[1]
    return target.value if target.kind in ("name", "str") else ""

def assignment_parts(node):
    """(target, value) when the node is an assignment, whichever arrow it uses; else None."""
    if node.kind != "binary" or node.value not in ASSIGNMENT_SIGNS:
        return None
    left, right = node.args
    return (right, left) if node.value in ("->", "->>") else (left, right)

def number_token(node):
    """A number as written in the code, brought to one form, with its line."""
    written = node.value.rstrip("Li")
    text = str(int(written, 16)) if written.lower().startswith("0x") else written
    parsed = parse_number(text) or {"value": text, "as_written": text, "decimals": 0, "unit": ""}
    parsed.update(as_written=node.value, line=node.line)
    return parsed

def unparse(node):
    """The tree back as short R-like text: used to show defaults and conditions as written."""
    kind, args = node.kind, node.args
    if kind in ("num", "name"):
        return node.value
    if kind == "str":
        return '"%s"' % node.value
    if kind == "missing":
        return ""
    if kind == "paren":
        return "(%s)" % unparse(args[0])
    if kind == "unary":
        return node.value + unparse(args[0])
    if kind in ("binary", "dollar", "ns"):
        tight = kind != "binary" or node.value in ("^", ":")
        return ("%s%s%s" if tight else "%s %s %s") % (unparse(args[0]), node.value, unparse(args[1]))
    if kind in ("call", "index"):
        shown = [("%s = " % name if name else "") + unparse(arg) for name, arg in zip(node.names, args[1:])]
        closer = {"(": ")", "[": "]", "[[": "]]"}[node.value]
        return "%s%s%s%s" % (unparse(args[0]), node.value, ", ".join(shown), closer)
    if kind == "if":
        return "if (%s) %s%s" % (unparse(args[0]), unparse(args[1]), " else " + unparse(args[2]) if len(args) == 3 else "")
    if kind == "function":
        return "function(%s) ..." % ", ".join(node.names)
    return "{ ... }" if kind == "block" else kind

def has_arithmetic(node, function_map, trivial):
    """Does this code compute something: arithmetic, a mathematical function, a comparison with
    a number, or a number that is not on the list of trivial ones? Numbers used as positions
    inside [ ] do not count."""
    positions = set()
    for inner in walk(node):
        if inner.kind == "index":
            positions.update(id(n) for arg in inner.args[1:] for n in walk(arg) if n.kind == "num")
    for inner in walk(node):
        if inner.kind == "function" and inner is not node:
            continue
        if inner.kind == "binary" and inner.value in ARITHMETIC_SIGNS:
            return True
        if inner.kind == "unary" and inner.value == "-" and inner.args[0].kind != "num":
            return True
        if inner.kind == "call" and callee_name(inner) in function_map["r_functions"]:
            return True
        if inner.kind == "binary" and inner.value in COMPARISON_SIGNS and "num" in (inner.args[0].kind, inner.args[1].kind):
            return True
        if inner.kind == "num" and id(inner) not in positions and number_token(inner)["value"] not in trivial:
            return True
    return False

def code_facts(node, skip_inner_functions=True):
    """The functions a piece of code calls and the names it assigns, in order of appearance."""
    calls, written = [], []
    def visit(inner, top):
        if inner.kind == "function" and not top and skip_inner_functions:
            return
        parts = assignment_parts(inner)
        if parts and parts[0].kind in ("name", "str"):
            written.append(parts[0].value)
            visit(parts[1], False)
            return
        if inner.kind == "call":
            name = callee_name(inner)
            if name:
                calls.append(name)
            for arg in (inner.args[1:] if name else inner.args):
                visit(arg, False)
            return
        if inner.kind in ("dollar", "ns"):
            visit(inner.args[0], False) if inner.kind == "dollar" else None
            return
        for child in inner.args:
            visit(child, False)
    visit(node, True)
    unique = lambda values: tuple(dict.fromkeys(values))
    return {"calls": unique(calls), "symbols_written": unique(written)}


# ---------------------------------------------------------------- units from R source
def draft(kind, path, lines, name, text, **more):
    """A unit before it has its reference. References are given at the end, in reading order."""
    unit = {"kind": kind, "file": path, "lines": lines, "name": name, "inside": "", "text": text,
            "parent_key": None, "key": "%s:%s:%s:%s" % (path, lines[0] if lines else 0, kind, name),
            "code": None, "data": None, "roxygen": None, "read_problem": None, "node": None}
    unit.update(more)
    return unit

def code_detail(node, function_map, settings, **more):
    """The facts about a piece of code that later steps use: its calls, what it assigns, what it reads."""
    facts = code_facts(node)
    return dict(facts, formals=(), exported=None, reads_data=(), **more)


def function_units(name, function_node, lines, path, source_lines, context, inside="", parent_key=None):
    """A function, as one unit: what is written inside it is part of it."""
    function_map = context["function_map"]
    formals = tuple((formal, unparse(default)) for formal, default in zip(function_node.names, function_node.args[:-1]))
    detail = code_detail(function_node, function_map, context["settings"], )
    detail.update(formals=formals, exported=is_exported(name, context["namespace"]) if not inside else False)
    unit = draft(KIND_FUNCTION, path, lines, name, "\n".join(source_lines[lines[0] - 1:lines[1]]),
                 inside=inside, parent_key=parent_key, code=detail, node=function_node)
    return [unit]

def statement_units(node, path, source_lines, context, in_tests):
    """The unit(s) of one top-level expression."""
    function_map, lines = context["function_map"], (node.line, node.end_line)
    text = "\n".join(source_lines[lines[0] - 1:lines[1]])
    parts = assignment_parts(node)
    if parts and parts[1].kind == "function" and parts[0].kind in ("name", "str"):
        return function_units(parts[0].value, parts[1], lines, path, source_lines, context)
    if node.kind == "call" and callee_name(node) in ("test_that", "it", "describe") and len(node.args) >= 2:
        label = node.args[1].value if node.args[1].kind == "str" else "test"
        return [draft(KIND_TEST, path, lines, label, text, code=code_detail(node, function_map, context["settings"]), node=node)]
    detail = code_detail(node, function_map, context["settings"])
    if parts and parts[0].kind == "name" and has_arithmetic(parts[1], function_map, context["trivial"]):
        return [draft(KIND_FORMULA, path, lines, parts[0].value, text, code=detail, node=node)]
    kind = KIND_TEST if in_tests and node.kind == "call" and callee_name(node).startswith("expect_") else KIND_TOPLEVEL
    name = parts[0].value if parts and parts[0].kind in ("name", "str") else (callee_name(node) if node.kind == "call" else "")
    return [draft(kind, path, lines, name, text, code=detail, node=node)]

def units_from_r_source(path, source, context, line_offset=0):
    """All units of one R file: roxygen blocks, functions, formula statements, test blocks,
    top-level statements, and a "File not read" unit for each expression that could not be
    parsed. Comment lines are attached to the unit that follows them (or, at the end of the
    file, to the unit before), so every non-blank line lies inside a unit. Enforces: R2"""
    source_lines = source.split("\n")
    units, in_tests = [], path.startswith("tests/")
    parsed = parse_r_source(source)
    for result in parsed:
        if isinstance(result, tuple):
            _, first, last, reason = result
            units.append(draft(KIND_NOT_READ, path, (first, last), "", "\n".join(source_lines[first - 1:last]),
                               read_problem="the tool's R reader could not read this expression: %s" % reason))
        else:
            units.extend(statement_units(result, path, source_lines, context, in_tests))
    units.extend(roxygen_units(path, source_lines, parsed, context))
    units.sort(key=lambda unit: (unit["lines"][0], 0 if unit["kind"] == KIND_ROXYGEN else 1, unit["lines"][1] * -1))
    covered = set()
    for unit in units:
        covered.update(range(unit["lines"][0], unit["lines"][1] + 1))
    top_level = [unit for unit in units if not unit["parent_key"]]
    for number, line in enumerate(source_lines, start=1):
        if line.strip() and number not in covered and top_level:
            after = [unit for unit in top_level if unit["lines"][0] > number]
            owner = after[0] if after else top_level[-1]
            owner["lines"] = (min(owner["lines"][0], number), max(owner["lines"][1], number))
            covered.add(number)
    if not units and source.strip():
        units.append(draft(KIND_TOPLEVEL, path, (1, len(source_lines)), "", source, code=None))
    units = self_contained(units)
    for unit in units:
        if unit["parent_key"] is None or unit["kind"] == KIND_FUNCTION:
            unit["text"] = "\n".join(source_lines[unit["lines"][0] - 1:unit["lines"][1]])
        unit["lines"] = (unit["lines"][0] + line_offset, unit["lines"][1] + line_offset)
    return units

def self_contained(units):
    """Rows that never overlap, each a whole piece of code: what is written inside a function is the
    function's (its statements are taken apart on Model_Implementation_Map, not here); a roxygen block
    is one row with what it documents; and two rows over the same lines are one row."""
    kept = []
    for unit in sorted((u for u in units if not u["parent_key"]), key=lambda u: (u["lines"][0], -u["lines"][1])):
        last = kept[-1] if kept else None
        if last and last["kind"] == KIND_ROXYGEN and unit["kind"] not in (KIND_ROXYGEN, KIND_NOT_READ):
            unit["roxygen"], unit["lines"] = last["roxygen"], (last["lines"][0], unit["lines"][1])
            kept[-1] = unit
        elif last and unit["lines"][0] <= last["lines"][1]:
            if unit["data"] and not last["data"]:            # a stored object keeps what it is
                last["kind"], last["name"] = unit["kind"], unit["name"]
            last["lines"] = (last["lines"][0], max(last["lines"][1], unit["lines"][1]))
            for part in ("data", "roxygen", "code"):
                last[part] = last[part] or unit[part]
        else:
            kept.append(unit)
    return kept

# ---------------------------------------------------------------- roxygen blocks and help pages

def roxygen_units(path, source_lines, parsed, context):
    """Consecutive #' lines form one block. It documents the object that follows: a function,
    a quoted name (a data object), or NULL together with an @name tag."""
    units, number = [], 0
    while number < len(source_lines):
        if not re.match(r"\s*#'", source_lines[number]):
            number += 1
            continue
        first = number
        while number < len(source_lines) and re.match(r"\s*#'", source_lines[number]):
            number += 1
        block_lines = [re.sub(r"^\s*#' ?", "", line) for line in source_lines[first:number]]
        tags, current = [], {"tag": "description", "name": "", "text": "", "line": first + 1}
        for offset, line in enumerate(block_lines):
            found = re.match(r"\s*@(\w+)\s*(.*)", line)
            if found:
                tags.append(current)
                current = {"tag": found.group(1), "name": "", "text": found.group(2).strip(), "line": first + 1 + offset}
                if current["tag"] == "param":
                    pieces = current["text"].split(None, 1)
                    current["name"], current["text"] = (pieces + ["", ""])[0], (pieces + ["", ""])[1]
            else:
                current["text"] = (current["text"] + "\n" + line).strip("\n")
        tags.append(current)
        tags = [tag for tag in tags if tag["tag"] != "description" or tag["text"].strip()]
        follower = next((r for r in parsed if not isinstance(r, tuple) and r.line >= number + 1), None)
        documents = ""
        if follower is not None:
            parts = assignment_parts(follower)
            if parts and parts[0].kind in ("name", "str"):
                documents = parts[0].value
            elif follower.kind == "str":
                documents = follower.value
        documents = documents or next((tag["text"].split()[0] for tag in tags if tag["tag"] == "name" and tag["text"]), "")
        detail = {"documents_ref": None, "documents_name": documents, "tags": tuple(tags)}
        units.append(draft(KIND_ROXYGEN, path, (first + 1, number), documents, "\n".join(source_lines[first:number]),
                           roxygen=detail))
    return units


def vignette_units(path, text, context):
    """A vignette: prose becomes "Vignette text" units, one per stretch between code chunks;
    code chunks are read as R code (and never run)."""
    units, lines, prose_start, number = [], text.split("\n"), 0, 0
    def close_prose(end):
        prose = "\n".join(lines[prose_start:end]).strip()
        if prose:
            units.append(draft(KIND_VIGNETTE, path, (prose_start + 1, end), "", prose))
    while number < len(lines):
        if re.match(r"^```+\s*\{r\b", lines[number]):
            close_prose(number)
            end = number + 1
            while end < len(lines) and not lines[end].startswith("```"):
                end += 1
            units.extend(units_from_r_source(path, "\n".join(lines[number + 1:end]), context, line_offset=number + 1))
            number = prose_start = end + 1
        else:
            number += 1
    close_prose(len(lines))
    return units

# ---------------------------------------------------------------- stored parameter data
COMPRESSION = ((b"\x1f\x8b", "gzip"), (b"BZh", "bzip2"), (b"\xfd7zXZ\x00", "xz"))

def expand(data, cap):
    """Undo gzip, bzip2 or xz compression, recognised from the first bytes and never from the
    extension, and stop when the content grows beyond the cap."""
    method = next((name for magic, name in COMPRESSION if data.startswith(magic)), "none")
    if method == "none":
        return data, method
    opener = {"gzip": lambda: zlib.decompressobj(31), "bzip2": bz2.BZ2Decompressor, "xz": lzma.LZMADecompressor}[method]()
    expanded = opener.decompress(data, cap + 1)
    if len(expanded) > cap:
        raise NotParsed("it expands to more than %d MB, so it was not read; it looks like a dataset" % (cap // 1048576))
    return expanded, method

def cell_text(value):
    """One stored value as its canonical text: numbers as the shortest decimal that gives the
    same stored value back, missing values as NA, logical values as TRUE/FALSE, dates in ISO form."""
    import numpy
    import pandas
    if value is None or value is pandas.NA or value is pandas.NaT:
        return "NA"
    if isinstance(value, (bool, numpy.bool_)):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, numpy.integer)):
        return str(int(value))
    if isinstance(value, (float, numpy.floating)):
        number = float(value)
        if number != number:
            return "NA"
        if number in (float("inf"), float("-inf")):
            return "Inf" if number > 0 else "-Inf"
        return plain_decimal(Decimal(repr(number)))
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)

def table_of(value):
    """A decoded object as a table: (header, rows of canonical cell texts, column types, R-side
    description), or None when the object has no tabular meaning. A data frame keeps its
    columns; a named vector becomes name and value; a matrix keeps its row and column names;
    a list of short values becomes rows of path and value."""
    import numpy
    import pandas
    if isinstance(value, pandas.DataFrame):
        header = [str(column) for column in value.columns]
        rows = [[cell_text(cell) for cell in row] for row in value.itertuples(index=False, name=None)]
        index = list(value.index)
        if index not in (list(range(len(index))), list(range(1, len(index) + 1))):
            header, rows = ["(row name)"] + header, [[cell_text(name)] + row for name, row in zip(index, rows)]
        return header, rows, "data frame"
    if hasattr(value, "dims") and hasattr(value, "coords"):                  # a named vector or matrix
        array = numpy.asarray(value)
        names = [[cell_text(n) for n in numpy.asarray(value.coords[d])] if d in value.coords else None for d in value.dims]
        if array.ndim == 1:
            labels = names[0] or [str(i + 1) for i in range(array.shape[0])]
            return ["name", "value"], [[label, cell_text(cell)] for label, cell in zip(labels, array.tolist())], "named vector"
        if array.ndim == 2:
            columns = names[1] or ["V%d" % (i + 1) for i in range(array.shape[1])]
            labels = names[0] or [str(i + 1) for i in range(array.shape[0])]
            return ["(row name)"] + columns, [[label] + [cell_text(c) for c in row] for label, row in zip(labels, array.tolist())], "matrix"
    if isinstance(value, numpy.ndarray) and value.ndim == 1:
        if value.shape[0] == 1:
            return ["value"], [[cell_text(value.tolist()[0])]], "single value"
        return ["position", "value"], [[str(i + 1), cell_text(c)] for i, c in enumerate(value.tolist())], "vector"
    if isinstance(value, numpy.ndarray) and value.ndim == 2:
        header = ["(row)"] + ["V%d" % (i + 1) for i in range(value.shape[1])]
        return header, [[str(i + 1)] + [cell_text(c) for c in row] for i, row in enumerate(value.tolist())], "matrix"
    if isinstance(value, (dict, list)):
        rows = []
        def flatten(path, inner):
            if isinstance(inner, dict):
                for key in inner:
                    flatten(path + [str(key)], inner[key])
            elif isinstance(inner, list):
                for position, item in enumerate(inner, start=1):
                    flatten(path + [str(position)], item)
            elif isinstance(inner, numpy.ndarray) and inner.ndim == 1 and inner.shape[0] <= 20:
                rows.append(["/".join(path), ", ".join(cell_text(c) for c in inner.tolist())])
            elif isinstance(inner, (str, int, float, bool)) or inner is None:
                rows.append(["/".join(path), cell_text(inner)])
            else:
                raise ValueError("not a short value")
        try:
            flatten([], value)
        except ValueError:
            return None
        return ["path", "value"], rows, "list"
    if isinstance(value, (str, int, float, bool)):
        return ["value"], [[cell_text(value)]], "single value"
    return None


def table_display(header, rows):
    """The one-cell display form: at most 50 rows, always below Excel's limit for one cell."""
    shown = ["; ".join(header)] + ["; ".join(row) for row in rows[:50]]
    if len(rows) > 50:
        shown.append("... %d more rows; the full table is in the audit files" % (len(rows) - 50))
    text = "\n".join(shown)
    return text if len(text) < 30000 else text[:30000] + "\n... (cut here; the full table is in the audit files)"

def data_object_unit(name, value, path, settings):
    """One stored object to a unit and, when it is assessable, its full values."""
    found = table_of(value)
    if found is None:
        described = "An object of Python type %s after decoding; it has no tabular meaning, so it is described and not compared." % type(value).__name__
        detail = {"object_name": name, "container_file": path, "dims": (), "columns": (), "assessable": False,
                  "not_assessable_reason": "it is not a table, a vector or a list of short values"}
        return draft(KIND_OBJECT, path, None, name, described, data=detail), None
    header, rows, shape = found
    n_cells = len(rows) * len(header)
    too_large = n_cells > settings["max_parameter_cells"] or len(header) > settings["max_parameter_columns"]
    reason = "too large to be a parameter table (%d cells); it looks like a dataset" % n_cells if too_large else None
    detail = {"object_name": name, "container_file": path, "dims": (len(rows), len(header)), "columns": tuple(header),
              "assessable": not too_large, "not_assessable_reason": reason}
    kind = KIND_OBJECT if shape == "list" else KIND_TABLE
    unit = draft(kind, path, None, name, table_display(header, rows), data=detail)
    return unit

def decode_data_file(path, data, settings):
    """Decode one stored-data file without R. The file is parsed by `rdata`, which evaluates
    nothing; a function or another language object inside it is described, never called.
    Returns (units, the fact for Model_Package_Info). Enforces: R7"""
    cap = int(settings["max_file_mb"] * 1024 * 1024)
    stem = os.path.splitext(os.path.basename(path))[0]
    if path.lower().endswith((".csv", ".tsv")):
        delimiter = "\t" if path.lower().endswith(".tsv") else ","
        table = [row for row in csv.reader(io.StringIO(decode_text(data)), delimiter=delimiter) if row]
        frame_header, frame_rows = (table[0], table[1:]) if table else ([], [])
        return [data_object_unit_from_rows(stem, frame_header, frame_rows, path, settings)], "%s: text table" % path
    try:
        raw, method = expand(data, cap)
        import rdata
        container = "several objects (.rda)" if raw[:3] in (b"RDX", b"RDA") else "one object (.rds)"
        body = raw[5:] if raw[:3] in (b"RDX", b"RDA") else raw
        layout = {b"X": "binary", b"A": "ASCII", b"B": "native binary"}.get(body[:1], "unknown")
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            converted = rdata.conversion.convert(rdata.parser.parse_data(raw))
        decoded_by = "rdata %s" % rdata.__version__
    except Exception as problem:                                   # any failure means: not decoded, never lost
        reason = str(problem) if isinstance(problem, NotParsed) else "the file could not be decoded as R data"
        unit = draft(KIND_NOT_READ, path, None, stem, "", read_problem="This data file was not read: %s." % reason)
        return [unit], "%s: not decoded (%s)" % (path, type(problem).__name__ if not isinstance(problem, NotParsed) else reason)
    objects = converted if container.startswith("several") and isinstance(converted, dict) else {stem: converted}
    units = [data_object_unit(str(name), objects[name], path, settings) for name in objects]
    fact = "%s: %s, %s layout, %s compression, %d object(s), decoded by %s" % (path, container, layout, method, len(units), decoded_by)
    return units, fact

def data_object_unit_from_rows(name, header, rows, path, settings):
    """A unit for a table given as header and rows (delimited text files under data/ or inst/extdata/)."""
    import pandas
    width = len(header)
    frame = pandas.DataFrame([list(row) + [""] * (width - len(row)) for row in rows], columns=header)
    return data_object_unit(name, frame, path, settings)

# ---------------------------------------------------------------- which code reads which data
def data_reads(function_node, formals, data_names, data_files):
    """Where a function reads stored data, and how the code shows it: a bare symbol that is
    neither an argument nor assigned in the function; data("x"); readRDS(...) or load(...) with
    a literal file name; pkg::x; get("x"). Column and row key are recorded when the syntax
    shows them, as in floors$lgd_floor or floors[floors$segment == "Retail", "lgd_floor"]."""
    written = set(code_facts(function_node)["symbols_written"]) | set(formals)
    reads = {}
    def note(name, how, column="", row_key=""):
        entry = reads.setdefault(name, {"object": name, "how": how, "column": "", "row_key": ""})
        entry["column"], entry["row_key"] = entry["column"] or column, entry["row_key"] or row_key
    for node in walk(function_node):
        if node.kind == "name" and node.value in data_names and node.value not in written:
            note(node.value, "bare symbol")
        elif node.kind == "ns" and node.args[1].value in data_names:
            note(node.args[1].value, "package::name")
        elif node.kind == "call" and callee_name(node) in ("data", "get", "readRDS", "load"):
            for inner in walk(node):
                if inner.kind in ("str", "name") and inner is not node.args[0]:
                    stem = os.path.splitext(os.path.basename(inner.value))[0]
                    if inner.value in data_names:
                        note(inner.value, '%s("%s")' % (callee_name(node), inner.value))
                    elif inner.kind == "str" and stem in data_files:
                        for name in data_files[stem]:
                            note(name, "%s() of the file %s" % (callee_name(node), os.path.basename(inner.value)))
        if node.kind == "dollar" and node.args[0].kind == "name" and node.args[0].value in reads:
            note(node.args[0].value, "", column=node.args[1].value)
        if node.kind == "index" and node.args[0].kind == "name" and node.args[0].value in reads:
            literals = [inner.value for arg in node.args[1:2] for inner in walk(arg) if inner.kind == "str"]
            columns = [arg.value for arg in node.args[2:3] if arg.kind == "str"]
            note(node.args[0].value, "", column=columns[0] if columns else "", row_key=literals[0] if literals else "")
    return tuple(reads[name] for name in sorted(reads))

# ---------------------------------------------------------------- step 04: read-package
DATA_EXTENSIONS = (".rda", ".rdata", ".rds")

def is_data_file(path):
    """Does this path name a stored-data file that the tool decodes?"""
    lowered = path.lower()
    if lowered.endswith(DATA_EXTENSIONS):
        return True
    return lowered.endswith((".csv", ".tsv")) and lowered.split("/")[0] in ("data", "inst")

def is_parsed_r_file(path):
    """Is this an R source file in a folder whose code the tool parses?"""
    return path.lower().endswith(".r") and path.lower().split("/")[0] in ("r", "tests", "data", "inst", "data-raw", "demo")


def file_units(path, data, context, facts, reader=""):
    """The units of one file of the package, by where it lies and what it is. A reader chosen
    for this member overrides only where the built-in tests give none."""
    lowered = path.lower()
    if reader and not is_data_file(path) and not lowered.startswith("src/"):
        text = decode_text(data) if b"\x00" not in data[:4096] else None
        if text is not None:
            if reader == "r-source":
                return units_from_r_source(path, text, context)
            if reader == "help-page":                 # generated from the roxygen comments, which are read
                facts["help pages"].append(path)
                return []
            if reader == "vignette":
                return vignette_units(path, text, context)
            if reader in ("r-data", "table-file"):
                units, fact = decode_data_file(path, data, context["settings"])
                facts["data"].append(fact)
                return units
    if is_data_file(path):
        units, fact = decode_data_file(path, data, context["settings"])
        facts["data"].append(fact)
        return units
    if lowered.startswith("src/"):
        return [draft(KIND_COMPILED, path, None, os.path.basename(path), "",
                      read_problem="Compiled code is not read by the tool; it needs a manual review.")]
    text = decode_text(data) if b"\x00" not in data[:4096] else None
    if text is None:
        return [draft(KIND_NOT_READ, path, None, os.path.basename(path), "",
                      read_problem="A binary file of a kind the tool does not know; it needs a manual review.")]
    if is_parsed_r_file(path):
        return units_from_r_source(path, text, context)
    if lowered.endswith(".rd") and lowered.startswith("man/"):   # a help page repeats the roxygen comments in the R files
        facts["help pages"].append(path)
        return []
    if lowered.endswith((".rmd", ".rnw", ".qmd")):
        return vignette_units(path, text, context)
    return [draft(KIND_OTHER, path, (1, text.count("\n") + 1), os.path.basename(path), text[:2000])]

def link_documentation_units(units):
    """Tie each roxygen block to the object it documents."""
    by_name = {}
    for unit in units:
        if unit["kind"] in (KIND_FUNCTION, KIND_TABLE, KIND_OBJECT) and not unit["inside"]:
            by_name.setdefault(unit["name"], unit)
    for unit in units:
        if unit["roxygen"]:                               # a block, or the object it is one row with
            target = by_name.get(unit["roxygen"]["documents_name"])
            unit["roxygen"]["documents_ref"] = target["key"] if target else None

def finalise_units(drafts, file_hashes):
    """Give every draft its reference, in reading order, and turn keys into references."""
    refs = {unit["key"]: make_ref("M", number) for number, unit in enumerate(drafts, start=1)}
    units = []
    for unit in drafts:
        if unit["roxygen"] and unit["roxygen"]["documents_ref"]:
            unit["roxygen"]["documents_ref"] = refs.get(unit["roxygen"]["documents_ref"])
        units.append(ModelUnit(
            ref=refs[unit["key"]], kind=unit["kind"], file=unit["file"], lines=unit["lines"], name=unit["name"],
            inside=unit["inside"], text=unit["text"], parent_ref=refs.get(unit["parent_key"]),
            file_sha256=file_hashes[unit["file"]], content_hash=content_hash(unit["text"]),
            code=CodeDetail(**unit["code"]) if unit["code"] else None,
            data=ParameterDataDetail(**unit["data"]) if unit["data"] else None,
            roxygen=RoxygenDetail(**unit["roxygen"]) if unit["roxygen"] else None,
            read_problem=unit["read_problem"]))
    return units, refs

def package_rows(description, namespace, units, facts, refused):
    """The package lines of Model_Package_Info."""
    rows = [("Package", "Name", description.get("Package", "not stated")),
            ("Package", "Version", description.get("Version", "not stated")),
            ("Package", "Title", description.get("Title", "")), ("Package", "Parser", PARSER_NAME)]
    counts = {}
    for unit in units:
        counts[unit.kind] = counts.get(unit.kind, 0) + 1
    rows.extend(("Package", "Units of kind %s" % kind, counts[kind]) for kind in UNIT_KINDS if kind in counts)
    exported = sorted(u.name for u in units if u.kind == KIND_FUNCTION and u.code and u.code.exported)
    rows.append(("Package", "Exported functions", ", ".join(exported) or "none found"))
    if facts["help pages"]:
        rows.append(("Package", "Help pages not read", "%d in man/: generated from the roxygen comments in the R files, which are read"
                     % len(facts["help pages"])))
    rows.extend(("Package data", "Data file", fact) for fact in facts["data"])
    rows.extend(("Package data", "Not assessed", "%s (%s): %s" % (u.ref, u.name, u.data.not_assessable_reason))
                for u in units if u.data and not u.data.assessable)
    rows.extend(("Package", "Could not be read", "%s %s lines %s" % (u.ref, u.file, "-".join(str(n) for n in u.lines or ())))
                for u in units if u.kind == KIND_NOT_READ)
    rows.extend(("Package", "Member of the tarball refused", "%s: %s" % entry) for entry in refused)
    return [{"group": group, "item": item, "value": value} for group, item, value in rows if value != ""]


def read_package(ctx):
    """Step 04, read-package. Files are taken in a fixed order (DESCRIPTION, NAMESPACE, R/,
    data, man/, tests/, vignettes/, the rest; by name inside each), so references are stable
    for an unchanged tarball. Enforces: R2, R5"""
    tarballs = ctx.options["inputs"]["package"]
    if not tarballs:
        return StepResult({}, {"units": 0}, ["No package was found in Inputs/2_Model_Package."])
    limit, root = int(ctx.settings["max_file_mb"] * 1024 * 1024), (ctx.options["inputs"].get("roots") or {}).get("package")
    archives = [path for path in tarballs if is_archive(path)]
    try:
        files, refused = unpack_package(archives[0], limit) if archives else loose_package(tarballs, root, limit)
    except Exception as problem:                     # a package that cannot be opened is named, never a stopped run (R2)
        return StepResult({}, {"units": 0}, ["The package could not be opened: %s." % reason_for(problem)])
    tarballs = archives or tarballs
    files = strip_top_folder(files)
    function_map = yaml.safe_load(R_FUNCTION_MAP_YAML)
    description = read_description(decode_text(files["DESCRIPTION"])) if "DESCRIPTION" in files else {}
    namespace = flowr_package(files)
    context = {"function_map": function_map, "notation": function_map["notation"], "namespace": namespace,
               "trivial": set(ctx.settings["trivial_numbers"]), "settings": ctx.settings}
    order = ("description", "namespace", "r", "data", "inst", "man", "tests", "vignettes")
    def rank(path):
        top = path.split("/")[0].lower()
        return (order.index(top) if top in order else len(order), path)
    chosen, plan_notes = {}, []
    drafts, facts = [], {"data": [], "help pages": []}
    for path in sorted(files, key=rank):
        drafts.extend(file_units(path, files[path], context, facts, chosen.get(path, "")))
    data_names = {unit["name"] for unit in drafts if unit["data"]}
    data_files = {}
    for unit in drafts:
        if unit["data"]:
            data_files.setdefault(os.path.splitext(os.path.basename(unit["file"]))[0], []).append(unit["name"])
    for unit in drafts:
        if unit["kind"] == KIND_FUNCTION:
            formals = [name for name, _ in unit["code"]["formals"]]
            unit["code"]["reads_data"] = data_reads(unit["node"], formals, data_names, data_files)
    link_documentation_units(drafts)
    hashes = {path: sha256_bytes(data) for path, data in files.items()}
    units, refs = finalise_units(drafts, hashes)
    inventory = [{"file": path, "bytes": len(files[path]), "sha256": hashes[path], "swhid": swhid_content(files[path])}
                 for path in sorted(files)]
    for entry in inventory:                              # for identity part 3: the lines that must lie inside a unit
        if is_parsed_r_file(entry["file"]):
            lines = decode_text(files[entry["file"]]).split("\n")
            entry["nonblank_lines"] = [number for number, line in enumerate(lines, start=1) if line.strip()]
    info = {"name": description.get("Package", ""), "version": description.get("Version", ""), "parser": PARSER_NAME,
            "tarball": os.path.basename(tarballs[0]), "files": inventory,
            "rows": package_rows(description, namespace, units, facts, refused)}
    messages = ["%d units read from %d files of the package." % (len(units), len(files))]
    r_files = sum(1 for path in files if path.lower().endswith(".r"))
    other_code = sum(1 for path in files if path.lower().endswith((".py", ".sas", ".m", ".jl", ".scala", ".java", ".cpp", ".c")))
    is_r_package = ("DESCRIPTION" in files and "Package:" in decode_text(files["DESCRIPTION"])) or (r_files and r_files >= other_code)
    if not is_r_package:                             # a DESCRIPTION naming the package, or more R than any other code
        # Found on a real run: an R package that keeps its code in one file beside many help pages
        # was called "not an R package" because R files were under a tenth of all its files.
        # the tool's reader of code reads R and nothing else. A model in Python, SAS or MATLAB comes
        # through as files of running text, fully accounted for and impossible to check - so the
        # analyst is told plainly, rather than left to wonder why nothing was linked. Enforces: R2
        note = ("This does not look like an R package (%s). The tool reads the code of R packages only: files in any "
                "other language are kept as running text and nothing in them can be linked or checked."
                % ("it has no DESCRIPTION file" if "DESCRIPTION" not in files else "%d of its %d files are R code" % (r_files, len(files))))
        messages.append(note)
        info["rows"].append({"group": "The package", "item": "what kind of package", "value": note})
    if len(tarballs) > 1:
        messages.append("More than one tarball was found; only %s was read." % os.path.basename(tarballs[0]))
    plain_units = [to_plain(unit) for unit in units]
    account = account_of_package(files, plain_units, refused, lambda path: is_parsed_r_file(path) or os.path.splitext(path)[1].lower() in TEXT_MEMBERS or "/" not in path,
                                 dropped=set(facts["help pages"]))
    info["rows"].extend({"group": "The package", "item": "content account", "value": line}
                        for line in account_lines(account))
    if not account["closed"]:
        messages.append("The content account of the package is open; Model_Package_Info says what could not be placed.")
    info["rows"].extend({"group": "The package", "item": "how it was read", "value": note} for note in plan_notes)
    return StepResult({"model_units": units, "package_info": [info],
                              },
                             {"units": len(units), "files": len(files), "members refused": len(refused)}, messages)

# ---------------------------------------------------------------- the data flow of a package: the implementation map's backbone
# Every function traced by code alone: each value it sets and the values it is computed from; each call,
# with which argument went to which parameter there; each column a dplyr verb creates and from what; the
# stored tables, files and hard-coded numbers everything comes from. What code cannot follow - a lambda
# purrr applies, do.call over a list built at run time, eval, <<-, an object system - is a named gap with
# its code, for the agents. Nothing here is guessed, and the units are not touched: this is a record of its
# own, so every M- reference stays as it was. Enforces: R2, R4, R7
DPLYR_CREATE = {"mutate", "transmute", "summarise", "summarize", "reframe"}
DPLYR_JOIN = {"left_join", "inner_join", "right_join", "full_join", "semi_join", "anti_join"}
DPLYR_MASKING = DPLYR_CREATE | DPLYR_JOIN | {"filter", "select", "arrange", "group_by", "rename", "distinct", "count", "pull",
                                              "case_when", "if_else", "slice", "relocate", "summarise_at", "with", "within", "subset", "transform"}
FILE_READERS = {"read.csv", "read.csv2", "read.table", "read.delim", "readRDS", "read_csv", "read_csv2", "read_tsv", "read_delim",
                "read_excel", "read_xlsx", "read_xls", "fread", "load", "scan", "readLines", "read_rds", "read_parquet", "fromJSON", "read_yaml"}
APPLIERS = {"map", "map_dbl", "map_chr", "map_int", "map_lgl", "map_df", "map_dfr", "map_dfc", "map2", "map2_dbl", "pmap", "imap", "walk",
            "reduce", "keep", "discard", "lapply", "sapply", "vapply", "mapply", "Map", "Reduce", "Filter", "apply", "tapply", "outer"}
OPAQUE_CALLS = {"do.call": "do.call over arguments built at run time", "eval": "code built at run time and evaluated",
                "evalq": "code built at run time and evaluated", "parse": "code built from text at run time",
                "get": "a value looked up by a name built at run time", "mget": "values looked up by names built at run time",
                "assign": "a value stored under a name built at run time", "match.fun": "a function chosen at run time",
                "UseMethod": "a function chosen by the class of its argument at run time", "NextMethod": "a function chosen by class at run time",
                "setRefClass": "an object system (reference classes)", "R6Class": "an object system (R6)", "setClass": "an object system (S4)",
                "setMethod": "an object system (S4 methods)", "local": "code run in an environment of its own"}

# ---------------------------------------------------------------- flowR: the program the data flow is read with
# flowR (Sihler and Tichy, Ulm University; GPLv3) parses R with tree-sitter and tells, for every name, the
# definition it reads, for every call, the function it calls, and for every argument, the parameter it becomes.
# It is fetched once, verified against the pinned SHA-256, and run in one-shot mode: no R process, no server,
# no open port, no network. Its answer is written to a file - through a pipe it stops at 128 KiB.
ELEMENT_MAKERS = ("list", "c", "data.frame", "tibble", "data.table")   # a named argument here is an element, a value of its own
FLOWR_VERSION = "2.15.8"
FLOWR_SHA256 = "39e1b9e5e4fab67f76204dbf6856d32e9e7f2a36132b1323e02cc8e3392436e4"
FLOWR_URL = "https://github.com/flowr-analysis/flowr-r-adapter/releases/download/flowr-v{0}/flowr-{0}-linux-x64.tar.gz"
READS, CALLS, BINDS = 1, 4, 16          # flowR's edge bits: reads, calls, defines-on-call; any other bit is ignored
FLOWR_ANSWER_MAX = 200 * 1024 * 1024    # flowR answers ~64 KB of JSON per line of R, and Python needs ~8x that to read it

FLOWR_FOLDERS = {}                      # once ready in a session, ready for the rest of it

def flowr_ready(source=""):
    """flowR's folder, fetched once from source - a staged archive, such as one in a Volume - or from the
    pinned release, refused unless its SHA-256 is the pinned one, and run once: ready means it runs here.
    The folder is this system user's own: a shared cluster runs every notebook session as a user of its
    own, and a folder another session made can be neither read nor written. Enforces: R12"""
    import tarfile, urllib.request
    if source in FLOWR_FOLDERS:
        return FLOWR_FOLDERS[source]
    folder = os.path.join(tempfile.gettempdir(), "flowr-%s-%d" % (FLOWR_VERSION, os.getuid()))
    binary = os.path.join(folder, "flowr")
    if not all(os.path.exists(os.path.join(folder, name)) for name in ("flowr", "tree-sitter.wasm", "tree-sitter-r.wasm")):
        os.makedirs(folder, mode=0o700, exist_ok=True)
        archive = os.path.join(folder, "flowr.tar.gz")
        shutil.copyfile(source, archive) if source else urllib.request.urlretrieve(FLOWR_URL.format(FLOWR_VERSION), archive)
        if file_sha256(archive) != FLOWR_SHA256:
            os.remove(archive)
            raise RuntimeError("The flowR archive is not the pinned release %s: its checksum differs." % FLOWR_VERSION)
        with tarfile.open(archive) as bundle:
            bundle.extractall(folder, members=[m for m in bundle.getmembers() if m.isfile() and "/" not in m.name.strip("./")])
        os.chmod(binary, 0o700)
    try:                                            # one line of R, read the way the review reads: ready means it ran
        flowr_read(folder, "x <- 1\n")
    except Exception as problem:
        raise RuntimeError("flowR is here but could not run on this cluster: %s" % problem)
    FLOWR_FOLDERS[source] = folder
    return folder

def flowr_read(folder, text, prefix=""):
    """flowR's syntax tree of one R source, indexed by id, and its edges as {id: [(target, bits)]}; every
    id carries the prefix, so that the answers for several sources can stand side by side. An answer too
    large to read safely is refused before it is read: loading it would take the driver's memory."""
    with tempfile.TemporaryDirectory() as work:
        source = os.path.join(work, "package.R")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(text)
        found = flowr_answer(folder, source, [{"type": "dataflow"}, {"type": "normalized-ast"}], work, "--no-fs")
    tree = found["normalized-ast"].get("normalized", found["normalized-ast"]).get("ast")
    edges = {prefix + str(s): [(prefix + str(t), e["types"]) for t, e in targets] for s, targets in found["dataflow"]["graph"]["edgeInformation"]}
    nodes, stack = {}, [(tree, None)]
    while stack:                                   # every node once, with its parent; no recursion, so no depth limit
        node, up = stack.pop()
        if isinstance(node, dict):
            if "type" in node and "info" in node:
                node["info"]["id"] = prefix + str(node["info"]["id"])
                node["up"], up = up, node["info"]["id"]
                nodes[up] = node
            stack += [(value, up) for key, value in node.items() if key not in ("info", "location", "lexeme", "up")]
        elif isinstance(node, list):
            stack += [(value, up) for value in node]
    return nodes, edges

class Dataflow:
    """The data flow of one package, read by flowR and laid out as the map needs it. flowR says which
    definition each name reads, which function each call calls and which parameter each argument becomes;
    what is the model's own - dplyr columns, stored tables, files read, the gaps left for the agents - is
    decided here, as it was before flowR. Node ids: 'f:v' a value v set in function f; 'f:arg:a' a
    parameter; 'f:return' what f returns; 'call:f:line:g' one call of g from f; 'column:c' a data-frame
    column; 'data:t' a stored table; 'file:path'; 'number:value:f:line'; 'outside:name'."""

    def __init__(self, units, trivial=(), folder=None):
        self.units, self.trivial = units, set(trivial)
        self.functions = {u["name"]: u for u in units if u["kind"] == KIND_FUNCTION and not u.get("inside")}
        self.tables = {u["data"]["object_name"]: u for u in units if (u.get("data") or {}).get("object_name")}
        self.nodes, self.records, self.tree, self.edges, self.unit_of, self.unread = {}, [], {}, {}, {}, {}
        folder = folder or flowr_ready()
        for number, unit in enumerate(sorted(self.functions.values(), key=lambda u: u["ref"])):
            prefix = "%d:" % number             # one function at a time: memory is bounded by the largest function,
            self.unit_of[prefix] = unit["name"]  # not by the package - the whole package at once took a driver down
            try:
                tree, edges = flowr_read(folder, unit["text"], prefix)
            except (ValueError, KeyError, OSError, subprocess.SubprocessError) as problem:
                self.unread[unit["name"]] = "flowR could not read it: %s" % problem
                continue
            self.tree.update(tree)
            self.edges.update(edges)
        named = lambda n: (n["lhs"].get("lexeme") or "").strip("`")          # an operator is defined as `%||%`
        self.defs = {str(n["rhs"]["info"]["id"]): named(n) for n in self.tree.values()
                     if n["type"] == "RBinaryOp" and n.get("rhs", {}).get("type") == "RFunctionDefinition"
                     and named(n) in self.functions and self.place(n)[0] == named(n)}
        self.assigned = {}                              # (function, name) -> how many times it is set there
        for n in self.tree.values():
            for label in self.set_here(n):
                key = (self.owner(str(n["info"]["id"])), label)
                self.assigned[key] = self.assigned.get(key, 0) + 1

    # ------------------------------------------------ where a node is, and what it holds
    def place(self, node):
        """(function, first line, last line) of a node, the lines counted in its function's own unit."""
        where = node["info"].get("fullRange") or node.get("location") or [0, 0, 0, 0]
        return self.unit_of[node["info"]["id"].split(":")[0] + ":"], max(where[0], 1), max(where[2], where[0], 1)

    def set_here(self, node):
        """The names a node sets: the variable an assignment sets, or the names of a list's elements."""
        if node["type"] == "RBinaryOp" and node.get("lexeme") in ("<-", "=", "<<-", "->", "->>"):
            target = node["rhs"] if node["lexeme"].startswith("-") else node["lhs"]
            while target["type"] == "RAccess":
                target = target["accessed"]
            return [target["lexeme"].strip("\"'`")] if target["type"] in ("RSymbol", "RString") else []
        if node["type"] == "RFunctionCall" and node["functionName"].get("lexeme") in ELEMENT_MAKERS:
            return [a["name"]["lexeme"] for a in node.get("arguments") or [] if a and a.get("name") and a.get("value")]
        return []

    def value_id(self, function, name, at):
        """A value set once is 'f:v'; one set several times is 'f:v@line', one node for each time it is set -
        tie_outputs set four times in tie_model_call is four nodes, each reading the one before it."""
        many = self.assigned.get((function, name), 0) > 1
        return "%s:%s@%d" % (function, name, self.place(at)[1]) if many else "%s:%s" % (function, name)

    def owner(self, node_id):
        while node_id and node_id not in self.defs:
            node_id = self.tree[node_id]["up"] if node_id in self.tree else None
        return self.defs.get(node_id)

    def kids(self, node):
        found = []
        for key, value in node.items():
            if key not in ("info", "location", "lexeme", "up", "grouping"):      # ( ) and { } group; they are not names
                found += [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, dict) and "type" in v]
        return found

    def node(self, node_id, kind, name, env=None, at=None, sources=(), **extra):
        record = self.nodes.get(node_id)
        if record is None:
            record = self.nodes[node_id] = {"record_type": "node", "node": node_id, "kind": kind, "name": name,
                                            "function": env["function"] if env else "", "line": self.line_of(env, at),
                                            "function_ref": self.functions[env["function"]]["ref"] if env else "",
                                            "code": self.code_of(env, at), "from": []}
        elif env and not record["function"] and kind == "column" and at is not None:   # read before it was created
            record.update(function=env["function"], function_ref=self.functions[env["function"]]["ref"],
                          line=self.line_of(env, at), code=self.code_of(env, at))
        record["from"] += [s for s in dict.fromkeys(sources) if s not in record["from"] and s != node_id]
        record.update(extra)
        return node_id

    def line_of(self, env, at):
        return self.functions[env["function"]]["lines"][0] + self.place(at)[1] - 1 if env and at else 0

    def code_of(self, env, at):
        if not env or not at:
            return ""
        _, first, last = self.place(at)
        return "\n".join(self.functions[env["function"]]["text"].split("\n")[first - 1:max(first, last)]).strip()

    def exact_of(self, env, at, to=None):
        """The characters from where a node starts to where `to` ends, not whole lines: a named argument's
        range covers its name only, so overrides_and_caps = tie_anchor_overrides(...) runs to the value's end."""
        span = lambda n: n["info"].get("fullRange") or n.get("location") or [0, 0, 0, 0]
        (first, c1), (last, c2) = span(at)[:2], span(to or at)[2:]
        lines = self.functions[env["function"]]["text"].split("\n")[first - 1:last]
        if not lines:
            return ""
        lines[-1] = lines[-1][:c2] if len(lines) > 1 else lines[-1][c1 - 1:c2]
        lines[0] = lines[0][c1 - 1:] if len(lines) > 1 else lines[0]
        return "\n".join(lines).strip()

    def gap(self, env, at, why):
        self.records.append({"record_type": "gap", "function": env["function"], "function_ref": self.functions[env["function"]]["ref"],
                             "line": self.line_of(env, at), "code": self.code_of(env, at), "why": why})

    # ------------------------------------------------ one function
    def trace(self, name):
        fdef = next((i for i, n in self.defs.items() if n == name), None)
        env = {"function": name}
        if fdef is None:
            self.records.append({"record_type": "gap", "function": name, "function_ref": self.functions[name]["ref"],
                                 "line": self.functions[name]["lines"][0], "code": self.functions[name]["text"].split("\n")[0],
                                 "why": self.unread.get(name, "the function could not be read")})
            return
        function = self.tree[fdef]
        for parameter in function.get("parameters") or []:
            default = parameter.get("defaultValue")
            self.node("%s:arg:%s" % (name, parameter["name"]["lexeme"]), "argument", parameter["name"]["lexeme"], env, function,
                      default_from=self.sources(default, env) if default else [], default_code=self.code_of(env, default) if default else "")
        body = function["body"]
        returned, stack = self.body(body, env), [body]
        while stack:                                       # return() anywhere, but not inside a function written in place
            inner = stack.pop()
            if inner["type"] == "RFunctionCall" and inner["functionName"].get("lexeme") == "return" and inner.get("arguments"):
                returned += self.sources(inner["arguments"][0], env)
            stack += [k for k in self.kids(inner) if k["type"] != "RFunctionDefinition"]
        items = body.get("children") if body["type"] == "RExpressionList" else [body]
        self.node("%s:return" % name, "return", "the value %s returns" % name, env, (items or [function])[-1], returned)

    def body(self, block, env):
        """The statements of a body, each value it sets a node; returns the sources of what the body gives."""
        items, given = (block.get("children") or []) if block["type"] == "RExpressionList" else [block], []
        for position, item in enumerate(items):
            last = position == len(items) - 1
            if item["type"] == "RBinaryOp" and item.get("lexeme") in ("<-", "=", "<<-", "->", "->>"):
                target, value = (item["rhs"], item["lhs"]) if item["lexeme"].startswith("-") else (item["lhs"], item["rhs"])
                while target["type"] == "RAccess":                          # x$c <- v and x[i] <- v change x
                    target = target["accessed"]
                if "<<" in item["lexeme"] or ">>" in item["lexeme"]:
                    self.gap(env, item, "a value assigned outside the function with <<-")
                if target["type"] in ("RSymbol", "RString"):
                    changed = item["rhs"] if item["lexeme"].startswith("-") else item["lhs"]
                    extra = self.sources(changed, env) if changed is not target else []
                    name = target["lexeme"].strip("\"'`")
                    node = self.node(self.value_id(env["function"], name, target), "value", name, env, item,
                                     self.sources(value, env) + extra)
                    given = [node] if last else given
            elif item["type"] == "RIfThenElse" and not last:
                self.sources(item["condition"], env)
                for branch in (item.get("then"), item.get("otherwise")):
                    if branch:
                        self.body(branch, env)
            elif item["type"] in ("RForLoop", "RWhileLoop", "RRepeatLoop"):
                self.body(item["body"], env)
            elif last:
                given = self.sources(item, env)
        return given

    # ------------------------------------------------ what a value is computed from
    def sources(self, node, env, masked=False):
        kind = node["type"] if node else ""
        if kind == "RNumber":
            value = node["lexeme"].rstrip("Li")
            return [self.node("number:%s:%s:%d" % (value, env["function"], self.place(node)[1]), "number", value, env, node,
                              trivial=value in self.trivial)]
        if kind in ("", "RString", "RLogical", "RComment"):
            return []
        if kind == "RSymbol":
            return self.resolve(node, env, masked)
        if kind == "RArgument":
            return self.sources(node.get("value"), env, masked)
        if kind == "RPipe":
            return self.call(node["rhs"], env, masked, first=node["lhs"].get("value", node["lhs"]))
        if kind == "RFunctionCall":
            return self.call(node, env, masked)
        if kind == "RBinaryOp" and node.get("lexeme") in ("<-", "=", "<<-"):
            self.body(node, env)
            return self.resolve(node["lhs"], env, masked) if node["lhs"]["type"] == "RSymbol" else []
        if kind == "RAccess":
            accessed, access = node["accessed"], node.get("access") or []
            access = access if isinstance(access, list) else [access]
            if accessed.get("lexeme") in (".data", ".env") and access:
                field = access[0].get("value") or access[0]
                if accessed["lexeme"] == ".data":
                    return self.column(field["lexeme"])
                own = [i % (env["function"], field["lexeme"]) for i in ("%s:arg:%s", "%s:%s") if i % (env["function"], field["lexeme"]) in self.nodes]
                return own[:1] or self.resolve(field, env, False)
            return self.sources(accessed, env, masked) + ([] if node.get("lexeme") == "$" else
                                                          [s for a in access for s in self.sources(a, env, masked)])
        if kind == "RFunctionDefinition":
            self.gap(env, node, "a function written in place, whose arguments are given at run time")
            return self.sources(node["body"], env, masked)
        return [s for k in self.kids(node) for s in self.sources(k, env, masked)]

    def resolve(self, symbol, env, masked):
        """What a name reads, as flowR resolves it: a parameter, a value set in a function, or a column a
        dplyr verb created. A name flowR finds no definition for is a stored table, a column of the data,
        or a name from outside the package."""
        name = symbol["lexeme"]
        if name in CONSTANT_NAMES:
            return []
        # a name reads only what has that name: inside a verb flowR also links a column the same verb made
        # earlier, which a later argument may use - but berth_utilisation does not read throughput_score
        found, reads = [], [t for t, bits in self.edges.get(str(symbol["info"]["id"]), []) if bits & READS and t in self.tree
                            and name in (self.tree[t].get("lexeme"), (self.tree[t].get("name") or {}).get("lexeme"))]
        for target in reads:
            up = self.tree.get(self.tree[target]["up"] or "", {})
            if up.get("type") == "RParameter":                       # a parameter: of a function of the package, or of a lambda
                owner = self.defs.get(up["up"])
                found += ["%s:arg:%s" % (owner, name)] if owner else []
            elif "RArgument" in (up.get("type"), self.tree[target]["type"]):   # a column a verb named: mutate(name = ...)
                found += self.column(name)
            elif self.tree[target]["lexeme"] not in self.functions and self.owner(target):   # the very assignment it reads
                found.append(self.value_id(self.owner(target), self.tree[target]["lexeme"], self.tree[target]))
        if reads:
            return list(dict.fromkeys(found))
        if name in self.tables:
            return [self.table_node(name)]
        if name in self.functions:
            return []
        return self.column(name) if masked else [self.node("outside:%s" % name, "outside", name)]

    def column(self, name):
        return [self.node("column:%s" % name, "column", name, created_in=self.nodes.get("column:%s" % name, {}).get("created_in", []))]

    def table_node(self, name):
        table = self.tables[name]
        return self.node("data:%s" % name, "stored data", name, file=table["data"].get("container_file", ""), unit_ref=table["ref"],
                         columns=list(table["data"].get("columns") or []))

    def call(self, node, env, masked, first=None):
        name = (node.get("functionName") or {}).get("lexeme", "")
        args = ([None] if first is not None else []) + [a for a in node.get("arguments") or [] if a]
        pairs = [("", first)] if first is not None else []
        pairs += [((a.get("name") or {}).get("lexeme", ""), a.get("value")) for a in node.get("arguments") or [] if a]
        values = [v for _, v in pairs]
        if name == "%>%" and len(values) == 2:                       # a %>% f(b) is f(a, b)
            left, right = values
            return self.call(right, env, masked, first=left) if right and right["type"] == "RFunctionCall" else self.sources(left, env, masked)
        flat = lambda inner: [s for v in values for s in self.sources(v, env, inner)]
        if name in OPAQUE_CALLS:
            self.gap(env, node, OPAQUE_CALLS[name])
            return flat(masked)
        if name in ELEMENT_MAKERS and any(label for label, _ in pairs):
            made = []            # list(overrides_and_caps = tie_anchor_overrides(...)): every named element is a value,
            for (label, value), argument in zip(pairs, args):   # one holding only NA as much as any other
                got = self.sources(value, env, masked)
                if label and value is not None:
                    made.append(self.node(self.value_id(env["function"], label, value), "value", label, env, argument, got,
                                          code=self.exact_of(env, argument, value)))
                else:
                    made += got
            return made
        if name in FILE_READERS:
            path = self.file_path(values[0]) if values else ""
            if not path:
                self.gap(env, node, "a file read from a path built at run time")
                return flat(masked)
            table = next((t for t, u in self.tables.items() if u["data"].get("container_file") == path), None)
            return [self.node("file:%s" % path, "file", path, unit_ref=self.tables[table]["ref"] if table else "")]
        if name in DPLYR_CREATE:
            created = self.sources(values[0], env, masked) if pairs and not pairs[0][0] else []
            for (label, value), argument in zip(pairs, args):
                if label:
                    column = self.node("column:%s" % label, "column", label, env, argument, self.sources(value, env, True),
                                       code=self.exact_of(env, argument, value))
                    self.nodes[column].setdefault("created_in", [])
                    if env["function"] not in self.nodes[column]["created_in"]:
                        self.nodes[column]["created_in"].append(env["function"])
                    created.append(column)
                elif value is not values[0]:
                    self.gap(env, node, "columns created by an expression that does not name them")
            return created
        if name in DPLYR_JOIN:
            keys = {k["lexeme"].strip("\"'") for label, value in pairs if label == "by" and value
                    for k in [value] + self.kids(value) if k["type"] == "RString"}
            joined = []
            for value in values[:2]:
                joined += self.sources(value, env, masked)
                if value and value["type"] == "RSymbol" and value["lexeme"] in self.tables:
                    table = self.nodes[self.table_node(value["lexeme"])]
                    joined += [self.node("column:%s" % c, "column", c, env, node, [table["node"]]) for c in table["columns"] if c not in keys]
            return joined
        callee = next((self.defs[t] for t, bits in self.edges.get(str(node["info"]["id"]), []) if bits & CALLS and t in self.defs),
                      name if name in self.functions else None)   # another function of the package: by its name
        if callee is None and name in APPLIERS:                     # map(x, f): a package function handed over by name
            handed = [v["lexeme"] for v in values if v and v["type"] == "RSymbol" and v["lexeme"] in self.functions]
            return [self.record_call(f, env, node, [], []) for f in handed] + [s for v in values if not (v and v["type"] == "RSymbol"
                    and v["lexeme"] in self.functions) for s in self.sources(v, env, masked)]
        inner = masked or name in DPLYR_MASKING
        if callee:
            return [self.record_call(callee, env, node, pairs, [self.sources(v, env, inner) for v in values])]
        return flat(inner)

    def record_call(self, callee, env, node, pairs, values):
        """One call of a package function: which parameter each argument becomes there - as flowR binds it,
        and for what flowR leaves unbound (a value piped in, say) as R does, by name and then by position -
        and a parameter left out takes its default."""
        formals = [p["name"]["lexeme"] for p in self.tree[next(i for i, n in self.defs.items() if n == callee)].get("parameters") or []]
        bound, left = {}, []
        for (label, value), got in zip(pairs, values):
            ids = [str(value["info"]["id"])] if value else []
            binds = [self.tree[t]["lexeme"] for i in ids for t, bits in self.edges.get(i, []) if bits & BINDS and t in self.tree]
            target = next((b for b in binds if b in formals and b not in bound), None)
            (bound.__setitem__(target, got) if target else left.append((label, got)))
        free = [f for f in formals if f not in bound and f != "..."]
        for label, got in left:
            if label in free:
                bound[label] = got
                free.remove(label)
            elif free:
                bound[free.pop(0)] = got
            elif "..." in formals:
                bound.setdefault("...", []).extend(got)
        call_id = "call:%s:%d:%s" % (env["function"], self.place(node)[1], callee)
        return self.node(call_id, "call", "%s()" % callee, env, node, [s for got in values for s in got] + ["%s:return" % callee],
                         callee=callee, bindings={f: bound.get(f, ["default"]) for f in formals})

    def file_path(self, value):
        """The path a reader is given: a string as written, or system.file(...), which names a file under inst/."""
        if value and value["type"] == "RString":
            return value["lexeme"].strip("\"'")
        if value and value["type"] == "RFunctionCall" and value["functionName"].get("lexeme") == "system.file":
            parts = [a["value"]["lexeme"].strip("\"'") for a in value.get("arguments") or []
                     if a and not a.get("name") and (a.get("value") or {}).get("type") == "RString"]
            return "inst/" + "/".join(parts) if parts else ""
        return ""

    # ------------------------------------------------ the whole package
    def run(self):
        for name in sorted(self.functions, key=lambda n: self.functions[n]["ref"]):
            self.trace(name)
        calls = [r for r in self.nodes.values() if r["kind"] == "call"]
        called = {r["callee"] for r in calls if r["callee"] != r["function"]}
        entry = set()
        parse_r_sources([unit["text"] for unit in self.units if unit["kind"] in (KIND_TEST, KIND_TOPLEVEL, KIND_VIGNETTE)])
        for unit in self.units:                          # the tests and vignettes that call a package function
            if unit["kind"] in (KIND_TEST, KIND_TOPLEVEL, KIND_VIGNETTE):
                for found in parse_r_source(unit["text"]):
                    if not isinstance(found, tuple):
                        entry |= {callee_name(inner) for inner in walk_nodes(found) if inner.kind == "call"} & set(self.functions)
        uncalled = set(self.functions) - called
        proposed = sorted(name for name in uncalled if (self.functions[name].get("code") or {}).get("exported") or name in entry)
        reached, frontier = set(proposed), list(proposed)
        while frontier:
            caller = frontier.pop()
            for record in calls:
                if record["function"] == caller and record["callee"] not in reached:
                    reached.add(record["callee"])
                    frontier.append(record["callee"])
        roots = {"record_type": "roots", "proposed": proposed, "not_reached": sorted(set(self.functions) - reached),
                 "why": {name: ", ".join(filter(None, ["nothing in the package calls it",
                                                         "exported" if (self.functions[name].get("code") or {}).get("exported") else "",
                                                         "called by a test or vignette" if name in entry else ""])) for name in uncalled}}
        return list(self.nodes.values()) + self.records + [roots]


def walk_nodes(node):
    """Every node of a tree, the tree itself first, without entering functions written inside it."""
    yield node
    for child in node.args:
        if child.kind != "function":
            yield from walk_nodes(child)

def trace_dataflow(ctx):
    """Step 05a, trace-dataflow: the package's data flow, by code alone - every value each function sets
    and what it is computed from, every call with its arguments matched to their parameters, every column
    a dplyr verb creates, every stored table, file and hard-coded number, and the gaps code cannot follow.
    Proposes the final outputs: exported functions nothing in the package calls, and those its tests and
    vignettes call. Enforces: R2, R4, R7, R14"""
    flow = Dataflow(ctx.read("model_units"), ctx.settings["trivial_numbers"], flowr_ready())
    records = flow.run()
    count = lambda kind: sum(1 for r in records if r.get("kind") == kind)
    gaps = [r for r in records if r["record_type"] == "gap"]
    roots = records[-1]
    return StepResult({"dataflow": records},
                           {"values": count("value"), "calls": count("call"), "columns": count("column"), "gaps": len(gaps),
                            "proposed final outputs": len(roots["proposed"])},
                           ["Traced %d functions: %d values, %d calls, %d columns; %d gaps for the agents. Proposed final outputs: %s."
                            % (len(flow.functions), count("value"), count("call"), count("column"), len(gaps), ", ".join(roots["proposed"]) or "none")])


def decided_outputs(records, decisions):
    """The final outputs a run works from, and why each is one: code's proposal, then a person's decisions
    over it - 'yes' makes any function a final output, 'no' takes one away. Where nothing is left, every
    function nothing in the package calls stands in, so the map always has a top. Returns (outputs, how,
    not reached): how says of each output where it came from; not reached are the functions no output
    reaches, following the calls. Enforces: R1, R2"""
    roots = next((r for r in records if r["record_type"] == "roots"), {"proposed": [], "not_reached": [], "why": {}})
    calls = [r for r in records if r["record_type"] == "node" and r["kind"] == "call"]
    functions = {r["function"] for r in records if r["record_type"] == "node" and r.get("function")} | set(roots["why"])
    outputs, how = [], {}
    for name in roots["proposed"]:
        if decisions.get(name) != "no":
            outputs.append(name)
            how[name] = "proposed by code: %s" % roots["why"].get(name, "")
    for name in sorted(decisions):
        if decisions[name] == "yes" and name in functions and name not in outputs:
            outputs.append(name)
            how[name] = "your decision"
    if not outputs:
        outputs = sorted(roots["why"])
        how = {name: "nothing in the package calls it (no final output was proposed or decided)" for name in outputs}
    reached, frontier = set(outputs), list(outputs)
    while frontier:
        caller = frontier.pop()
        for call in calls:
            if call["function"] == caller and call["callee"] not in reached:
                reached.add(call["callee"])
                frontier.append(call["callee"])
    return outputs, how, sorted(functions - reached)


# ================================================================================================
# the map: how the model computes what it returns
# ================================================================================================
# ---------------------------------------------------------------- the graph and the map

# ---------------------------------------------------------------- the ledger and the graph in memory





# ---------------------------------------------------------------- words: splitting, stemming, word lists







# ---------------------------------------------------------------- S3: explicit references as written


# ---------------------------------------------------------------- the skill map-implementation: the implementation map's agents
# Code traced the data flow (step 05a); these agents work only where it stopped. The Tracer is given one
# gap on the path from a final output and a fixed list of actions; each turn it chooses one, code carries
# it out on the records and shows what it found, and every link it declares must copy the code word for
# word and use only names that code holds. Each turn is a question of its own, recorded, so a run replays
# without a model. The Namer gives each step a plain name, outside the accounting. The Auditor is code.
# The model chooses; code executes. Enforces: R3, R4, R5


# ---------------------------------------------------------------- step 05: build-graph



# ---------------------------------------------------------------- what each piece of code does, in plain words


# ================================================================================================
# ---------------------------------------------------------------- a fault inside the tool
class EngineFault(Exception):
    """The tool found itself inconsistent. Never raised about the model under review. Enforces: R2"""


# ---------------------------------------------------------------- the run: its folder, its record and its two deliverables
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- settings (allow-list)
DEFAULT_SETTINGS = {
    
    
    
    
    "max_parameter_cells": 5000, "max_parameter_columns": 50, "protect_sheets": True,
    "trivial_numbers": ["0", "1", "2", "-1", "10", "100"],
    
    
    "max_file_mb": 200.0, "reviewer_id": "", "read_pictures": True,
    "map_granularity": "statement", "map_rows_max": 5000}

def make_settings(overrides=None):
    """The settings of a run. Only names on the allow-list above exist, so a new setting
    can never leak into the manifest by default, and no setting can hold the token.
    Enforces: R8"""
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    for name, value in (overrides or {}).items():
        if name not in DEFAULT_SETTINGS:
            raise ValueError("'%s' is not a setting the tool knows" % name)
        settings[name] = value
    return settings

# ---------------------------------------------------------------- paths and project setup
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
LONGEST_AUDIT_NAME = "Output.xlsx"
PATH_BUDGET = 100

@dataclass
class RunPaths:
    """Where one run lives. Output.xlsx sits in run_dir itself; _audit/
    beside them holds the three files of the record; local_dir is scratch space on the driver.
    outputs_dir is the same folder as run_dir, kept as a name so that every reader of the two
    deliverables says which folder it means."""
    projects_dir: str; model_id: str; project_date: str; project_dir: str; inputs_dir: str
    run_id: str; run_dir: str; outputs_dir: str; audit_dir: str; local_dir: str

def check_model_id(model_id):
    """Return "" when the model ID is usable, otherwise a plain sentence saying why not."""
    if MODEL_ID_RE.match(model_id or ""):
        return ""
    return ("The model ID may hold at most 24 characters from letters, digits, hyphen and "
            "underscore. Please shorten or change '%s'." % model_id)

def setup_project(projects_dir, model_id, project_date=""):
    """Create the project skeleton and say what is still missing. Inputs are never touched."""
    problem = check_model_id(model_id)
    if problem:
        raise ValueError(problem)
    project_date = project_date or datetime.date.today().isoformat()
    project_dir = os.path.join(projects_dir, model_id, project_date)
    missing = []
    for _, folder, readme in INPUT_FOLDERS:
        path = os.path.join(project_dir, "Inputs", folder)
        os.makedirs(path, exist_ok=True)
        readme_path = os.path.join(path, "README.txt")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as handle:
                handle.write(readme + "\n")
        if not [n for n in os.listdir(path) if n != "README.txt" and not n.startswith(".")]:
            missing.append("Inputs/%s is still empty. %s" % (folder, readme))
    return project_dir, missing

def new_run_id(project_dir, now=None):
    """Run_<date>_<HHMM>, with a letter added when that folder already exists."""
    now = now or datetime.datetime.now()
    base = now.strftime("Run_%Y-%m-%d_%H%M")
    for suffix in [""] + list("bcdefghijklmnopqrstuvwxyz"):
        if not os.path.exists(os.path.join(project_dir, base + suffix)):
            return base + suffix
    raise ValueError("Too many runs were started in the same minute; please wait a minute.")

def pick_scratch_root(preferred=""):
    """The first folder on the driver the tool can actually write in, tried in order.

    A run is built on the driver's own disk and copied whole into the Workspace afterwards
    (R12), so this folder is needed before anything else can happen. A cluster is shared, and
    a scratch folder made by one user cannot be written into by another; the folders tried
    here therefore carry the user's own name. Writing is tested, not assumed, because a
    folder can exist and still refuse."""
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")
    refused = []
    for root in ([preferred] if preferred else []) + [
            os.path.join(tempfile.gettempdir(), "verifier_scratch_" + user),
            os.path.join("/local_disk0", "verifier_scratch_" + user)]:
        try:
            os.makedirs(root, exist_ok=True)
            probe = os.path.join(root, ".verifier_write_test")
            with open(probe, "w") as handle:
                handle.write("x")
            os.remove(probe)
            return root
        except OSError as problem:
            refused.append("%s (%s)" % (root, problem.strerror or problem))
    raise PermissionError(
        "the tool builds each run on the driver's own disk and copies the finished files into the "
        "Workspace, so it needs one folder it may write in. These were refused: %s. Put a "
        "folder you can write in into the 'Scratch folder' widget, or ask for one on this "
        "cluster." % "; ".join(refused))

def open_run(projects_dir, model_id, project_date="", run_id="", scratch_root="", now=None):
    """Create or re-open a run folder and its local scratch folder. Enforces: R6"""
    project_dir, _ = setup_project(projects_dir, model_id, project_date)
    project_date = os.path.basename(project_dir)
    run_id = run_id or new_run_id(project_dir, now)
    run_dir = os.path.join(project_dir, run_id)
    scratch_root = pick_scratch_root(scratch_root)
    place = sha256_text(os.path.abspath(run_dir))[:8]       # two Projects folders never share scratch space
    local_dir = os.path.join(scratch_root, "%s_%s_%s_%s" % (model_id, project_date, run_id, place))
    paths = RunPaths(projects_dir, model_id, project_date, project_dir,
                     os.path.join(project_dir, "Inputs"), run_id, run_dir,
                     run_dir, os.path.join(run_dir, "_audit"), local_dir)
    longest = os.path.join(paths.run_dir, LONGEST_AUDIT_NAME)
    relative = os.path.relpath(longest, os.path.dirname(os.path.abspath(projects_dir)))
    if len(relative) > PATH_BUDGET:
        raise ValueError("The folder path is %d characters long and the limit is %d, so that "
                         "Excel can still open downloaded files. Please use a shorter model ID "
                         "or Projects folder." % (len(relative), PATH_BUDGET))
    for folder in (paths.outputs_dir, paths.audit_dir, paths.local_dir):
        os.makedirs(folder, exist_ok=True)
    return paths

# ---------------------------------------------------------------- live values (the token)
@dataclass
class LiveValues:
    """The three values chat() reads when it is CALLED: endpoint, token, user id. They live
    in memory only. `generation` goes up whenever a different token arrives, which is how
    paused workers learn that a fresh one was pasted. Enforces: R8"""
    values: dict = field(default_factory=dict); generation: int = 0; set_at: float = 0.0
    recent_tokens: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, llm_endpoint="", llm_token="", llm_user_id=""):
        """Take the latest widget values; a different token starts a new generation."""
        with self.lock:
            if llm_token and llm_token != self.values.get("llm_token"):
                self.generation += 1
                self.set_at = time.time()
                self.recent_tokens = ([llm_token] + self.recent_tokens)[:5]
            self.values = {"llm_endpoint": llm_endpoint, "llm_token": llm_token, "llm_user_id": llm_user_id}

    def get(self, name):
        """One of the three values, read now. The user id is one value under two names: the widget is
        called reviewer_id, because the same id records who made a decision and is sent to the LLM."""
        with self.lock:
            return self.values.get("llm_user_id" if name == "reviewer_id" else name, "")

    def token_age_minutes(self):
        """Minutes since the current token was pasted."""
        return (time.time() - self.set_at) / 60.0 if self.set_at else 0.0

    def redact(self, text):
        """Remove the current and recent token strings from any text before it is kept."""
        for token in list(self.recent_tokens):
            if token:
                text = text.replace(token, "[token removed]")
        return text

# ---------------------------------------------------------------- the audit store
AUDIT_OBJECTS = ("run_manifest", "package_info", "coverage")
AUDIT_FILE = "Audit_Log.xlsx"            # the record of a run: one workbook, in the run folder's _audit
CELL_LIMIT = 30000                       # Excel holds 32,767 characters in a cell; longer text is written in parts

def copy_whole(source, target):
    """Copy one whole file: to a temporary name, then replace; a plain copy if the file
    system does not support replace (probe P-5). Enforces: R12"""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".part"
    shutil.copyfile(source, temporary)
    try:
        os.replace(temporary, target)
    except OSError:
        shutil.copyfile(source, target)
        os.remove(temporary)

@dataclass
class AuditStore:
    """The record of a run, as one workbook a person can open: _audit/Audit_Log.xlsx.

        Run            the run's manifest and account, one line per entry
        Steps          every step that ran, with its version, what it counted and what it said
        Records        every record of every kind, in the order written, each as its own JSON
        Model_Calls    every exchange with the model: the question, the answer and the outcome

    Records are held in memory while a cell runs and the workbook is written whole at each
    sync, beside and then swapped in, so a reader never sees it half written. Text longer than
    a cell holds is written in numbered parts and joined again when read, so nothing is cut.
    Enforces: R4, R5, R12"""
    local_dir: str; remote_dir: str
    rows: list = field(default_factory=list)       # {"kind", "record"}, in the order written
    calls: list = field(default_factory=list)
    account: dict = field(default_factory=dict)    # the manifest and the other single-object kinds
    loaded: bool = False

    def target(self):
        return os.path.join(self.remote_dir, AUDIT_FILE)

    def read(self, kind):
        """Every record of one kind, in the order written."""
        self.restore()
        if kind == "llm_calls":
            return list(self.calls)
        if kind in AUDIT_OBJECTS:
            found = self.account.get(kind)
            return [found] if found is not None else []
        return [row["record"] for row in self.rows if row["kind"] == kind]

    def append(self, kind, records):
        """Add records of one kind; the single-object kinds are replaced whole."""
        self.restore()
        if kind in AUDIT_OBJECTS:
            self.account[kind] = to_plain(records[-1])
            return
        self.rows += [{"kind": kind, "record": to_plain(record)} for record in records]

    def append_calls(self, records):
        self.restore()
        self.calls += [to_plain(record) for record in records]

    def read_calls(self):
        return self.read("llm_calls")

    def sync(self):
        """Write the whole workbook, beside and then swapped in. Returns what was written."""
        import openpyxl
        os.makedirs(self.remote_dir, exist_ok=True)
        book = openpyxl.Workbook()
        book.remove(book.active)
        run = book.create_sheet("Run")
        run.append(["Entry", "Value"])
        for key in sorted(self.account):
            for line, part in parts_of(canonical_json(self.account[key])):
                run.append([key if line == 1 else "%s (part %d)" % (key, line), part])
        steps = book.create_sheet("Steps")
        steps.append(["Step", "Name", "Version", "Seconds", "What it counted", "What it said"])
        for record in self.read("step_records"):
            steps.append([record.get("step_id", ""), record.get("step", ""), record.get("step_version", ""),
                          record.get("seconds", ""), canonical_json(record.get("counts") or {})[:CELL_LIMIT],
                          "\n".join(record.get("messages") or [])[:CELL_LIMIT]])
        records = book.create_sheet("Records")
        records.append(["Kind", "Number", "Part", "Record (JSON)"])
        for number, row in enumerate(self.rows, start=1):
            for part_number, part in parts_of(canonical_json(row["record"])):
                records.append([row["kind"], number, part_number, part])
        calls = book.create_sheet("Model_Calls")
        calls.append(["Number", "Question", "Step", "Question type", "Attempt", "Outcome", "Part", "Exchange (JSON)"])
        for number, record in enumerate(self.calls, start=1):    # a question asked twice has two records: each its own number
            for part_number, part in parts_of(canonical_json(record)):
                calls.append([number, record.get("question_id", ""), record.get("step", ""), record.get("question_type", ""),
                              record.get("attempt", ""), record.get("outcome", ""), part_number, part])
        for sheet in book.worksheets:
            sheet.freeze_panes = "A2"
        partial = os.path.join(self.local_dir, AUDIT_FILE + ".writing")
        os.makedirs(self.local_dir, exist_ok=True)
        book.save(partial)
        copy_whole(partial, self.target())
        os.remove(partial)
        return [AUDIT_FILE]

    def restore(self):
        """On resume: read the workbook of the run folder back, once."""
        if self.loaded:
            return
        self.loaded = True
        if not os.path.exists(self.target()):
            return
        import openpyxl
        book = openpyxl.load_workbook(self.target(), read_only=True)
        joined = {}
        for row in book["Records"].iter_rows(min_row=2, values_only=True):
            kind, number, _, part = row[0], row[1], row[2], row[3] or ""
            joined.setdefault((kind, number), []).append(part)
        self.rows = [{"kind": kind, "record": json.loads("".join(parts))}
                     for (kind, number), parts in sorted(joined.items(), key=lambda pair: pair[0][1])]
        whole = {}
        for row in book["Model_Calls"].iter_rows(min_row=2, values_only=True):
            whole.setdefault(row[0], []).append((row[6] or 1, row[7] or ""))
        self.calls = [json.loads("".join(part for _, part in sorted(parts))) for _, parts in sorted(whole.items())]
        entries = {}
        for row in book["Run"].iter_rows(min_row=2, values_only=True):
            key = re.sub(r" \(part \d+\)$", "", str(row[0] or ""))
            entries.setdefault(key, []).append(row[1] or "")
        self.account = {key: json.loads("".join(parts)) for key, parts in entries.items() if key}

def parts_of(text):
    """One long text as numbered parts, each short enough for a cell."""
    return [(number + 1, text[at:at + CELL_LIMIT]) for number, at in enumerate(range(0, max(len(text), 1), CELL_LIMIT))]

OPEN_STORES = {}                         # one store per run folder: two of them would overwrite each other's records

def open_store(paths, settings):
    """The audit store of a run, read back from the run folder's workbook when there is one. The same
    store is returned for the same run folder, so everything a run records goes into one account."""
    key = (paths.local_dir, paths.audit_dir)
    if key not in OPEN_STORES:
        OPEN_STORES[key] = AuditStore(paths.local_dir, paths.audit_dir)
    return OPEN_STORES[key]

# ---------------------------------------------------------------- the wrapper around chat()


# Fields of the gateway's reply that are worth keeping in the audit record. The reply also
# echoes the prompts back (query, defaultprompt, source) and those are dropped: the tool already
# stores the prompts it sent, and an echo would double the size of every call record.


# ---------------------------------------------------------------- the pipeline runner
def load_pipeline(engine_dir=ENGINE_DIR):
    """Read pipeline.yaml and refuse anything that is not a known step carried out by a known
    function. A step is named, versioned and mapped to its function in the one file; only
    functions listed in STEP_FUNCTIONS can be named, and there is no loading of scripts by path.
    Enforces: R11"""
    with open(os.path.join(engine_dir, "pipeline.yaml"), encoding="utf-8") as handle:
        pipeline = yaml.safe_load(handle)
    seen = set()
    for step in pipeline["steps"]:
        for key in ("id", "name", "version", "carried_out_by"):
            if key not in step:
                raise ValueError("Step %s of pipeline.yaml has no '%s'." % (step.get("id", "?"), key))
        if step["id"] in seen:
            raise ValueError("Step id %s appears twice in pipeline.yaml." % step["id"])
        seen.add(step["id"])
        step["version"] = str(step["version"])
        if step["carried_out_by"] != "a person" and step["carried_out_by"] not in STEP_FUNCTIONS:
            raise ValueError("pipeline.yaml names '%s', which is not a function this engine offers. "
                             "Only the functions in STEP_FUNCTIONS may be named." % step["carried_out_by"])
    return pipeline

def update_manifest(store, changes):
    """Change fields of the run manifest and write it back."""
    manifest = (store.read("run_manifest") or [{}])[0]
    manifest.update(changes)
    store.append("run_manifest", [manifest])
    return manifest


def run_pipeline(paths, settings, stop_after=""):
    """Run, or resume, the pipeline. Each finished step leaves a step record; called again,
    the run continues at the first step without one. A human step stops the run and says
    what the person should do. Returns {"state", "message", "steps_run"}."""
    store = open_store(paths, settings)
    pipeline = load_pipeline()
    done = {record["step_id"] for record in store.read("step_records")}
    steps_run = []
    for step in pipeline["steps"]:
        if stop_after and step["id"] > stop_after:
            break
        if step["id"] in done:
            continue
        run_step(step, store, paths, settings)
        steps_run.append(step["name"])
        if stop_after and step["id"] == stop_after:
            break
    message = "Every step has run." if not stop_after else "Stopped after step %s as asked." % stop_after
    rebuild_outputs(store, paths, settings, message)
    return {"state": "finished", "message": message, "steps_run": steps_run}

def run_step(step, store, paths, settings):
    """Build the context, call the step function, write what it returns, record the step,
    rebuild the outputs and sync. Steps never touch the store themselves."""
    notes = []
    provenance = Provenance(paths.run_id, step["id"], step["name"], step["version"])
    options = dict(step.get("with") or {})
    options.update({"inputs": list_input_files(paths.inputs_dir), "paths": paths,
                    "run": {"model_id": paths.model_id, "project_date": paths.project_date, "run_id": paths.run_id}})
    work_dir = os.path.join(paths.local_dir, "work")
    os.makedirs(work_dir, exist_ok=True)
    context = StepContext(settings, options, store.read, work_dir, notes.append, provenance)
    function = STEP_FUNCTIONS[step["carried_out_by"]]
    started = time.time()
    try:
        result = function(context)
    except Exception as problem:                     # a step that fails is written down, never a stopped run (R2)
        result = StepResult({}, {"step did not finish": 1}, [step_failure(step, problem, work_dir)])
    for kind in sorted(result.records):
        store.append(kind, result.records[kind])
    result.messages = list(result.messages) + notes
    record_step(store, step, result, time.time() - started)
    rebuild_outputs(store, paths, settings, "")
    store.sync()

def step_failure(step, problem, work_dir):
    """What the analyst is told when a step could not finish, and where the details are kept for
    whoever maintains the tool. The run goes on: the steps after this one work with what there is, and
    each says what it could not do. The details go to the run's work folder, not to the evidence
    pack, because they are about the tool and not about the model under review. Enforces: R2"""
    with open(os.path.join(work_dir, "step_%s_did_not_finish.txt" % step["id"]), "w", encoding="utf-8") as handle:
        handle.write("".join(traceback.format_exception(type(problem), problem, problem.__traceback__)))
    return ("Step %s (%s) could not finish, because of a fault inside the tool (%s). The steps after it ran on what there "
            "was, and say what they could not do. The details are in the run's work folder, for whoever maintains the tool."
            % (step["id"], step["name"], type(problem).__name__))

def record_step(store, step, result, seconds):
    """Leave the step record that makes a finished step visible and resume possible."""
    produced = {kind: len(records) for kind, records in sorted(result.records.items())}
    store.append("step_records", [{
        "step_id": step["id"], "name": step["name"], "version": step["version"],
        "carried_out_by": step["carried_out_by"], "produced": produced, "counts": result.counts,
        "messages": result.messages, "finished_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "seconds": round(seconds, 3)}])

def log_line(store, text):
    """Technical text (exception messages, Python names) belongs in run_log.txt only."""
    with open(os.path.join(store.local_dir, "run_log.txt"), "a", encoding="utf-8") as handle:
        handle.write("%s  %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), text))

# ---------------------------------------------------------------- step 01: prepare-run
PACKAGES_RECORDED = ("PyYAML", "openpyxl", "python-docx", "numpy", "scipy", "sympy", "rdata",
                     "pdfplumber", "pypdf", "pyreadr")

def fingerprint_file(path, corner, inputs_dir):
    """Name, corner, size, SHA-256 and content identifier of one input file."""
    with open(path, "rb") as handle:
        data = handle.read()
    return {"corner": corner, "file": os.path.relpath(path, inputs_dir).replace(os.sep, "/"),
            "bytes": len(data), "sha256": sha256_bytes(data), "swhid": swhid_content(data)}

def engine_file_hashes():
    """SHA-256 of every file that makes up the engine (its code, which now holds its prompts and
    reference data, the pipeline and the requirements), so that an evidence pack names exactly the
    code that produced it."""
    import glob
    found = {}
    for pattern in ("*.py", "pipeline.yaml", "requirements.txt"):
        for path in sorted(glob.glob(os.path.join(ENGINE_DIR, pattern), recursive=True)):
            if os.path.isfile(path):
                found["engine/" + os.path.relpath(path, ENGINE_DIR).replace(os.sep, "/")] = file_sha256(path)
    return found

def prepare_run(ctx):
    """Step 01. Fingerprint every input, record the environment and the allow-listed
    settings, and say what changed since the previous run of the same project."""
    import importlib.metadata
    paths, inputs = ctx.options["paths"], ctx.options["inputs"]
    fingerprints = []
    for corner, _, _ in INPUT_FOLDERS:
        fingerprints.extend(fingerprint_file(path, corner, paths.inputs_dir) for path in inputs[corner])
    for key in ("glossary", "tag_rules"):
        if inputs[key]:
            fingerprints.append(fingerprint_file(inputs[key], key, paths.inputs_dir))
    versions = {"python": sys.version.split()[0]}
    for name in PACKAGES_RECORDED:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed"
    previous, changes = previous_run_inputs(paths), []
    if previous is not None:
        before = {f["file"]: f["sha256"] for f in previous["inputs"]}
        now = {f["file"]: f["sha256"] for f in fingerprints}
        changes = ["%s: changed" % n for n in sorted(now) if n in before and before[n] != now[n]]
        changes += ["%s: new" % n for n in sorted(now) if n not in before]
        changes += ["%s: no longer present" % n for n in sorted(before) if n not in now]
    manifest = dict(ctx.options["run"], engine_version=ENGINE_VERSION, versions=versions, engine_files=engine_file_hashes(),
                    settings=ctx.settings, inputs=fingerprints, changes_since_previous_run=changes,
                    previous_run=previous["run_id"] if previous else "",
                    started_at=datetime.datetime.now().isoformat(timespec="seconds"))
    return StepResult({"run_manifest": [manifest]}, {"input files": len(fingerprints)},
                             ["%d input files fingerprinted." % len(fingerprints)])

def previous_run_inputs(paths):
    """The manifest of the latest earlier run of this project, or None."""
    runs = sorted(n for n in os.listdir(paths.project_dir) if n.startswith("Run_") and n < paths.run_id)
    for run in reversed(runs):
        manifest_path = os.path.join(paths.project_dir, run, "_audit", "run_manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as handle:
                return json.load(handle)
    return None

# ---------------------------------------------------------------- Output.xlsx
CELL_WITHHELD = "This text could not be shown in plain words; the technical text is in the audit records."
CUT_NOTE = " ... (cut here; the full text is in the audit files)"
PYTHON_TRACES = re.compile(r"Traceback|\b\w+(Err" r"or|Exception)\b|<class |object at 0x|\bnan\b|\bverifier\d_\w+|"
                           r"[:=(\[]\s*None\b|\{'|\['|^None$")


def plain_cell(value, input_text, store):
    """The last gate before a cell is written. the tool's own words must be free of Python
    traces and of words the wording rule rejects; otherwise the text goes to run_log.txt
    and the cell gets one fixed, plain sentence. Enforces: R1, R10"""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value == int(value) else plain_number(value)
    text = str(value)
    if not input_text:
        own_words = re.sub(r"\u201c.*?\u201d", "", text, flags=re.S)
        if PYTHON_TRACES.search(own_words) or has_banned_wording(own_words):
            log_line(store, "cell text withheld: " + text)
            text = CELL_WITHHELD
    return text if len(text) <= 32000 else text[:31900] + CUT_NOTE


def run_identity(store, paths):
    """What ties a workbook to its run: also written into the workbook's properties."""
    return {"model_id": paths.model_id, "date_initiated": paths.project_date, "run_id": paths.run_id,
            "engine_version": ENGINE_VERSION}

def rows_package_info(store, paths, settings, progress):
    """The rows of Model_Package_Info: identity, inputs, what was read, and the repairs made while reading."""
    identity, rows = run_identity(store, paths), []
    def add(group, item, value):
        rows.append({"group": group, "item": item, "value": value})
    add("Identity", "Model ID", identity["model_id"])
    add("Identity", "Date initiated", identity["date_initiated"])
    add("Identity", "Run", identity["run_id"])
    add("Identity", "Run progress", progress)
    add("Identity", "Engine version", identity["engine_version"])
    manifest = (store.read("run_manifest") or [{}])[0]
    if manifest.get("engine_files"):
        add("Identity", "Engine files fingerprint", sha256_text(canonical_json(manifest["engine_files"]))[:16] +
            " (%d files; the full list is in the run manifest)" % len(manifest["engine_files"]))
    for entry in manifest.get("inputs", []):
        add("Inputs", entry["file"], "SHA-256 %s (%d bytes)" % (entry["sha256"], entry["bytes"]))
    for change in manifest.get("changes_since_previous_run", []):
        add("Inputs", "Changed since run %s" % manifest.get("previous_run", ""), change)
    for info in store.read("package_info"):
        for row in info.get("rows", []):
            add(row["group"], row["item"], row["value"])
    for row in store.read("info_rows"):
        add(row["group"], row["item"], row["value"])
    repairs = {}
    for repair in store.read("read_repairs"):
        repairs.setdefault(repair["file"], []).append(repair["kind"])
    for name in sorted(repairs):
        kinds = sorted(set(repairs[name]))
        add("Repairs made while reading", name, "; ".join("%s (%d)" % (k, repairs[name].count(k)) for k in kinds))
    return rows


MAP_ROLES = {"return": "Final output", "value": "Intermediate value", "column": "Column", "argument": "Parameter",
             "stored data": "Raw input: stored data", "file": "Raw input: file", "number": "Raw input: hard-coded number",
             "outside": "From outside the package"}
MAP_OUTLINE_MAX = 7          # Excel groups rows eight levels deep (outline levels 0 to 7); deeper rows are indented only
MAP_ID_COLUMNS = 12          # the Map ID, one column per level, for filtering; a deeper level joins the last column


def implementation_map(store, settings=None):
    """The rows of Model_Implementation_Map: one row per value the model computes, from each final output
    down to the rawest inputs. A row says one thing: this variable, computed here, by this function, from
    these arguments - and every argument is a row of its own beneath it, where it is the variable. A called
    function is entered with that call's own arguments, and what it computes inside stands under the value
    it produces. Nothing that is not part of a calculation appears: what no final output reaches is not a
    row of this sheet. Enforces: R2, R4, R14"""
    flow = store.read("dataflow")
    if not flow:
        return []
    nodes = {r["node"]: r for r in flow if r["record_type"] == "node"}
    units = store.read("model_units")
    functions = {u["name"]: u for u in units if u["kind"] == KIND_FUNCTION and not u.get("inside")}
    outputs, _, _ = decided_outputs(flow, {})
    by_function = (settings or DEFAULT_SETTINGS)["map_granularity"] == "function"
    rows_max = int((settings or DEFAULT_SETTINGS)["map_rows_max"])
    rows, cut = [], []

    def variable_of(node):
        """The one variable a row is about. What a function returns is the function's own result: its row
        is the function, and the value it returns - the last tie_outputs, say - is that row's child."""
        return node.get("function", "") if node["kind"] == "return" else node["name"]


    def function_of(node):
        """The function that defines this value: for what a function returns, that function; otherwise the
        package function this value calls, else the function named in the code itself (a function of R or
        of another package, which has no unit of its own). A raw input is defined by no function."""
        if node["kind"] not in ("value", "column", "return"):
            return "", ""
        if node["kind"] == "return":
            return node.get("function", ""), functions.get(node.get("function"), {}).get("ref", "")
        calls = [nodes[s] for s in node["from"] if nodes.get(s, {}).get("kind") == "call"]
        if calls:
            callee = calls[0]["callee"]
            return callee, functions.get(callee, {}).get("ref", "")
        code = (node.get("code") or "").split("\n")[0]
        written = re.sub(r"^\s*[A-Za-z._][\w.]*\s*(?:<-|=[^=])", "", code)
        found = re.search(r"(?:([A-Za-z._][\w.]*)::)?([A-Za-z._][\w.]*)\s*\(", written)
        return (found.group(2) if found else ""), ""

    def expand(source, frames, depth=0):
        """One source, resolved to the values that are rows: a call becomes what it was given and what the
        called function computes inside from it; a parameter becomes the argument the call gave it, or its
        default; and, asked for a map by function, a value becomes what it rests on. Everything else is a
        row of its own."""
        record = nodes.get(source)
        if record is None or record["kind"] == "guard" or depth > 60:
            return []
        if record["kind"] == "call":
            callee = record["callee"]
            found = [pair for argument in record["from"] if argument != "%s:return" % callee
                     for pair in expand(argument, frames, depth + 1)]
            if callee in (name for name, _ in frames):
                return found                                     # the function calls itself: its arguments stand, the descent stops
            inner = frames + [(callee, record["bindings"])]
            for inside in nodes.get("%s:return" % callee, {"from": []})["from"]:
                kid = nodes.get(inside, {})
                if kid.get("kind") == "argument" and kid.get("function") == callee:
                    if record["bindings"].get(kid["name"], ["default"]) == ["default"]:
                        found += [pair for value in kid.get("default_from") or [] for pair in expand(value, inner, depth + 1)]
                    continue                                     # a parameter is the argument the call gave, already a row
                found += expand(inside, inner, depth + 1)
            return found
        if record["kind"] == "argument" and record.get("function") == frames[-1][0] and frames[-1][1] is not None:
            given = frames[-1][1].get(record["name"], ["default"])
            if given == ["default"]:
                return [pair for value in record.get("default_from") or [] for pair in expand(value, frames, depth + 1)]
            return [pair for value in given for pair in expand(value, frames[:-1], depth + 1)]
        if by_function and record["kind"] in ("value", "column") and record["from"]:
            return [pair for value in record["from"] for pair in expand(value, frames, depth + 1)]
        return [(source, frames)]

    def children(node, frames):
        """What this value is computed from, each a row of its own beneath it."""
        seen, once = set(), []
        for source in node["from"]:
            for child, child_frames in expand(source, frames):
                key = (child, tuple(name for name, _ in child_frames))
                if key not in seen:                              # the same value twice under one step is one row
                    seen.add(key)
                    once.append((child, child_frames))
        return once                                          # in the order the code gives them: c(overrides_and_caps, tie_outputs)

    def emit(node_id, frames, map_id, level, path):
        node = nodes.get(node_id)
        if node is None or node["kind"] == "guard":
            return
        key = (node_id, tuple(name for name, _ in frames))
        if key in path:                                          # a value that feeds itself: the descent stops
            return
        if len(rows) >= rows_max:
            if not cut:
                cut.append(True)
                rows.append(dict(blank_row(), map_id=map_id, level=level, output_variable="the map was cut here",
                                 arguments="the setting map_rows_max stopped the map; ask for a map by function (map_granularity) or raise it"))
            return
        kids = children(node, frames)
        variable = variable_of(node)
        name, ref = function_of(node)
        row = dict(blank_row(), map_id=map_id, level=level, output_variable=variable, 
                   ov_code=node.get("code") or node.get("file") or "", 
                   function_name=name, fn_ref=ref, role=MAP_ROLES.get(node["kind"], node["kind"]),
                   arguments="; ".join(dict.fromkeys(variable_of(nodes[child]) for child, _ in kids if child in nodes)))
        if node["kind"] == "argument" and frames[-1][1] is None:
            row["role"] = "Raw input: argument of the final output"
        if node["kind"] == "column" and not node["from"]:
            row["role"] = "Raw input: column of the data given"
        if row["role"].startswith("Raw input"):                 # never calculated: where the calculation starts
            row["output_variable"], row["ov_code"] = "%s (terminal input)" % variable, ""
        elif node["kind"] == "return" and node.get("function") in functions:    # the function that assembles it all
            text = functions[node["function"]]["text"].split("\n")
            start = next((n for n, line in enumerate(text) if re.match(r"\s*`?%s`?\s*(<-|=)" % re.escape(node["function"]), line)), 0)
            row["ov_code"] = "\n".join(text[start:]).strip()
        for position, part in enumerate(map_id.split(".")[:MAP_ID_COLUMNS], start=1):
            row["id%d" % position] = ".".join(map_id.split(".")[MAP_ID_COLUMNS - 1:]) if position == MAP_ID_COLUMNS else part
        rows.append(row)
        width = max(2, len(str(len(kids))))
        for position, (child, child_frames) in enumerate(kids, start=1):
            emit(child, child_frames, "%s.%0*d" % (map_id, width, position), level + 1, path | {key})

    for position, output in enumerate(outputs, start=1):
        emit("%s:return" % output, [(output, None)], "%02d" % position, 0, frozenset())
    return rows

def blank_row():
    """Every column of the map, empty: a row fills the ones it has."""
    row = {"map_id": "", "level": 0, "output_variable": "", "ov_code": "",
           "function_name": "", "fn_ref": "", "arguments": "", "role": ""}
    row.update({"id%d" % number: "" for number in range(1, MAP_ID_COLUMNS + 1)})
    return row


def rows_chunks(chunks):
    """The rows of Chunks_Methodology and Chunks_Documentation."""
    return [{"ref": c["ref"], "section": " > ".join(c["heading_chain"]), "kind": c["kind"], "text": c["text"],
             "source_file": c["source_file"]} for c in chunks]


def rows_model_units(units):
    """The rows of Chunks_Model: each a whole piece of code, as written."""
    return [{"ref": u["ref"], "kind": u["kind"], "file": u["file"], "text": u["text"],
             "lines": "%d-%d" % tuple(u["lines"]) if u.get("lines") else ""} for u in units]


def sheet_rows(store, paths, settings, progress):
    """The rows of all five sheets, by sheet name."""
    mapped = implementation_map(store, settings)
    model_rows, doc_rows = rows_model_units(store.read("model_units")), rows_chunks(store.read("chunks_doc"))
    return {"Model_Package_Info": rows_package_info(store, paths, settings, progress),
            "Chunks_Methodology": rows_chunks(store.read("chunks_canon")), "Chunks_Documentation": doc_rows, "Chunks_Model": model_rows,
            "Model_Implementation_Map": mapped}

def check_written_totals(rows, store):
    """The identity of the workbook: every unit read is one row of its sheet, and no row is anything
    else. Raised as a fault of the tool, never as a remark about the model. Enforces: R2"""
    for kind, sheet in (("model_units", "Chunks_Model"), ("chunks_doc", "Chunks_Documentation"), ("chunks_canon", "Chunks_Methodology")):
        read = [record["ref"] for record in store.read(kind)]
        written = [row["ref"] for row in rows[sheet]]
        if sorted(read) != sorted(written) or len(set(written)) != len(written):
            raise EngineFault(
                "The workbook does not hold exactly what was read: %d unit(s) read for %s and %d row(s) written. "
                "This is a defect in the tool, not in the model under review." % (len(read), sheet, len(written)))

# ---------------------------------------------------------------- the workbook layout
# Every sheet of Output.xlsx in order, and every column of each: its header, its colour group, the
# field of the row it shows, its width, and whether it is typed by a person (input_text). One line
# per column. Parsed on every call, so a caller's change stays its own. Enforces: R10
WORKBOOK_LAYOUT_YAML = r'''colours: {identity: D9E1F2, code_text: E2EFDA, methodology: FCE4D6, documentation: E4DFEC, assessments: DDEBF7}
sheets:
- name: Model_Package_Info
  columns:
  - {header: Group, group: identity, field: group, width: 26}
  - {header: Item, group: identity, field: item, width: 40}
  - {header: Value, group: assessments, field: value, width: 90}
- name: Chunks_Methodology
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Section (heading chain), group: identity, field: section, width: 44}
  - {header: Type, group: identity, field: kind, width: 11}
  - {header: Text, group: methodology, field: text, width: 90, input_text: true}
  - {header: Source file, group: identity, field: source_file, width: 28}
- name: Chunks_Documentation
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Section (heading chain), group: identity, field: section, width: 44}
  - {header: Type, group: identity, field: kind, width: 11}
  - {header: Text, group: documentation, field: text, width: 90, input_text: true}
  - {header: Source file, group: identity, field: source_file, width: 28}
- name: Chunks_Model
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Kind, group: identity, field: kind, width: 20}
  - {header: File, group: identity, field: file, width: 30}
  - {header: Lines, group: identity, field: lines, width: 10}
  - {header: Text, group: code_text, field: text, width: 80, input_text: true}
- name: Model_Implementation_Map
  columns:
  - {header: MapID1, group: identity, field: id1, width: 7}
  - {header: MapID2, group: identity, field: id2, width: 7}
  - {header: MapID3, group: identity, field: id3, width: 7}
  - {header: MapID4, group: identity, field: id4, width: 7}
  - {header: MapID5, group: identity, field: id5, width: 7}
  - {header: MapID6, group: identity, field: id6, width: 7}
  - {header: MapID7, group: identity, field: id7, width: 7}
  - {header: MapID8, group: identity, field: id8, width: 7}
  - {header: MapID9, group: identity, field: id9, width: 7}
  - {header: MapID10, group: identity, field: id10, width: 7}
  - {header: MapID11, group: identity, field: id11, width: 7}
  - {header: MapID12, group: identity, field: id12, width: 7}
  - {header: Level, group: identity, field: level, width: 7}
  - {header: Output Variable, group: identity, field: output_variable, width: 28}
  - {header: Output Variable - Model Code, group: code_text, field: ov_code, width: 60}
  - {header: Function Name, group: identity, field: function_name, width: 24}
  - {header: Function Name - Model Ref, group: assessments, field: fn_ref, width: 16, links_to: Chunks_Model}
  - {header: Arguments, group: assessments, field: arguments, width: 46}
'''

def load_layout():
    """The workbook layout: every sheet and every column of Output.xlsx."""
    return yaml.safe_load(WORKBOOK_LAYOUT_YAML)

def write_sheet(sheet, sheet_layout, rows, colours, settings, store, index=None):
    """One generic writer for every sheet: header row and first column frozen, filter on
    the header, wrapped text, no merged cells, reviewer columns yellow and unlocked."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.hyperlink import Hyperlink
    columns = sheet_layout["columns"]
    wrap = Alignment(wrap_text=True, vertical="top")
    for number, column in enumerate(columns, start=1):
        header = column["header"]
        cell = sheet.cell(row=1, column=number, value=header)
        cell.font, cell.alignment = Font(bold=True), wrap
        cell.fill = PatternFill("solid", start_color=colours[column["group"]])
        sheet.column_dimensions[get_column_letter(number)].width = column.get("width", 20)
    for row_number, row in enumerate(rows, start=2):
        for number, column in enumerate(columns, start=1):
            value = row.get(column["field"])
            cell = sheet.cell(row=row_number, column=number, value=plain_cell(value, column.get("input_text"), store))
            cell.alignment = wrap
    if sheet_layout["name"] == "Model_Implementation_Map":     # collapsible: each parent a summary row above its members
        sheet.sheet_properties.outlinePr.summaryBelow = False
        sheet.column_dimensions.group(get_column_letter(1), get_column_letter(MAP_ID_COLUMNS), outline_level=1)
        at_variable = [c["field"] for c in columns].index("output_variable") + 1
        for number, row in enumerate(rows, start=2):
            level = int(row.get("level") or 0)
            if level:
                sheet.row_dimensions[number].outline_level = min(level, MAP_OUTLINE_MAX)
            sheet.cell(row=number, column=at_variable).alignment = Alignment(wrap_text=True, vertical="top", indent=min(level, 15))
    index = index or {}
    for number, column in enumerate(columns, start=1):         # a reference is a link to the row that holds it
        target = column.get("links_to")
        if not target:
            continue
        for row_number, row in enumerate(rows, start=2):
            where = (index.get(target) or {}).get(row.get(column["field"]))
            if where:
                cell = sheet.cell(row=row_number, column=number)
                cell.hyperlink = Hyperlink(ref=cell.coordinate, location="'%s'!A%d" % (target, where))
                cell.style = "Hyperlink"
    last = get_column_letter(len(columns))
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = "A1:%s%d" % (last, max(1, len(rows) + 1))
    if settings["protect_sheets"]:
        sheet.protection.sheet = True
        sheet.protection.autoFilter = False          # False = not locked: filtering stays possible
        sheet.protection.formatColumns = False

def build_workbook(store, paths, settings, progress, target):
    """Build Output.xlsx on local disk from the record of the run. All five sheets always
    exist; a sheet whose step has not run shows its header only."""
    import openpyxl
    layout = load_layout()
    rows = sheet_rows(store, paths, settings, progress)
    check_written_totals(rows, store)
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    index = {"Chunks_Model": {row["ref"]: number for number, row in enumerate(rows.get("Chunks_Model") or [], start=2)}}
    for sheet_layout in layout["sheets"]:
        sheet = workbook.create_sheet(sheet_layout["name"])
        write_sheet(sheet, sheet_layout, rows[sheet_layout["name"]], layout["colours"], settings, store, index)
    workbook.properties.title = "the tool Output"
    workbook.properties.description = canonical_json(run_identity(store, paths))
    workbook.save(target)
    return rows

# ---------------------------------------------------------------- rebuilding the outputs
def file_sha256(path):
    """SHA-256 of a file's bytes."""
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read())


def progress_text(store, waiting_message):
    """Where the run stands, in one or two plain sentences."""
    records = store.read("step_records")
    if not records:
        return "The run has been opened; no step has finished yet."
    last = records[-1]
    text = "Step %s (%s) is the last finished step." % (last["step_id"], last["name"])
    return text + (" " + waiting_message if waiting_message else "")

def rebuild_outputs(store, paths, settings, waiting_message):
    """Rebuild Output.xlsx (and the report once flagged items exist) on local disk and copy
    them whole into the run folder. The guard: a workbook in the run folder that differs from the last
    one the tool wrote is a reviewer's work in progress and is never overwritten before it has
    been read in. Afterwards the run folder holds exactly the two files. Enforces: R6, R12"""
    work = os.path.join(store.local_dir, "work")
    os.makedirs(work, exist_ok=True)
    progress = progress_text(store, waiting_message)
    manifest = (store.read("run_manifest") or [{}])[0]
    target = os.path.join(paths.outputs_dir, "Output.xlsx")
    guarded = (os.path.exists(target) and manifest.get("last_workbook_sha256")
               and file_sha256(target) not in (manifest["last_workbook_sha256"], manifest.get("last_upload_sha256")))
    local_workbook = os.path.join(work, "Output.xlsx")
    build_workbook(store, paths, settings, progress, local_workbook)
    if guarded:
        log_line(store, "Output.xlsx in the run folder was edited and not yet read in: left untouched")
    else:
        copy_whole(local_workbook, target)
        if manifest:
            update_manifest(store, {"last_workbook_sha256": file_sha256(target)})
    store.sync()
    return not guarded

# ---------------------------------------------------------------- determinations
def contents_of(path):
    """Every byte string a file holds, looking INSIDE the compressed ones: the call log is gzip,
    and the workbook and the report are ZIP archives, so a token written into any of them would
    be invisible to a search of the raw bytes. Yields the raw bytes first, then each member of a
    ZIP and the decompressed stream of a gzip. Enforces: R8"""
    with open(path, "rb") as handle:
        raw = handle.read()
    yield raw
    try:
        if raw.startswith(b"\x1f\x8b"):
            yield gzip.decompress(raw)
        elif raw.startswith(b"PK\x03\x04"):
            import zipfile
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for member in archive.namelist():
                    yield archive.read(member)
    except Exception:
        return                                       # a damaged archive is caught by the other lines of the verification

def verify_evidence_pack(paths, settings, live=None):
    """Works from a run folder and the Inputs folder alone. Returns rows (what was checked,
    "Confirmed" or "Not confirmed", detail). Re-reading the inputs is reperformance: every
    content hash is computed again from the input files and compared with the record."""
    store, rows = AuditStore(paths.audit_dir, paths.audit_dir), []        # read the pack itself, not the scratch copy of this driver
    def line(what, good, detail=""):
        """good is True, False, or None for a check the run has not reached yet - which is not a failure
        and must not read as one. Found on a real run that stopped after step 06: the coverage line said
        Not confirmed, as if the pack had been tampered with."""
        rows.append((what, "Confirmed" if good else "Not reached yet" if good is None else "Not confirmed", detail))
    manifest = (store.read("run_manifest") or [{}])[0]
    changed = [e["file"] for e in manifest.get("inputs", []) if not os.path.exists(os.path.join(paths.inputs_dir, e["file"]))
               or file_sha256(os.path.join(paths.inputs_dir, e["file"])) != e["sha256"]]
    line("Input files have the recorded fingerprints", not changed, ", ".join(changed))
    installed, recorded = engine_file_hashes(), manifest.get("engine_files", {})
    other = sorted(name for name in set(installed) | set(recorded) if installed.get(name) != recorded.get(name))
    line("The engine files that produced this run are the ones installed here", not other, ", ".join(other[:5]))
    options = {"inputs": list_input_files(paths.inputs_dir)}
    context = StepContext(settings, options, lambda kind: [], None, paths.local_dir, lambda text: None)
    for kind, function in (("chunks_canon", read_methodology), ("chunks_doc", read_documentation),
                           ("model_units", read_package)):
        fresh = {to_plain(r)["ref"]: to_plain(r)["content_hash"] for r in function(context).records.get(kind, [])}
        recorded = {r["ref"]: r["content_hash"] for r in store.read(kind)}
        differing = sorted(ref for ref in set(fresh) | set(recorded) if fresh.get(ref) != recorded.get(ref))
        sheet = {"chunks_canon": "Chunks_Methodology", "chunks_doc": "Chunks_Documentation", "model_units": "Chunks_Model"}.get(kind, kind)
        line("Re-reading the inputs gives the recorded content hashes (%s)" % sheet, not differing, ", ".join(differing[:5]))
    written = {kind: len(store.read(kind)) for kind in ("chunks_canon", "chunks_doc", "model_units")}
    line("Every unit read is in the record", all(written.values()),
         ", ".join("%s: %d" % pair for pair in sorted(written.items())))
    identity = run_identity(store, paths)
    try:
        import openpyxl
        found = json.loads(openpyxl.load_workbook(os.path.join(paths.outputs_dir, "Output.xlsx"), read_only=True).properties.description)
        line("The workbook carries this run's ids and fingerprints", all(found.get(k) == v for k, v in identity.items()))
    except Exception:
        line("The workbook carries this run's ids and fingerprints", False, "Output.xlsx could not be opened")
    secrets = [value.encode("utf-8") for value in (list(live.recent_tokens) if live else []) if value]
    leaked = []
    for folder, _, names in os.walk(paths.run_dir):
        for name in names:
            leaked += [name for data in contents_of(os.path.join(folder, name)) for value in secrets if value in data]
    line("No access token was written into the run folder", not leaked, ", ".join(sorted(set(leaked))))
    return rows

def combine(ctx, *parts):
    """One step that carries out several: each part in order, everything they record kept, their counts
    and their messages side by side. A later part reads what the earlier ones have just recorded, as it
    would if each were still a step of its own - the records of a step reach the store only when the step
    ends. Enforces: R2"""
    records, counts, messages = {}, {}, []
    for part in parts:
        stored = ctx.read
        so_far = {kind: [to_plain(row) for row in rows] for kind, rows in records.items()}   # as the store would hand them back
        reading = dataclasses.replace(ctx, read=lambda kind, stored=stored, so_far=so_far: list(stored(kind)) + so_far.get(kind, []))
        found = part(reading)
        for kind, rows in (found.records or {}).items():
            records.setdefault(kind, []).extend(rows)
        for name, value in (found.counts or {}).items():     # two parts that count the same thing add up
            counts[name] = counts.get(name, 0) + value if isinstance(value, (int, float)) and isinstance(counts.get(name, 0), (int, float)) else value
        messages += found.messages or []
    return StepResult(records, counts, messages)

def read_inputs(ctx):
    """Step 02, read-inputs: the methodology, the model documentation and the model package, each read
    into units, in that order. Enforces: R2, R7"""
    return combine(ctx, read_methodology, read_documentation, read_package)

def build_map(ctx):
    """Step 03, build-map: the data flow of the package, read by flowR. Enforces: R2, R4, R14"""
    return trace_dataflow(ctx)


STEP_FUNCTIONS = {        # every function that pipeline.yaml is allowed to name. Enforces: R11
    "read_methodology": read_methodology,
    "read_documentation": read_documentation,
    "read_package": read_package,
    "trace_dataflow": trace_dataflow,
    "prepare_run": prepare_run,
    "read_inputs": read_inputs,
    "build_map": build_map}

# ---------------------------------------------------------------- the notebook: four cells, each one call
# Everything the notebook does is here, so that it holds no code of its own but the organisation's chat():
# cell 1 is setup(dbutils), cell 2 check_chat(chat), cell 3 review(), cell 4 verify(). The session - the
# widgets, the chat() that answered, the run being worked on - is kept in NOTEBOOK, not in the notebook.
REQUIRED_PACKAGES = ("yaml", "openpyxl", "numpy", "rdata")   # what the engine imports; installed only if missing
WIDGETS = (("llm_endpoint", "", "01 LLM endpoint"), ("llm_token", "", "02 LLM token"),
           ("model_id", "", "03 Model ID"), ("project", "", "04 Project date (empty = new project today)"))
OLD_WIDGETS = ("llm_user_id", "reviewer_role", "run", "projects_dir", "scratch_dir", "concept_subject", "flowr_archive",
               "reviewer_id", "jfrog_index_url", "concurrency_limit", "token_cap")
PYPI = "https://pypi.org/simple/"          # where every package comes from: named here, so no pip setting of the cluster redirects it
NOTEBOOK = {"dbutils": None, "home": "", "projects": "", "user": "", "live": None, "chat": None, "paths": None, "result": None}

def databricks_user(dbutils):
    """Who runs the notebook, as Databricks knows them: the notebook context's user name; on a cluster that keeps
    that context from Python, Spark's current_user(); outside Databricks, the system user."""
    try:
        return dbutils.notebook.entry_point.getDbutils().notebook().getContext().userName().get()
    except Exception:
        pass
    try:
        from pyspark.sql import SparkSession
        session = SparkSession.getActiveSession()
        if session is not None:
            return session.sql("SELECT current_user()").first()[0]
    except Exception:
        pass
    return getpass.getuser()

def live(name):
    """The endpoint and token, read from the widgets at the moment chat() calls - a token pasted into widget 02
    while a run works is used by its next call - and the user id (asked for as "reviewer_id"), from Databricks. Enforces: R8"""
    session = NOTEBOOK["live"] = NOTEBOOK["live"] or LiveValues()
    try:
        widgets = NOTEBOOK["dbutils"].widgets
        session.update(widgets.get("llm_endpoint"), widgets.get("llm_token"), NOTEBOOK["user"])
    except Exception:
        pass                                        # no notebook, or a widget read failed: the last values stand
    return session.get(name)

def notebook_folder(dbutils):
    try:
        path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
        return os.path.dirname(path if path.startswith("/Workspace") else "/Workspace" + path)
    except Exception:
        return os.getcwd()

def setup(dbutils, home=None, projects=None):
    """Cell 1: the widgets, the packages the engine needs (installed only if one is missing), flowR, and
    what to do next. Safe to run any number of times; run it again after anything restarts Python."""
    import importlib.util
    widgets = dbutils.widgets
    for name, default, label in WIDGETS:              # made before anything is installed: a bare cluster works
        try:
            widgets.get(name)
        except Exception:
            widgets.text(name, default, label)
    for name in OLD_WIDGETS:                          # widgets of an earlier notebook, no longer used
        try:
            widgets.remove(name)
        except Exception:
            pass
    home = home or notebook_folder(dbutils)
    NOTEBOOK.update(dbutils=dbutils, home=home, projects=projects or os.path.join(home, "Projects"), user=databricks_user(dbutils))
    missing = [name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]
    if missing:
        install(missing, dbutils, os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt"))
        return
    print("Folder:", home, "| Python", sys.version.split()[0], "| engine", ENGINE_VERSION)
    for name in REQUIRED_PACKAGES + ("pdfplumber", "pypdf"):
        found = importlib.util.find_spec(name)
        print("  %-11s %s" % (name, "installed" if found else "not installed" + ("" if name in ("pdfplumber", "pypdf") else " - run this cell again")))
    token = live("llm_token")
    print("Endpoint set:", bool(live("llm_endpoint")), "| token:", ("%d characters" % len(token)) if token else "not set")
    staged = os.path.join(home, FLOWR_URL.format(FLOWR_VERSION).rsplit("/", 1)[-1])
    try:                                              # flowR reads the R code: fetched once, checked against its SHA-256
        print("flowR %s ready in %s" % (FLOWR_VERSION, flowr_ready(staged if os.path.exists(staged) else "")))
    except Exception as problem:
        print("flowR IS NOT READY: %s" % problem)
        if problem.__class__.__module__.startswith("urllib"):   # only a failed download is helped by putting it here
            print("The cluster could not download it. Download %s on an approved machine and put it in %s, next to this"
                  " notebook." % (FLOWR_URL.format(FLOWR_VERSION), home))
    print("\nTHE ENGINE IS READY. What happens next:")
    print("  Cell 2  paste your organisation's chat(), check it answers, and see where to put your files.")
    print("  Cell 3  read the inputs and run the review; it prints what each step did.")
    print("  Cell 4  check the finished run folder against its own record.")
    print("Widgets 01 and 02 carry the endpoint and the token; 03 the model id; 04 the project date.")
    print("Your user id is taken from Databricks: %s. Paste a fresh token into widget 02 at any time - chat() reads it" % NOTEBOOK["user"])
    print("at the moment it calls.")
    print("Next: cell 2.")

def pip_said(stderr):
    """What pip said, without any credentials of an index URL, and what its most common failure means."""
    text = re.sub(r"//[^/@\s]+@", "//...@", stderr or "")[-1500:]
    missing = re.findall(r"satisfies the requirement ([\w.\-\[\]]+)", stderr or "")
    if "from versions: none" in (stderr or ""):
        text += ("\nPyPI offered no version of %s that fits this cluster's Python, or the cluster cannot reach %s: its network "
                 "has to let the cluster reach PyPI." % (missing[0] if missing else "that package", PYPI))
    elif "ResolutionImpossible" in (stderr or "") or "conflicting dependencies" in (stderr or ""):
        text += "\nThe packages asked for cannot be installed together; the lines above say which."
    return text

def install(missing, dbutils, requirements):
    """Install what the engine needs from PyPI, the runtime's own packages pinned as they are, and restart Python
    only if those still import together afterwards."""
    import importlib.metadata
    hide = lambda text: re.sub(r"//[^/@\s]+@", "//...@", text or "")    # no credentials of an index URL are shown
    pins = []
    for name in ("numpy", "pandas", "pyarrow", "scipy"):
        try:
            pins.append("%s==%s" % (name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            pass
    constraints = os.path.join(tempfile.mkdtemp(prefix="verifier_"), "constraints.txt")
    with open(constraints, "w") as handle:
        handle.write("\n".join(pins) + "\n")
    command = [sys.executable, "-m", "pip", "install", "-r", requirements, "-c", constraints, "--index-url", PYPI]
    print("Installing", ", ".join(missing), "| kept as the runtime has them:", ", ".join(pins) or "none found")
    done = subprocess.run(command, capture_output=True, text=True)
    if done.returncode:
        print("The install did not finish. What pip said:\n" + pip_said(done.stderr))
        print("Nothing the runtime needs was changed.")
        return
    with open(requirements, encoding="utf-8") as handle:
        wanted = handle.read().split("# --- optional ---")
    if len(wanted) > 1:
        spare = os.path.join(tempfile.gettempdir(), "optional.txt")
        with open(spare, "w", encoding="utf-8") as handle:
            handle.write(wanted[1])
        extra = subprocess.run(command[:4] + ["-r", spare] + command[6:], capture_output=True, text=True)
        print("Optional packages (the PDF readers):", "installed." if not extra.returncode else "not installed; a PDF will say it could not be read.")
    probe = subprocess.run([sys.executable, "-c", "import numpy, pandas, pyarrow"], capture_output=True, text=True)
    if probe.returncode:
        print("STOPPED BEFORE RESTARTING PYTHON: the runtime's own packages no longer import together (%s)." % hide((probe.stderr or "").strip())[-300:])
        print("Restarting now would crash this notebook session. Detach this notebook from the cluster and attach it again to undo the install.")
        return
    still = subprocess.run([sys.executable, "-c", "import " + ", ".join(missing)], capture_output=True, text=True)
    if still.returncode:
        print("STOPPED BEFORE RESTARTING PYTHON: %s is still missing after the install, so restarting would only bring "
              "this cell back here." % ", ".join(missing))
        print("What Python said:\n" + hide(still.stderr)[-600:])
        print("Check that engine/requirements.txt names it, and that PyPI carries it for this cluster's Python.")
        return
    print("Installed. Restarting Python; then run this cell once more.")
    dbutils.library.restartPython()

def notebook_settings():
    return make_settings({"reviewer_id": NOTEBOOK["user"]})

def check_chat(chat):
    """Cell 2: ask the organisation's chat() one question and, once it answers, make the project's three
    Inputs folders and say what belongs in each."""
    if NOTEBOOK["dbutils"] is None:
        print("Run cell 1 first.")
        return
    NOTEBOOK["chat"] = chat
    try:
        reply = chat("Reply with the single word OK.", "Reply with the single word OK.")["answer"]
        print("chat() answered:", str(reply)[:60])
    except Exception as problem:
        print("chat() did not answer (%s: %s). Check widgets 01 and 02 - and that the gateway knows your Databricks user id, %s -"
              " then run this cell again." % (type(problem).__name__, problem, NOTEBOOK["user"]))
        return
    widgets = NOTEBOOK["dbutils"].widgets
    project_dir, missing = setup_project(NOTEBOOK["projects"], widgets.get("model_id"), widgets.get("project"))
    print("\nPUT YOUR FILES IN THESE THREE FOLDERS, then run cell 3:")
    for _, folder, note in INPUT_FOLDERS:
        print("  %s\n      %s" % (os.path.join(project_dir, "Inputs", folder), note))
    print("\nOne methodology file, the model package as it ships (.tar.gz, .zip or the unpacked folder), and the")
    print("model documentation. A folder with nothing in it stops the run and says so, rather than reading around it.")
    print("\nStill empty: " + "; ".join(missing) if missing else "\nAll three folders have files in them. Next: cell 3.")

def open_current():
    """The run the widgets name: the one this session opened, or a new one; None, with what to do, while the
    project's folders are still empty."""
    widgets = NOTEBOOK["dbutils"].widgets
    model_id, project = widgets.get("model_id"), widgets.get("project")
    _, missing = setup_project(NOTEBOOK["projects"], model_id, project)
    if missing:
        print("\n".join(missing))
        print("Put the files in, then run cell 3.")
        return None
    paths = NOTEBOOK["paths"]
    if paths is None or paths.model_id != model_id or (project and paths.project_date != project):
        paths = NOTEBOOK["paths"] = open_run(NOTEBOOK["projects"], model_id, project)   # a new session starts a new run
    return paths

def review():
    """Cell 3: read the inputs and map how the model computes what it returns, in this cell; then say
    what each step did. A step already finished is never repeated."""
    if NOTEBOOK["dbutils"] is None:
        print("Run cell 1 first.")
        return
    paths = open_current()
    if paths is None:
        return
    settings = notebook_settings()
    result = NOTEBOOK["result"] = run_pipeline(paths, settings)
    print(result["message"])
    store = open_store(paths, settings)
    print("\nWhat each step did:")
    for record in store.read("step_records"):
        print("  step %s %-14s %s" % (record["step_id"], record["name"], ", ".join("%s: %s" % item for item in sorted((record["counts"] or {}).items()))))
        for message in record["messages"]:
            print("      " + message)
    print("\nRun folder:", paths.run_dir)
    print("Open Output.xlsx there: the three Chunks sheets show everything that was read, and Model_Implementation_Map")
    print("how the model computes what it returns.")
    print("Then run cell 4 to check the run folder against its own record.")

def verify():
    """Cell 4: check the run folder against its own record."""
    paths = NOTEBOOK["paths"]
    if paths is None:
        print("Cell 3 has not read the inputs yet. Run cell 3 first.")
        return
    print("Verifying the evidence pack:")
    for what, verdict, detail in verify_evidence_pack(paths, notebook_settings(), live=NOTEBOOK["live"] or LiveValues()):
        print("  %-62s %-16s %s" % (what, verdict, detail))
    print("\nRun folder:", paths.run_dir, "- Output.xlsx is the deliverable; _audit/Audit_Log.xlsx is the record")
    print("of the run: every step, every record, and every exchange with the model.")
