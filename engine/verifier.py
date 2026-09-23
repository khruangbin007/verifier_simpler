"""
Verifier 0.0.4 - verifier.py - the whole engine, in one file. For every reviewer.

Reads a model's methodology, its package of code and data, and its documentation, and maps how the model
computes what it returns, from each final output down to its rawest inputs. The documents are read by
Docling, the R code by flowR. One deliverable: Output.xlsx. Everything a run does is recorded.

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
from email import policy


# ================================================================================================
# the contracts, the reading floor and the front door
# ================================================================================================
# ---------------------------------------------------------------- the contracts: what every record is, and the words the tool may use
ENGINE_VERSION = "0.0.3"

# ---------------------------------------------------------------- vocabulary (Appendix B)


KIND_FUNCTION, KIND_FORMULA, KIND_TOPLEVEL = "Function", "Formula statement", "Top-level statement"
KIND_TEST, KIND_TABLE, KIND_OBJECT = "Test block", "Parameter table", "Parameter object"
KIND_ROXYGEN, KIND_HELP, KIND_VIGNETTE = "Roxygen block", "Help page", "Vignette text"
KIND_COMPILED, KIND_NOT_READ, KIND_OTHER = "Compiled code", "File not read", "Other file"
UNIT_KINDS = (KIND_FUNCTION, KIND_FORMULA, KIND_TOPLEVEL, KIND_TEST, KIND_TABLE, KIND_OBJECT,
              KIND_ROXYGEN, KIND_HELP, KIND_VIGNETTE, KIND_COMPILED, KIND_NOT_READ, KIND_OTHER)

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
class Chunk:
    """One citable unit of a document: a paragraph, a table, a figure or an equation, under its headings."""
    ref: str; corner: str; source_file: str; kind: str; heading_chain: tuple; text: str; content_hash: str

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


# ---------------------------------------------------------------- the expression tree





# ================================================================================================

# ---------------------------------------------------------------- the prompts
# Every question the tool asks, as the model sees it: a version line, the system half, the main half
# with [[UNIT]] and similar places the question builder fills. The text is exact - a question's id is
# the hash of its prompt, and recorded answers are found by that id - so a changed word here is a new
# version and asks new questions. Enforces: R3, R5, R9


# ---------------------------------------------------------------- element helpers



# ---------------------------------------------------------------- baseline slicing: what a document's shape says









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

# A format the tool does not read, what it is in plain words, and what to do about it.

# The name a format goes by in what the analyst reads.




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

# ---------------------------------------------------------------- the linear-notation parser

# ---------------------------------------------------------------- reference data of the reader
# The tag rules: which tag of a document is what (heading, paragraph, table, ...), the numbering
# schemes. An analyst's Inputs/tag_rules.yaml is laid
# over these for one project and always wins. Kept as YAML text and parsed on every call, so that a
# caller that changes the rules it was given changes only its own copy. Enforces: R9

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








# ---------------------------------------------------------------- equation markup -> linear notation








# ---------------------------------------------------------------- format from content, and repairs





# ---------------------------------------------------------------- tag rules and the block walker

# ---------------------------------------------------------------- discovering an unfamiliar schema




















# ---------------------------------------------------------------- MHTML (a web page saved as one file)


# ---------------------------------------------------------------- .docx









# ---------------------------------------------------------------- .pdf





# ---------------------------------------------------------------- levels, references, chunks








# ---------------------------------------------------------------- the two steps


# ---------------------------------------------------------------- the methodology and the documentation, read by Docling
# Docling reads every document into its parts - headings, paragraphs, tables, figures, equations - and its
# hierarchical chunker makes one unit of each part, with the headings above it. It runs in a process of its own,
# from a folder of its own: it needs pandas 2 and PyTorch, which a managed runtime may not carry, and the
# runtime's own packages are never changed for it. What Docling does not read itself (XML, saved web archives,
# plain text) is first turned here into a page it does read.
DOCLING_MODELS = ""                       # Docling's model folder, when one is staged next to the notebook
DOCLING_HOME = {}                         # where Docling runs from, once found: {"path": its folder, or "" for the runtime}
UNIT_KIND_OF_LABEL = (("table", "Table"), ("picture", "Figure"), ("formula", "Equation"))
DOCLING_WORKER = r'''
"""Docling, in a process of its own: reads each file of a request into units - [heading chain, kind, text] -
and writes them back as JSON. Started by verifier.docling_read; it never imports the engine. It makes no network
connection: the documents never leave this machine, and Docling's models come from the staged folder."""
import io, json, sys, importlib.metadata

def no_network(event, args):                     # before anything is imported: no host looked up, no connection made
    local = (None, "", "localhost", "127.0.0.1", "::1")
    if event == "socket.getaddrinfo" and args and args[0] not in local:
        raise OSError("the Docling process makes no network connection (%s was asked for)" % (args[0],))
    if event == "socket.connect" and isinstance(args[1], tuple) and args[1] and args[1][0] not in local:
        raise OSError("the Docling process makes no network connection (%s was asked for)" % (args[1][0],))
sys.addaudithook(no_network)

def refused_opencv():
    """On a FIPS-mode machine, the OpenCV about to be loaded when it carries an OpenSSL with Red Hat's FIPS self-test
    (OpenCV 4.13 on): that self-test fails for a copy inside a wheel and stops the whole process. OpenCV 4.12 carries
    a plain OpenSSL and is loaded. Returns the refused library, or ""."""
    import glob, importlib.util, os
    try:
        fips = open("/proc/sys/crypto/fips_enabled").read().strip() == "1"
    except OSError:
        fips = False
    if not (fips or os.environ.get("OPENSSL_FORCE_FIPS_MODE")):
        return ""
    spec = importlib.util.find_spec("cv2")
    folder = os.path.dirname(os.path.dirname(spec.origin)) if spec and spec.origin else ""
    for library in glob.glob(os.path.join(folder, "opencv*.libs", "libcrypto*")) if folder else []:
        with open(library, "rb") as handle:
            if b"crypto/fips/fips.c" in handle.read():
                return library
    return ""

class NoOpenCV:                                  # a refused OpenCV: its import fails - PDF tables need it, and say so - instead of
    def __init__(self, library):                 # its OpenSSL stopping the process and every file with it
        self.library = library
    def find_spec(self, name, path=None, target=None):
        if name == "cv2" or name.startswith("cv2."):
            raise ImportError("this OpenCV carries an OpenSSL whose FIPS self-test fails on this machine (%s): Docling's folder "
                              "needs opencv-python-headless below 4.13 - run cell 1" % self.library.rsplit("/", 1)[-1])
        return None
if refused_opencv():
    sys.meta_path.insert(0, NoOpenCV(refused_opencv()))
request = json.load(open(sys.argv[1], encoding="utf-8"))
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import HeadingHierarchyOptions, PdfPipelineOptions
from docling_core.transforms.chunker import HierarchicalChunker
options = PdfPipelineOptions(do_ocr=False, artifacts_path=request["models"] or None, generate_parsed_pages=True)
options.heading_hierarchy_options = HeadingHierarchyOptions(enabled=True)   # a PDF's heading levels: outline, numbering, type
convert = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}).convert
chunk, kinds = HierarchicalChunker().chunk, request["kinds"]
label = lambda item: str(getattr(item.label, "value", item.label))
def version_of(*names):
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return ""
answer = {"version": version_of("docling-slim", "docling"), "files": []}
for name, path in request["files"]:
    try:
        with open(path, "rb") as handle:
            document = convert(DocumentStream(name=name, stream=io.BytesIO(handle.read()))).document
        title = next((item.text.strip() for item in document.texts if label(item) == "title"), "")
        units = []
        for piece in chunk(document):
            chain = list(piece.meta.headings or [])
            chain = [title] + chain if title and chain[:1] != [title] else chain     # the document's title heads every chain
            found = {label(item) for item in piece.meta.doc_items}
            if piece.text.strip():
                units.append([chain, next((kind for part, kind in kinds if part in found), "Paragraph"), piece.text])
        answer["files"].append({"units": units})
    except Exception as problem:                     # one file that cannot be read never stops the others
        answer["files"].append({"error": ("%s: %s" % (type(problem).__name__, problem))[:300]})
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(answer, handle)
'''

def docling_folder():
    """Docling's own folder: on the machine's local disk, and this system user's own - a shared cluster runs each
    notebook session as a user of its own."""
    base = "/local_disk0/tmp" if os.path.isdir("/local_disk0/tmp") else tempfile.gettempdir()
    return os.path.join(base, "docling-%d" % os.getuid())

def docling_environment(folder):
    """The environment a Docling process runs in: its folder first on the path, ahead of the runtime's packages, and
    Hugging Face offline - Docling's models are read from the staged folder, never fetched."""
    environment = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")
    if folder:
        environment["PYTHONPATH"] = folder + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    return environment

def docling_requirements():
    """engine/requirements-docling.txt, and the fingerprint of what it asks for."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements-docling.txt")
    return path, file_sha256(path)

def docling_ready():
    """Where Docling runs from: its own folder, or "" when the runtime itself carries it; None when it is nowhere yet.
    A folder installed from other requirements than today's is out of date: it counts as nowhere, and is made again."""
    if "path" not in DOCLING_HOME:
        for folder in (docling_folder(), ""):         # its own folder first: the runtime's copy, if any, may not fit
            if folder and not os.path.isdir(folder):
                continue
            if folder:
                try:
                    with open(os.path.join(folder, ".requirements-sha256")) as handle:
                        current = handle.read().strip() == docling_requirements()[1]
                except OSError:
                    current = False
                if not current:
                    continue
            probe = subprocess.run([sys.executable, "-s", "-c", "import docling, docling_core"], env=docling_environment(folder),
                                   capture_output=True, text=True, timeout=600)
            if probe.returncode == 0:
                DOCLING_HOME["path"] = folder
                break
    return DOCLING_HOME.get("path")

def docling_install():
    """Install Docling from PyPI into its own folder - never into the runtime's packages - made anew: pip adds to a
    folder but never takes out what the requirements no longer ask for. Returns what pip said when it failed, else ""."""
    requirements, fingerprint = docling_requirements()
    folder = docling_folder()
    shutil.rmtree(folder, ignore_errors=True)
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--target", folder, "-r", requirements, "--index-url", PYPI],
                          capture_output=True, text=True)
    DOCLING_HOME.clear()
    if done.returncode:
        return done.stderr
    with open(os.path.join(folder, ".requirements-sha256"), "w") as handle:
        handle.write(fingerprint)
    return ""

def docling_read(pages):
    """Every page of a corner read by ONE Docling process - its models are loaded once - into
    {"version", "files": one {"units"} or {"error"} per page, in order}."""
    folder = docling_ready()
    if folder is None:
        return {"version": "", "files": [{"error": "Docling is not installed here - run cell 1"} for _ in pages]}
    with tempfile.TemporaryDirectory(prefix="docling-") as work:
        request = {"models": DOCLING_MODELS, "kinds": UNIT_KIND_OF_LABEL, "files": []}
        for number, (name, data) in enumerate(pages):
            request["files"].append([name, os.path.join(work, "%04d" % number)])
            with open(request["files"][-1][1], "wb") as handle:
                handle.write(data)
        for file_name, text in (("worker.py", DOCLING_WORKER), ("request.json", json.dumps(request))):
            with open(os.path.join(work, file_name), "w", encoding="utf-8") as handle:
                handle.write(text)
        answer = os.path.join(work, "answer.json")
        done = subprocess.run([sys.executable, "-s", os.path.join(work, "worker.py"), os.path.join(work, "request.json"), answer],
                              env=docling_environment(folder), capture_output=True, text=True, cwd=work, timeout=3600)
        if done.returncode or not os.path.exists(answer):
            reason = ((done.stderr or "").strip().splitlines() or ["it gave no answer"])[-1]
            return {"version": "", "files": [{"error": "Docling stopped: %s" % reason[:300]} for _ in pages]}
        with open(answer, encoding="utf-8") as handle:
            return json.load(handle)

def read_corner(ctx, corner, input_key, label):
    """Read every file of one corner, in file-name order, into units numbered in reading order. A file that
    cannot be read is said so, and the others are still read. Enforces: R2"""
    inputs, chunks, info_rows, pages, not_read = ctx.options["inputs"], [], [], [], {}
    for left_out, why in (inputs.get("skipped") or {}).get(input_key, []):
        info_rows.append({"group": label, "item": "%s: left out of the folder" % left_out, "value": "Not read: %s." % why})
    for path in inputs[input_key]:
        try:
            with open(path, "rb") as handle:
                pages.append((path,) + page_of(os.path.basename(path), handle.read()))
        except Exception as problem:                 # one file that cannot be read never stops the others (R2)
            not_read[path] = str(problem)[:300] or type(problem).__name__
    read = docling_read([(name, data) for _, name, data in pages]) if pages else {"version": "", "files": []}
    results = dict(zip([path for path, _, _ in pages], read["files"]))
    for path in inputs[input_key]:
        name, found = os.path.basename(path), results.get(path) or {"error": not_read.get(path, "not read")}
        if "error" in found:
            info_rows.append({"group": label, "item": name, "value": "Not read: %s" % found["error"]})
            continue
        for chain, kind, text in found["units"]:
            chunks.append(dataclasses.asdict(Chunk("%s-%04d" % ("C" if corner == "canon" else "D", len(chunks) + 1),
                                                   corner, name, kind, tuple(chain), text, content_hash(text))))
        info_rows.append({"group": label, "item": name, "value": "Read by Docling %s: %d units" % (read["version"], len(found["units"]))})
    return StepResult({"chunks_canon" if corner == "canon" else "chunks_doc": chunks, "info_rows": info_rows},
                      {"files": len(inputs[input_key]), "units": len(chunks)}, [])

def docx_for_docling(data):
    """Word may leave out <m:dPr> in an equation's brackets (the format makes it optional); Docling's
    equation reader expects it, so an empty one - meaning ordinary parentheses - is put in."""
    source, out = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                content = re.sub(rb"<m:d>(?!\s*<m:dPr)", b"<m:d><m:dPr/>", content)
            target.writestr(item, content)
    return out.getvalue()

def html_of_mhtml(data):
    """The page inside a saved web archive."""
    for part in email.message_from_bytes(data, policy=policy.default).walk():
        if part.get_content_type() == "text/html":
            return part.get_content()
    raise ValueError("the archive holds no HTML page")

NUMBERED = re.compile(r"^(?:(?P<letter>[A-Z])\.|(?P<roman>[IVX]+)\.|(?P<dotted>\d+(?:\.\d+)+)\.?|(?P<number>\d+)\.?)\s+\S")

def html_of_text(text):
    """Plain text as a page. A block of one short line, not ending as a sentence does, is a heading when it is
    numbered (A., I., 1., 1.2) or opens the file; each numbering style takes the next level down, in the
    order the styles first appear."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if b.strip()]
    styles, out = [], []
    for number, block in enumerate(blocks):
        level = None
        if "\n" not in block and len(block.split()) <= 12 and not block.endswith((".", ":", ";", ",")):
            found = NUMBERED.match(block)
            if found:
                style = next(k for k in ("letter", "roman", "dotted", "number") if found.group(k))
                style += str(found.group("dotted").count(".")) if style == "dotted" else ""
                styles += [style] if style not in styles else []
                level = 2 + styles.index(style)
            elif number == 0:
                level = 1
        tag = "h%d" % min(level, 6) if level else "p"
        out.append("<%s>%s</%s>" % (tag, html.escape(" ".join(block.split())), tag))
    return "<html><body>%s</body></html>" % "".join(out)

def local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""

def html_of_xml(data):
    """Any XML as a page, by its structure alone: a short first child standing apart from its siblings is the
    heading of what holds it; children that are rows of cells are a table; children all alike and item-like
    are a list; an element with text of its own is a paragraph; MathML stays as written."""
    xml_names = (b"lt", b"gt", b"amp", b"quot", b"apos")
    data = re.sub(rb"&([A-Za-z][A-Za-z0-9]*);", lambda m: m.group(0) if m.group(1) in xml_names else "".join(
        "&#%d;" % ord(ch) for ch in html.unescape("&%s;" % m.group(1).decode())).encode("ascii"), data)   # &nbsp; and its kind
    try:
        root, out = ElementTree.fromstring(data), []
    except ElementTree.ParseError:                  # broken XML: its words, as plain text
        return html_of_text(re.sub(r"<[^>]+>", "\n", data.decode("utf-8", "replace")))
    words = lambda e: " ".join("".join(e.itertext()).split())
    own_text = lambda e: bool((e.text or "").strip()) or any((c.tail or "").strip() for c in e)
    def visit(e, depth):
        children = [c for c in e if isinstance(c.tag, str)]
        if local(e.tag) == "math" or not children or own_text(e):
            if words(e):
                out.append("<p>%s</p>" % html.escape(words(e)))
            return
        rows = [c for c in children if len(c) >= 2 and all(len(cell) == 0 for cell in c)]
        cells = [words(cell) for r in rows for cell in r]
        if len(rows) >= 2 and len(rows) >= len(children) - 1 and len({local(r.tag) for r in rows}) == 1 and \
                sum(len(c.split()) for c in cells) <= 8 * len(cells):     # rows of short cells, not sections of sentences
            caption = " ".join(words(c) for c in children if c not in rows)
            out.append("%s<table>%s</table>" % ("<p>%s</p>" % html.escape(caption) if caption else "",
                        "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(words(cell)) for cell in r) for r in rows)))
            return
        tags = {local(c.tag) for c in children}
        if len(children) >= 2 and len(tags) == 1 and all(len(c) == 0 for c in children) and (
                tags & {"item", "li", "point", "entry", "bullet"} or re.search("list|bullet|items|points", local(e.tag))):
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(words(c)) for c in children))
            return
        first = children[0]
        if len(children) > 1 and len(first) == 0 and local(first.tag) != local(children[1].tag) and \
                0 < len(words(first).split()) <= 12 and not words(first).endswith("."):
            number = next((v.strip() for k, v in e.attrib.items() if local(k) in ("num", "number", "no", "idx", "n", "label")
                           and re.fullmatch(r"[0-9A-Za-z]{1,4}(\.[0-9]+)*\.?", v.strip())), "")
            heading = words(first) if not number or words(first).startswith(number) else number + " " + words(first)
            out.append("<h%d>%s</h%d>" % (min(depth, 6), html.escape(heading), min(depth, 6)))
            children = children[1:]
        for c in children:
            visit(c, depth + 1)
    visit(root, 1)
    return "<html><body>%s</body></html>" % "".join(out)


def captions_out(page):
    """A table's <caption> as a paragraph just before the table: some Docling versions drop a caption."""
    return re.sub(r"(<table\b[^>]*>)\s*<caption\b[^>]*>(.*?)</caption>", r"<p>\2</p>\1", page, flags=re.I | re.S)

def page_of(name, data):
    """(name, bytes) Docling reads: a format told by its content, not its name - an .xml, .txt or any file may
    hold XML, a page or plain text."""
    low, head = name.lower(), data[:4096].lstrip().lower()
    if low.endswith(".docx"):
        return name, docx_for_docling(data)
    if low.endswith((".mhtml", ".mht")) or head.startswith(b"mime-version") or b"content-type: multipart/related" in head:
        return name + ".html", captions_out(html_of_mhtml(data)).encode("utf-8")
    if low.endswith((".pdf", ".pptx", ".xlsx", ".csv", ".md")):
        return name, data
    if head.startswith((b"<!doctype html", b"<html")) or low.endswith((".html", ".htm")):
        return name + ("" if low.endswith((".html", ".htm")) else ".html"), captions_out(decode_text(data)).encode("utf-8")
    if head.startswith(b"<"):
        return name + ".html", html_of_xml(data).encode("utf-8")
    return name + ".html", html_of_text(data.decode("utf-8", "replace")).encode("utf-8")


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
            "code": None, "data": None, "roxygen": None, "helppage": None, "read_problem": None, "node": None}
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
def braces_content(text, position):
    """The content of the {...} that starts at `position` (nested braces allowed), and the
    position after it. Used for \\eqn{}, \\deqn{} and the help-page format."""
    depth, start = 0, position
    while position < len(text):
        if text[position] == "\\":
            position += 2
            continue
        depth += {"{": 1, "}": -1}.get(text[position], 0)
        position += 1
        if depth == 0:
            return text[start + 1:position - 1], position
    return text[start + 1:], len(text)

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

def help_page_unit(path, text):
    """A help page (.Rd): name, aliases, title, usage and arguments, read from the macro format
    with nested braces; % starts a comment."""
    generated_from = re.search(r"%\s*Please edit documentation in\s+(\S+)", text)
    body = re.sub(r"(?<!\\)%[^\n]*", "", text)
    sections, position = [], 0
    for found in re.finditer(r"\\([A-Za-z]+)\s*(?=\{)", body):
        if found.start() < position:
            continue
        content, position = braces_content(body, found.end())
        sections.append((found.group(1), content))
    first = lambda macro: next((normalise_text(content) for name, content in sections if name == macro), "")
    arguments = []
    for name, content in sections:
        if name == "arguments":
            for item in re.finditer(r"\\item\s*(?=\{)", content):
                argument, after = braces_content(content, item.end())
                description, _ = braces_content(content, after) if content[after:after + 1] == "{" else ("", after)
                arguments.append((normalise_text(argument), normalise_text(description)))
    detail = {"rd_name": first("name"), "aliases": tuple(normalise_text(c) for n, c in sections if n == "alias"),
              "title": first("title"), "usage": first("usage"), "arguments": tuple(arguments),
              "generated_from_ref": None, "in_step_with_source": None,
              "generated_from_file": generated_from.group(1) if generated_from else ""}
    return draft(KIND_HELP, path, (1, text.count("\n") + 1), detail["rd_name"] or os.path.basename(path), text, helppage=detail)

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
            if reader == "help-page":
                return [help_page_unit(path, text)]
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
    if lowered.endswith(".rd") and lowered.startswith("man/"):
        return [help_page_unit(path, text)]
    if lowered.endswith((".rmd", ".rnw", ".qmd")):
        return vignette_units(path, text, context)
    return [draft(KIND_OTHER, path, (1, text.count("\n") + 1), os.path.basename(path), text[:2000])]

def link_documentation_units(units):
    """Tie each roxygen block to the object it documents and each help page to the block that
    generated it (by name and aliases), and say whether the page is still in step with it."""
    by_name = {}
    for unit in units:
        if unit["kind"] in (KIND_FUNCTION, KIND_TABLE, KIND_OBJECT) and not unit["inside"]:
            by_name.setdefault(unit["name"], unit)
    blocks = {}
    for unit in units:
        if unit["roxygen"]:                               # a block, or the object it is one row with
            target = by_name.get(unit["roxygen"]["documents_name"])
            unit["roxygen"]["documents_ref"] = target["key"] if target else None
            blocks.setdefault(unit["roxygen"]["documents_name"], unit)
    for unit in units:
        if unit["kind"] == KIND_HELP:
            page = unit["helppage"]
            block = next((blocks[name] for name in (page["rd_name"],) + tuple(page["aliases"]) if name in blocks), None)
            if block is not None:
                page["generated_from_ref"] = block["key"]
                parameters = [tag["name"] for tag in block["roxygen"]["tags"] if tag["tag"] == "param"]
                documented = [name for names in parameters for name in names.split(",")]
                page["in_step_with_source"] = sorted(documented) == sorted(name for a, _ in page["arguments"] for name in a.split(", "))

def finalise_units(drafts, file_hashes):
    """Give every draft its reference, in reading order, and turn keys into references."""
    refs = {unit["key"]: make_ref("M", number) for number, unit in enumerate(drafts, start=1)}
    units = []
    for unit in drafts:
        for part, field_name in (("roxygen", "documents_ref"), ("helppage", "generated_from_ref")):
            if unit[part] and unit[part][field_name]:
                unit[part][field_name] = refs.get(unit[part][field_name])
        helppage = dict(unit["helppage"]) if unit["helppage"] else None
        if helppage:
            helppage.pop("generated_from_file", None)
        units.append(ModelUnit(
            ref=refs[unit["key"]], kind=unit["kind"], file=unit["file"], lines=unit["lines"], name=unit["name"],
            inside=unit["inside"], text=unit["text"], parent_ref=refs.get(unit["parent_key"]),
            file_sha256=file_hashes[unit["file"]], content_hash=content_hash(unit["text"]),
            code=CodeDetail(**unit["code"]) if unit["code"] else None,
            data=ParameterDataDetail(**unit["data"]) if unit["data"] else None,
            roxygen=RoxygenDetail(**unit["roxygen"]) if unit["roxygen"] else None,
            helppage=HelpPageDetail(**helppage) if helppage else None, read_problem=unit["read_problem"]))
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
    drafts, facts = [], {"data": []}
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
    account = account_of_package(files, plain_units, refused, lambda path: is_parsed_r_file(path) or os.path.splitext(path)[1].lower() in TEXT_MEMBERS or "/" not in path)
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
    
    
    "max_file_mb": 200.0, "reviewer_id": "", 
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
    """The rows of Chunks_Canon and Chunks_Doc."""
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
            "Chunks_Canon": rows_chunks(store.read("chunks_canon")), "Chunks_Doc": doc_rows, "Chunks_Model": model_rows,
            "Model_Implementation_Map": mapped}

def check_written_totals(rows, store):
    """The identity of the workbook: every unit read is one row of its sheet, and no row is anything
    else. Raised as a fault of the tool, never as a remark about the model. Enforces: R2"""
    for kind, sheet in (("model_units", "Chunks_Model"), ("chunks_doc", "Chunks_Doc"), ("chunks_canon", "Chunks_Canon")):
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
- name: Chunks_Canon
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Section (heading chain), group: identity, field: section, width: 44}
  - {header: Type, group: identity, field: kind, width: 11}
  - {header: Text, group: methodology, field: text, width: 90, input_text: true}
  - {header: Source file, group: identity, field: source_file, width: 28}
- name: Chunks_Doc
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
        line("Re-reading the inputs gives the recorded content hashes (%s)" % kind, not differing, ", ".join(differing[:5]))
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
    for name in REQUIRED_PACKAGES:
        print("  %-11s %s" % (name, "installed" if importlib.util.find_spec(name) else "not installed - run this cell again"))
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
    models = os.path.join(home, "docling-models")      # Docling's models, staged for a cluster that cannot reach Hugging Face
    globals()["DOCLING_MODELS"] = models if os.path.isdir(models) else ""
    print("Docling models:", models if os.path.isdir(models) else "NOT STAGED in %s - a PDF is read only if they are already cached on "
          "this machine (the manual says how to stage them). Docling never fetches them: it makes no network connection." % models)
    if docling_ready() is None:                      # Docling in a folder of its own: the runtime's packages are never changed for it
        print("Installing Docling into its own folder, %s - the first time on a cluster this takes several minutes." % docling_folder())
        said = docling_install()
        if said:
            print("DOCLING IS NOT READY. What pip said:\n" + pip_said(said))
            print("Documents cannot be read until it is; the runtime's own packages were not changed.")
    if docling_ready() is not None:
        print("Docling ready, from", docling_ready() or "the runtime's own packages")
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
        print("Optional packages (words inside pictures):", "installed." if not extra.returncode else "not installed; pictures of text will say so.")
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
