"""
Verifier 0.0.2 - reading.py - reading the methodology, the model documentation and the model
package into units. For Reviewer 1 (documents) and Reviewer 2 (the package).

WHAT THIS FILE DOES
  Documents. Every file of Inputs/1_Methodology and Inputs/3_Model_Documentation becomes citable
  units - paragraphs, tables, figures and equations - each with its place in the outline (level,
  heading chain, numbering as written), a content hash, and a locator. Whatever the format, the
  path is the same: bytes -> format from the content -> repairs, each recorded -> blocks in
  reading order -> levels -> units. Word footnotes are read; page furniture is dropped and
  named; a heading nothing sits below becomes a unit so its words are not lost. Where the
  built-in rules cannot tell what a file's tags are for, and guided reading is on, one question
  about the file's SHAPE is asked first and the answer applied beneath everything the rules
  already know. It also holds the one parser for written formulas and the converters from
  Office Math, MathML and a LaTeX subset into the tool's linear notation.
  The package. The tarball (or ZIP, or source folder) becomes units: functions, formula
  statements and top-level objects from R source parsed by the tool's own tokenizer and parser
  into expression trees; stored data decoded into tables of values; help pages, vignettes and
  roxygen blocks tied to what they document. Where the built-in tests give a member no reader,
  one question chooses which existing reader takes it; there is no reader that means skip.
  Every file read keeps a content account: every piece of it ends in a named class or is
  reported, and nothing a unit shows comes from anywhere but the file or a named transform.

WHAT IT TAKES IN AND PRODUCES
  In: the input files of three corners; tag_rules.yaml and a project's override; the notation
  in r_function_map.yaml; a chat() where guided reading is on.
  Out: chunks_canon, chunks_doc, model_units, parameter_tables, package_info, read_repairs,
  outline, content_accounts, shape_digests and info_rows records.

WHICH SHEETS SHOW ITS RESULTS
  Chunks_Canon, Chunks_Doc and Chunks_Model, one row per unit; the text columns of the mapping
  sheets; and on Model_Package_Info what each file was read as, what was left out and why, the
  content account of every file, and how a file the rules were unsure of was read.

DESIGN RULES ENFORCED HERE
  R2  nothing is dropped in silence: a figure, an unreadable file, a refused format is a unit
  R4  every unit carries a content hash a citation can be checked against
  R5  reading order only; no clocks, no random choices
  R6  inputs are opened for reading only
  R7  no input text is executed; formulas and R code are parsed, never evaluated
  R9  no domain concept: tags, numbering schemes and phrases live in tag_rules.yaml
  R13 the content account of every file, and a model that chooses but never writes

HOW TO SANITY-CHECK IT
  Run tests/test_documents.py, tests/test_package.py, tests/test_guided_reading.py and
  tests/test_hard_reading_samples.py. Run cell 3 on a sample project and open Output.xlsx: on
  Chunks_Canon every table sits in one cell, every figure and equation has its own row, and Level
  and Section follow the document's own outline; on Model_Package_Info every file's content
  account is closed.
"""

from dataclasses import dataclass, field
from decimal import Decimal
import bz2
import csv
import email
import html.entities
import html.parser
import io
import lzma
import os
import re
import tarfile
import xml.etree.ElementTree as ElementTree
import zipfile
import zlib

import yaml

import core

# ================================================================================================
# ---------------------------------------------------------------- from verifier1_documents
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
# schemes, the phrases that make a statement checkable. An analyst's Inputs/tag_rules.yaml is laid
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
# A documentation passage "states something checkable" when it holds a number, a formula,
# or one of these phrases. Narrative passages get the clean status "Narrative - nothing to check".
checkable_phrases: [is calculated, is computed, is set to, equals, is defined as, is floored, is capped,
                    at least, at most, not exceed, no less than, no more than, minimum, maximum,
                    must, shall, is applied, are applied, is multiplied, is divided, rounded, per cent, percent]
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
# plumbing: calls that mark a statement as supporting code by syntax (no formula in it).
plumbing_calls: [stop, warning, message, stopifnot, print, cat, library, require, requireNamespace,
                 missing, is.null, is.numeric, is.character, is.na, match.arg, invisible, on.exit,
                 tryCatch, suppressWarnings, inherits, class, structure, names, length, nrow, ncol,
                 seq_len, seq_along, vapply, lapply, sapply, data, utils::data, format, paste, paste0, sprintf]
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
            tokens.append(("number", core.plain_decimal(value / 100 if match.group("percent") else value)))
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
            left = core.Expr("eq", args=(left, self.comparison()))
            if self.peek() == ("sign", "="):
                raise NotReadable("it has more than one equals sign")
        return left

    def comparison(self):
        """An expression, optionally compared with another one."""
        left = self.sum()
        if self.peek()[0] == "sign" and self.peek()[1] in ("<", ">", "<=", ">="):
            sign = self.take()[1]
            left = core.Expr("cmp", name=sign, args=(left, self.sum()))
        return left

    def sum(self):
        """Terms joined by + and -, from left to right."""
        left = self.product()
        while self.peek() in (("sign", "+"), ("sign", "-")):
            op = "add" if self.take()[1] == "+" else "sub"
            left = core.Expr(op, args=(left, self.product()))
        return left

    def product(self):
        """Factors joined by * and /, from left to right; juxtaposition only where the source allows it."""
        left = self.unary()
        while True:
            if self.peek() in (("sign", "*"), ("sign", "/")):
                op = "mul" if self.take()[1] == "*" else "div"
                left = core.Expr(op, args=(left, self.unary()))
            elif self.implicit_product and self.term_follows():
                left = core.Expr("mul", args=(left, self.power()))
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
            return core.Expr("neg", args=(self.unary(),))
        if self.peek() == ("sign", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        """A base with an optional power (right-associative), an inverse-function mark or a percent sign."""
        base = self.atom()
        if self.peek() == ("sign", "^"):
            self.take()
            base = core.Expr("pow", args=(base, self.unary()))
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
            return core.Expr("num", value=text)
        if kind == "sign" and text == "(":
            inner = self.statement()
            self.take(")")
            return inner
        if kind == "sign" and text == "\u221a":
            return core.Expr("call", name="sqrt", args=(self.atom(),))
        if kind != "name":
            raise NotReadable("'%s' stands where a number or a symbol was expected" % (text or "the end"))
        function = self.functions.get(text) or self.functions.get(core.normalise_symbol(text))
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
            return core.Expr("call", name=function, args=tuple(arguments))
        return core.Expr("sym", name=core.normalise_symbol(text))

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
    linear = core.normalise_text(linear)
    if not linear:
        reason = core.UNDECIDED_REASONS[0] if image_sha256 or source_form == "image" else "no formula text was found"
        return core.EquationData(source_form, "", False, reason, None, image_sha256)
    try:
        tree = parse_formula(linear, notation, implicit_product=source_form in ("omml", "mathml", "latex"))
    except NotReadable as problem:
        return core.EquationData(source_form, linear, False, str(problem), None, image_sha256)
    return core.EquationData(source_form, core.expr_to_text(tree), True, "", core.to_plain(tree), image_sha256)

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
        return core.EquationData("inline", core.expr_to_text(tree), True, "", core.to_plain(tree), "")
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
    name = core.local_name(element.tag)
    def part(child_name):
        child = core.child_named(element, child_name)
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
        return "(%s)" % ", ".join(math_children(child) for child in element if core.local_name(child.tag) == "e")
    if name == "func":
        return "%s(%s)" % (part("fname").strip(), strip_outer_brackets(part("e")))
    if name == "nary":
        properties = core.child_named(element, "narypr")
        sign = core.child_named(properties, "chr") if properties is not None else None
        kind = NARY_NAMES.get(core.attribute(sign, "val"), "sum_over") if sign is not None else "integral_over"
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
            elif word in core.GREEK:
                output.append(core.GREEK[word])
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
        if rules["family_of"].get(core.local_name(child.tag)) not in skip:
            if rules["family_of"].get(core.local_name(child.tag)) in BLOCKS_INSIDE and "".join(pieces).strip():
                pieces.append(" ")
            pieces.append(element_text(child, rules, skip))
        pieces.append(child.tail or "")
    return "".join(pieces)

def new_block(kind, text="", locator="", **more):
    """One block of a document before numbering: kind, text, where it was found, and what its kind needs."""
    block = {"type": kind, "text": core.normalise_text(text), "locator": locator, "level_hint": None,
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
    ask: object = None                             # the asker, where a guided reading is turned on
    settings: dict = field(default_factory=dict)
    digests: list = field(default_factory=list)    # the shapes shown to the model, recorded
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
    name = core.local_name(element.tag)
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
        caption = next((core.normalise_text(element_text(n, state.rules, skip=())) for n in element.iter()
                        if state.rules["family_of"].get(core.local_name(n.tag)) == "caption"), "") or element.get("alt") or element.get("title") or ""
        with open(linked, "rb") as handle:
            state.blocks.extend(svg_blocks(handle.read(), os.path.basename(linked), here, state, caption))
        state.consumed.add(linked)
        state.notes.append("%s: read in place, where %s refers to it." % (os.path.basename(linked), state.file_name or "the document"))
        return
    if family is None:                                   # discovery names every tag it reaches; this is the net under it
        family = "container" if len(element) else "paragraph"
    numbering = core.written_numbering(element, state.rules)
    if family == "heading":
        text = element_text(element, state.rules)
        digit = re.fullmatch(r"h([1-6])", name)
        state.blocks.append(new_block("heading", text, here, numbering=numbering or state.lent_numbering,
                                      level_hint=int(digit.group(1)) if digit else depth))
        state.lent_numbering = ""
    elif family in ("container", "list_container", "inline"):
        # A container that carries its own heading in an attribute (<section name="4. Market">)
        # gives that heading a block of its own, so the chain below it is not lost.
        heading, _ = core.attribute_text(element, state.rules["heading_attributes"]) if family == "container" else ("", "")
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
        state.blocks[-1]["caption"] = core.normalise_text(element_text(element, state.rules, skip=()))

def walk_mixed(element, here, depth, state, own_kind=None, numbering="", marker=""):
    """An element that may hold both running text and blocks. Its own text becomes one
    paragraph; a formula that fills the paragraph alone becomes an Equation block instead."""
    block_families = ("heading", "container", "list_container", "paragraph", "list_item", "table",
                      "figure", "equation", "caption", None)
    children = [c for c in element if core.local_name(c.tag) and
                (state.family(core.local_name(c.tag)) in block_families or core.local_name(c.tag) == "verifier-preserved-equation")]
    inline_only = [c for c in children if state.family(core.local_name(c.tag)) is None and not len(c)
                   and own_kind]
    children = [c for c in children if c not in inline_only]
    text = core.normalise_text(element_text(element, state.rules, skip=("figure", "equation", "ignore", "caption",
                                 "table", "list_container")) if own_kind or not children else (element.text or ""))
    equations = [c for c in children if state.family(core.local_name(c.tag)) == "equation"]
    if own_kind and text and equations:                  # text around a formula: show the formula in place
        text = core.normalise_text(text + " " + " ".join(math_to_linear(c) for c in equations))
        children = [c for c in children if c not in equations]
    if text and (own_kind or not children):
        state.blocks.append(new_block(own_kind or "paragraph", text, here, numbering=numbering, marker=marker))
    for position, child in enumerate(children, start=1):
        if own_kind and state.family(core.local_name(child.tag)) in ("paragraph", "inline"):
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
    family = lambda node: state.family(core.local_name(node.tag))
    found = [node for node in element.iter() if family(node) == "row"] or core.table_rows(element, state.rules)
    rows, captions = [], []
    in_a_row = {id(node) for row in found for node in row.iter()}
    for node in element.iter():
        # A caption may be named as one, or may simply sit beside the rows rather than in them
        # (<gridcaption> under <gridholder>). Either way its words belong to the table and are
        # kept: a table whose title is lost cannot be cited by its number. Enforces: R13
        beside = (node is not element and id(node) not in in_a_row and family(node) not in ("row", "table_part", "ignore")
                  and not any(child is not None and family(child) == "row" for child in node))
        part = core.normalise_text(element_text(node, state.rules, skip=())) if family(node) == "caption" or beside else ""
        if part and part not in captions:
            captions.append(part)
    for row in found:
        cells = [core.normalise_text(element_text(cell, state.rules, skip=())) for cell in row
                 if core.local_name(cell.tag) and family(cell) not in ("caption", "ignore")]
        if any(cells):
            rows.append(cells)
    block = table_from_rows(rows, here, ". ".join(captions))
    words = "" if rows else core.normalise_text(element_text(element, state.rules, skip=("ignore", "caption")))
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
    types = []
    for column in range(width):
        values = [row[column] for row in body if row[column]]
        numeric = values and all(core.find_numbers(v) and len(core.find_numbers(v)) == 1 and
                                 len(re.sub(r"[\d.,%\s+-]|bps?|basis points?", "", v)) == 0 for v in values)
        types.append("number" if numeric else "text")
    row_key = header[0] if header and types and types[0] == "text" else ""
    table = core.TableData(tuple(header), tuple(tuple(row) for row in body), row_key, tuple(types))
    return new_block("table", "", locator, table=table, caption=caption, display=display)

PICTURE_READER = []                     # the OCR engine, looked for once: [engine] or [None]
OCR_NOTE = "Words read from the picture by OCR (a machine reading: check it against the picture itself):"

def read_picture(data, state):
    """The words in a picture, read by OCR, as lines to show under the Figure; "" when there are
    none or no OCR package is installed (rapidocr-onnxruntime is optional; its models come inside
    the package, so nothing is fetched when it runs). The words help a person and the search to
    find the picture. They are never evidence: a machine misreads digits, so a Figure still ends
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
    caption = next((core.normalise_text(element_text(n, state.rules, skip=())) for n in element.iter()
                    if state.rules["family_of"].get(core.local_name(n.tag)) == "caption"), "")
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
    values = [value for key, value in element.attrib.items() if LINK_ATTRIBUTE.search(core.local_name(key))]
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
    markup, words, _ = core.svg_to_markup(data, name)
    own_caption, labels = (words.split("\n", 1) + [""])[:2]
    state.atoms.extend(core.atoms_of_plain_text(labels if caption else words, name))
    blocks = walk_svg_markup(parse_markup(markup, name, [], False), here, state)
    for block in blocks:
        block["caption"] = caption or own_caption
        block["source"], block["image_sha256"] = name, core.sha256_bytes(data)
        if block["type"] == "figure" and not block["text"].strip():
            seen = "".join(read_picture(picture, state) for picture in core.svg_embedded_pictures(root)).strip()
            if seen:
                block["text"] = seen                     # words read from a picture: shown, never evidence
            else:
                block["not_read_reason"] = "the picture gave no words: %s" % core.svg_why_no_text(root)
    return blocks

def walk_svg_markup(root, here, state):
    """The blocks the SVG's markup gives: a table block, or one figure block carrying the
    picture's labels as its text."""
    blocks = []
    for node in root:
        family = state.rules["family_of"].get(core.local_name(node.tag))
        if family == "table":
            block = table_block(node, here, state)
            if block is not None:
                blocks.append(block)
        elif family == "figure":
            blocks.append(new_block("figure", node.get("alt") or "", here,
                                    caption=next((core.normalise_text("".join(c.itertext())) for c in node if core.local_name(c.tag) == "caption"), "")))
    return blocks


def equation_block(element, here, state):
    """An equation element: MathML or Office Math is converted; LaTeX or linear text is read as
    written; an equation that is only a picture stays an Equation chunk that could not be read."""
    markup = next((n for n in element.iter() if core.local_name(n.tag) in ("math", "omath")), None)
    picture = next((n for n in element.iter() if core.local_name(n.tag) in ("img", "image", "graphic", "imagedata")), None)
    if markup is not None:
        form = "mathml" if core.local_name(markup.tag) == "math" else "omml"
        equation = read_equation(form, math_to_linear(markup), state.notation)
    elif picture is not None and not core.normalise_text(element_text(element, state.rules)):
        source = picture.get("src") or picture.get("fileref") or ""
        equation = read_equation("image", "", state.notation, state.images.get(source, "") or core.sha256_text(source))
    else:
        written = core.normalise_text(element_text(element, state.rules, skip=("caption", "ignore")))
        try:
            linear = latex_to_linear(written) if "\\" in written else written
            equation = read_equation("latex" if "\\" in written else "inline", linear, state.notation)
        except NotReadable as problem:
            equation = core.EquationData("latex", written, False, str(problem), None, "")
    label = picture.get("alt") if picture is not None and picture.get("alt") else ""
    text = equation.linear or label or "Equation shown as a picture"
    return new_block("equation", text, here, equation=equation)

def blocks_from_markup(text, file_name, state, repairs, tolerant_only=False):
    """XML or HTML text to blocks: parse (repairing where needed), then walk the tree by the tag rules."""
    root = parse_markup(text, file_name, repairs, tolerant_only)
    discovered = core.discover_families(root, state.rules, state.unknown_tags)
    state.rules["family_of"].update(discovered)
    core.guided_rules(root, file_name, state, discovered)
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
            fingerprint = core.sha256_bytes(payload)
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
    text = core.normalise_text(re.sub(r"<[^>]+>", " ", found.group(1))) if found else ""
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
        name = core.local_name(node.tag)
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
                        if core.local_name(n.tag) == "docpr"), "")
    fingerprint, words = "", ""
    for node in picture.iter():
        for key, value in node.attrib.items():
            if key.startswith("{%s}" % WORD_NS["r"]) and value in related:
                fingerprint, words = core.sha256_bytes(related[value]), read_picture(related[value], state)
    fingerprint = fingerprint or core.sha256_bytes(ElementTree.tostring(picture))
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
                text = core.normalise_text("".join(run.text or "" for run in paragraph.iter("{%s}t" % WORD_NS["w"])))
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
        locator, name = "body element %d" % position, core.local_name(element.tag)
        if name == "tbl":
            rows = []
            for row in element.findall("w:tr", WORD_NS):
                rows.append([core.normalise_text(docx_paragraph_parts(cell)[0]) for cell in row.findall("w:tc", WORD_NS)])
            blocks.append(table_from_rows(rows, locator, pending_caption))
            pending_caption = ""
            continue
        if name != "p":
            continue
        level, numbered, style_name = docx_paragraph_facts(element, styles)
        text, formulas, pictures = docx_paragraph_parts(element)
        text = core.normalise_text(text)
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
            if numbered and not core.first_numbering(text, state.rules)[0]:
                counters[level - 1] += 1
                counters[level:] = [0] * (9 - level)
                block["numbering"] = ".".join(str(c) for c in counters[:level] if c)
                block["reconstructed"] = True
            blocks.append(block)
        elif formulas and not core.normalise_text(re.sub(r"\s+", " ", text.replace(math_to_linear(formulas[0]), ""))):
            equation = read_equation("omml", math_to_linear(formulas[0]), state.notation)
            blocks.append(new_block("equation", equation.linear or text, locator, equation=equation))
        elif text:
            page += sum(1 for node in element.iter() if core.local_name(node.tag) == "lastrenderedpagebreak")
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
MATH_CHARACTERS = set("=+\u2212\u00d7\u00f7\u2211\u221a\u222b^/\u2264\u2265\u2248()") | set(core.GREEK.values())

BULLET = re.compile(r"^(?:[\u2022\u25aa\u25cf\u25e6\u2023\u2043\u2013\u2014*o-]|\(cid:\d+\))\s+(?=\S)")

def pdf_lines(document, file_name):
    """Every line, table and picture of a PDF in reading order, each with its page, its place on
    the page, and whether it sits in the top or bottom margin ("edge")."""
    lines = []
    for number, page in enumerate(document.pages, start=1):
        edge = lambda top, bottom: "top" if bottom < 0.12 * page.height else "bottom" if top > 0.88 * page.height else ""
        tables = page.find_tables()
        for table in tables:
            rows = [[core.normalise_text(cell or "") for cell in row] for row in table.extract()]
            lines.append({"page": number, "top": table.bbox[1], "table": rows, "edge": ""})
        for count, image in enumerate(page.images, start=1):
            mark = "%s page %d picture %d %s" % (file_name, number, count, image.get("srcsize"))
            lines.append({"page": number, "top": image["top"], "figure": core.sha256_text(mark), "text": "picture %s" % (image.get("srcsize"),),
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
        lines = core.without_page_furniture(pdf_lines(document, file_name), len(document.pages), state, file_name)
        sizes = sorted(entry["size"] for entry in lines if "size" in entry)
        body_size = sizes[len(sizes) // 2] if sizes else 10.0
        numbered = any("size" in entry and core.first_numbering(entry["text"], state.rules)[0] for entry in lines)
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
                core.first_numbering(text, state.rules)[0] or (len(text.split()) <= 14 and text[-1] not in ".,;:"))
            near = open_block and entry["page"] == open_block["page"] and entry["top"] - open_block["bottom"] < 0.7 * entry["size"]
            over_the_page = open_block and entry["page"] == open_block["page"] + 1 and not title and not bullet \
                and open_block["block"]["type"] != "heading" and open_block["block"]["text"][-1:] not in ".:;?!" and text[:1].islower()
            if title and near and open_block["block"]["type"] == "heading":       # a heading set over two lines
                kind = None
            elif title:
                kind, more = "heading", {"level_hint": None if numbered else -int(round(entry["size"] * 2)) + (0 if entry["size"] > body_size * 1.08 else 1)}
            elif dense > 0.25 and len(text.split()) <= 12:
                kind, more = "equation", {"equation": core.EquationData("pdf", text, False, core.UNDECIDED_REASONS[1], None, "")}
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
            text = core.normalise_text(paragraph)
            if text:
                kind = "heading" if core.first_numbering(text, state.rules)[0] and len(text) < 100 else "paragraph"
                blocks.append(new_block(kind, text, "page %d" % page_number))
    return blocks

# ---------------------------------------------------------------- levels, references, chunks

def cross_references(text, rules):
    """Cross-references as written: "Table 3", "section 4.2", "Annex A"."""
    labels = "|".join(re.escape(label) for label in rules["cross_reference_labels"])
    found = re.findall(r"\b((?:%s)\s+(?:[A-Z]\b|\d+(?:\.\d+)*[a-z]?|\([a-z0-9]+\)))" % labels, text or "", re.IGNORECASE)
    return tuple(dict.fromkeys(core.normalise_text(reference) for reference in found))

def states_something_checkable(block, rules):
    """Does a documentation passage state something that can be checked against the methodology
    or the code: a number, a formula, a table, or a phrase from the rules file?"""
    if block["type"] in ("table", "equation"):
        return True
    if block["type"] == "figure" or block["not_read_reason"]:
        return None
    lowered = block["text"].lower()
    return bool(core.find_numbers(block["text"]) or "=" in lowered or
                any(phrase in lowered for phrase in rules["checkable_phrases"]))

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
    chunks, chain, levels, paragraph_number, section_numbering = [], [], [], 0, ""
    carried, empty = [], []                          # (heading block, anything under it yet), and those with nothing
    for block in fold_lists(core.infer_levels(blocks, state.rules)):
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
            paragraph_number, section_numbering = 0, block["numbering"]
            # The number belongs to the heading whether the document wrote it (num="1.") or Word
            # left it to be counted back. Without it a citation to "section 2" can be resolved
            # against nothing, and the number itself reaches no unit at all. Enforces: R13
            if block["numbering"] and not block["text"].startswith(block["numbering"]):
                chain[-1] = "%s %s" % (block["numbering"], block["text"])
            continue
        carried = [(was, True) for was, _ in carried]
        kind = KIND_OF_BLOCK[block["type"]]
        text = block.get("display") or block["text"]
        if kind == "Paragraph" and not block["not_read_reason"]:
            paragraph_number += 1
        equation = block["equation"]
        if kind == "Paragraph" and equation is None:
            equation = inline_formula(text, state.notation)
        chunks.append(core.Chunk(
            ref=core.make_ref(prefix, first_number + len(chunks)), corner=corner, source_file=source_file,
            kind=kind, level=levels[-1] if levels else 0, heading_chain=tuple(chain), numbering=section_numbering,
            para_no=paragraph_number if kind == "Paragraph" and not block["not_read_reason"] else None,
            text=text, locator=block["locator"], content_hash=core.content_hash(text + block.get("image_sha256", "")),
            table=block["table"], equation=equation, refs_out=cross_references(text + " " + block["caption"], state.rules),
            checkable=states_something_checkable(block, state.rules) if corner == "doc" else None,
            numbering_reconstructed=bool(chain) and block_is_under_reconstructed(blocks, block),
            caption=block["caption"], not_read_reason=block["not_read_reason"],
            para_label=block["numbering"] if kind == "Paragraph" else ""))
    while carried:                                   # whatever is still on the chain when the file ends
        was, under = carried.pop()
        if not under:
            empty.append(was)
    for block in empty:
        chunks.append(core.Chunk(
            ref=core.make_ref(prefix, first_number + len(chunks)), corner=corner, source_file=source_file,
            kind="Paragraph", level=block["level"], heading_chain=(), numbering=block["numbering"],
            para_no=None, text=block["text"], locator=block["locator"],
            content_hash=core.content_hash(block["text"]), table=None, equation=None,
            refs_out=cross_references(block["text"], state.rules),
            checkable=states_something_checkable(block, state.rules) if corner == "doc" else None,
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

def outline_lines(chunks):
    """The indented outline an analyst compares with the document's own table of contents:
    one line per section, with its range of references and the number of units in it."""
    sections = {}
    for chunk in chunks:
        for depth in range(0 if not chunk.heading_chain else 1, len(chunk.heading_chain) + 1):
            key = (chunk.source_file, chunk.heading_chain[:depth])     # the section and every section above it
            entry = sections.setdefault(key, {"depth": depth, "first": chunk.ref, "count": 0})
            entry["last"], entry["count"] = chunk.ref, entry["count"] + 1
    lines = []
    for (source_file, chain), entry in sections.items():
        title = chain[-1] if chain else "(text before the first heading of %s)" % source_file
        lines.append("%s%s   [%s to %s, %d units]" % ("    " * max(0, entry["depth"] - 1), title,
                                                      entry["first"], entry["last"], entry["count"]))
    return lines

# ---------------------------------------------------------------- the two steps
def atoms_of_file(data, found, file_name, state, repairs):
    """The smallest pieces of text the file holds, counted straight from the file and NOT from
    the blocks the reader made of it. That independence is the whole point: an account drawn
    from the reader's own output could never show what the reader missed. Enforces: R13"""
    try:
        if found == "docx":
            return core.atoms_of_docx(zipfile.ZipFile(io.BytesIO(data)), safe_xml, file_name)
        if found == "pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as document:
                return core.atoms_of_pdf(document, file_name)
        if found == "mhtml":
            message = email.message_from_bytes(data)
            for part in message.walk():
                payload = part.get_payload(decode=True)
                if part.get_content_type() == "text/html" and payload is not None:
                    text = payload.decode(part.get_content_charset() or "utf-8", "replace")
                    return core.atoms_of_markup(parse_markup(repair_markup(text, file_name, []), file_name, [], tolerant_only=True), file_name, state.rules)
            return []
        if found in ("xml", "html"):
            text = repair_markup(core.decode_text(data), file_name, [])
            return core.atoms_of_markup(parse_markup(text, file_name, [], tolerant_only=found == "html"), file_name, state.rules)
        return core.atoms_of_plain_text(core.decode_text(data), file_name)
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
    found = core.detect_format(data, file_name)
    if found in core.NOT_READ:                    # said in plain words, with a next step; never decoded as text
        state.atoms = [core.atom("whole file not read", file_name, "")]
        return found, [not_read_block(file_name, "the file is " + core.NOT_READ[found])]
    if found == "svg":                               # read by the text it holds, as a table or a figure
        state.atoms = []
        return found, svg_blocks(data, file_name, file_name, state)
    if found in core.CONVERTED:                   # read through markup the walker already reads
        markup, words, how = core.converted(found, data, file_name)
        state.atoms = core.atoms_of_plain_text(words, file_name)
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
        return found, blocks_from_markup(core.decode_text(data), file_name, state, repairs, tolerant_only=found == "html")
    blocks = [new_block("paragraph", part, "paragraph %d" % number)
              for number, part in enumerate(re.split(r"\n\s*\n", core.decode_text(data)), start=1) if part.strip()]
    return "plain text", blocks

def read_corner(ctx, corner, input_key, label):
    """Read every file of one corner, in file-name order, into chunks numbered in reading order."""
    options = ctx.options
    rules = load_tag_rules(options["inputs"].get("tag_rules"))
    notation = load_notation()
    chunks, repairs, info_rows, outline, accounts, digests, read_as_what = [], [], [], [], [], [], []
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
        state.ask, state.settings = ctx.ask, ctx.settings
        state.svgs, state.consumed, state.file_name = svgs, consumed, file_name
        try:
            found, blocks = read_file_blocks(path, file_name, state, repairs, int(ctx.settings["max_file_mb"] * 1024 * 1024))
        except Exception as problem:                 # a file that breaks a reader is named, never a stopped run (R2)
            found, blocks = "unreadable", [not_read_block(file_name, core.reason_for(problem))]
            state.atoms, state.blocks = [core.atom("whole file not read", file_name, "")], []
        read_as_what.append((file_name, found, blocks[0].get("not_read_reason", "") if len(blocks) == 1 else ""))
        new_chunks = blocks_to_chunks(blocks, corner, file_name, len(chunks) + 1, state)
        chunks.extend(new_chunks)
        plain = [core.to_plain(chunk) for chunk in new_chunks]
        for tag in sorted(state.guided):
            info_rows.append({"group": label, "item": "%s: how it was read" % file_name,
                              "value": "<%s> was read as %s on the model's proposal." % (tag, state.guided[tag])})
        digests.extend(state.digests)
        found_account = core.account(file_name, state.atoms, plain, state.dropped,
                                        core.marks_of_rendering(plain)
                                        + [LIST_MARKER] * (len(plain) + 1) + [NOTES_HEADING],
                                        os.path.getsize(path) if os.path.isfile(path) else 0)
        accounts.append(found_account)
        info_rows.extend({"group": label, "item": "%s: content account" % file_name, "value": line}
                         for line in core.account_lines(found_account))
        counts = {}
        for chunk in new_chunks:
            counts[chunk.kind] = counts.get(chunk.kind, 0) + 1
        summary = ", ".join("%d %s" % (counts[kind], kind.lower() + ("s" if counts[kind] != 1 else ""))
                            for kind in core.CHUNK_KINDS if kind in counts) or "nothing could be read"
        info_rows.append({"group": label, "item": file_name, "value": "Read as %s: %d units (%s)"
                          % (core.FORMAT_NAMES.get(found, found), len(new_chunks), summary)})
        info_rows.extend({"group": label, "item": "%s: reading note" % file_name, "value": note} for note in state.notes)
        for tag in sorted(state.unknown_tags):
            seen = state.unknown_tags[tag]
            because = ", because it %s" % seen["reason"] if seen.get("reason") else ""
            info_rows.append({"group": label, "item": "%s: unrecognised tag" % file_name, "value":
                              "Unrecognised tag '%s', %d times, read as %s%s. "
                              "It can be added to Inputs/tag_rules.yaml."
                              % (tag, seen["count"], seen.get("family") or seen.get("read_as"), because)})
    outline.append({"corner": corner, "lines": outline_lines(chunks)})
    kind = "chunks_canon" if corner == "canon" else "chunks_doc"
    unreadable = sum(1 for chunk in chunks if chunk.kind == "Equation" and not chunk.equation.readable)
    messages = ["%d units read from %d file(s)." % (len(chunks), len(options["inputs"][input_key]))]
    read_as = {}
    for _, found, _ in read_as_what:
        if found in core.FORMAT_NAMES:
            read_as[core.FORMAT_NAMES[found]] = read_as.get(core.FORMAT_NAMES[found], 0) + 1
    if read_as:                                      # what each file was read as, and what was not read and why
        messages.append("Read as: %s." % ", ".join("%d %s" % (count, name) for name, count in sorted(read_as.items())))
    messages.extend("Not read: %s - %s." % (name, why) for name, found, why in read_as_what
                    if why and (found in core.NOT_READ or found == "unreadable"))
    skipped = (options["inputs"].get("skipped") or {}).get(input_key, [])
    if skipped:
        messages.append("%d file(s) in the folder were left out; Model_Package_Info lists them." % len(skipped))
    if unreadable:
        messages.append("%d equation(s) could not be read and will be raised for a person." % unreadable)
    open_accounts = [one for one in accounts if not one["closed"]]
    if open_accounts:
        messages.append("The content account is open on %d file(s); Model_Package_Info says what could not be placed."
                        % len(open_accounts))
    return core.StepResult({kind: chunks, "read_repairs": repairs, "info_rows": info_rows, "outline": outline,
                              "content_accounts": accounts, "shape_digests": digests},
                             {"units": len(chunks), "repairs": len(repairs),
                              "content account open on": len(open_accounts)}, messages)

def read_methodology(ctx):
    """Step 02, read-methodology: the canonical methodology into chunks C-0001, C-0002, ..."""
    return read_corner(ctx, "canon", "methodology", "Methodology files")

def read_documentation(ctx):
    """Step 03, read-documentation: the model documentation into chunks D-0001, D-0002, ..."""
    return read_corner(ctx, "doc", "documentation", "Documentation files")


# ================================================================================================
# ---------------------------------------------------------------- from verifier2_package
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

def read_namespace(text):
    """Exported names and export patterns from NAMESPACE."""
    text = re.sub(r"#[^\n]*", "", text)
    exports, patterns = set(), []
    for directive, inner in re.findall(r"(export|exportPattern|S3method)\s*\(([^)]*)\)", text):
        names = [part.strip().strip("\"'`") for part in inner.split(",") if part.strip()]
        if directive == "export":
            exports.update(names)
        elif directive == "exportPattern":
            patterns.extend(names)
    return {"exports": exports, "patterns": patterns}

def is_exported(name, namespace):
    """Is `name` exported by this NAMESPACE (by name, by pattern or as an S3 method)? None when there is no NAMESPACE."""
    if namespace is None:
        return None
    return name in namespace["exports"] or any(re.search(pattern, name) for pattern in namespace["patterns"])

# ---------------------------------------------------------------- the R tokenizer
@dataclass
class Token:
    """One token of R source: kind is num, str, name, op, newline or end. `column` is 0 for a
    token that starts its line, which is where a new top-level statement usually begins."""
    kind: str; text: str; line: int; column: int = -1

_R_TOKEN = re.compile(r"""
  (?P<space>[ \t\r\f]+)
 |(?P<newline>\n)
 |(?P<comment>\#[^\n]*)
 |(?P<raw>[rR]["'](?P<dashes>-*)[\(\[\{])
 |(?P<num>0[xX][0-9a-fA-F]+[Li]?|(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?[Li]?)
 |(?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
 |(?P<backtick>`[^`]*`)
 |(?P<name>(?:[^\W\d_]|\.(?![0-9]))[\w.]*)
 |(?P<op><<-|->>|\|>|:::|%[^%\n]*%|<-|->|<=|>=|==|!=|&&|\|\||::|\*\*|\[\[|[-+*/^<>=!&|~?:$@(){}\[\],;\\])
""", re.X)
_RAW_CLOSERS = {"(": ")", "[": "]", "{": "}"}

def tokenize_r(source):
    """R source to tokens. Comments are dropped here (roxygen lines are collected by
    roxygen_blocks). Line breaks are kept as tokens because in R a line break ends an
    expression unless a bracket is open or an operator is waiting for its right side."""
    tokens, position, line, line_start = [], 0, 1, 0
    while position < len(source):
        match = _R_TOKEN.match(source, position)
        column = position - line_start
        if not match:
            raise NotParsed("line %d holds the character '%s', which the tool's R reader does not know"
                            % (line, source[position]))
        kind, text = match.lastgroup, match.group(0)
        if kind == "dashes":
            kind = "raw"
        if kind == "raw":
            closer = _RAW_CLOSERS[text[-1]] + match.group("dashes") + text[1]
            end = source.find(closer, match.end())
            if end < 0:
                raise NotParsed("a raw string that starts on line %d is never closed" % line)
            tokens.append(Token("str", source[match.end():end], line, column))
            text = source[position:end + len(closer)]
        elif kind == "str":
            tokens.append(Token("str", text[1:-1], line, column))
        elif kind == "backtick":
            tokens.append(Token("name", text[1:-1], line, column))
        elif kind in ("num", "name", "op", "newline"):
            tokens.append(Token(kind, text, line, column))
        line += text.count("\n")
        position += len(text)
        if "\n" in text:
            line_start = position - (len(text) - text.rfind("\n") - 1)
    tokens.append(Token("end", "", line))
    return tokens

# ---------------------------------------------------------------- the R parser
@dataclass
class Node:
    """One node of the syntax tree. kind is one of: num, str, name, call, index, binary,
    unary, dollar, ns, function, block, if, for, while, repeat, paren, missing.
    For a call, args[0] is what is called and `names` holds the argument names ("" when the
    argument is positional). For a function, `names` are the formals, args[:-1] their
    defaults (kind "missing" when there is none) and args[-1] the body."""
    kind: str; value: str = ""; args: tuple = (); names: tuple = (); line: int = 0; end_line: int = 0

BINARY_POWER = {"?": 1, "=": 2, "<-": 3, "<<-": 3, "->": 4, "->>": 4, "~": 5, "|": 6, "||": 6, "&": 7, "&&": 7,
                "==": 9, "!=": 9, "<": 9, ">": 9, "<=": 9, ">=": 9, "+": 10, "-": 10, "*": 11, "/": 11,
                "|>": 12, ":": 13, "^": 15, "**": 15}
RIGHT_TO_LEFT = ("=", "<-", "<<-", "^", "**")
UNARY_POWER = {"-": 14, "+": 14, "!": 8, "~": 5, "?": 1}
ASSIGNMENT_SIGNS = ("<-", "<<-", "=", "->", "->>")
KEYWORDS = ("if", "else", "for", "while", "repeat", "function", "break", "next")

class RParser:
    """Precedence climbing over R's documented operator table (?Syntax). `open_brackets`
    remembers which bracket is open: inside ( and [ a line break means nothing; at the top
    level and inside { it ends the expression."""
    def __init__(self, tokens):
        self.tokens, self.position, self.open_brackets, self.last_line = tokens, 0, [], 1

    def peek(self):
        """The token at the reading position, without taking it."""
        while self.tokens[self.position].kind == "newline" and self.open_brackets and self.open_brackets[-1] != "{":
            self.position += 1
        return self.tokens[self.position]

    def take(self, text=None):
        """Take the next token; with `text`, insist that it is that token."""
        token = self.peek()
        if text is not None and not (token.kind == "op" and token.text == text):
            raise NotParsed("line %d: '%s' was expected where '%s' stands" % (token.line, text, token.text or "the end of the file"))
        self.position += 1
        self.last_line = token.line
        return token

    def skip_newlines(self):
        """Skip line ends where R allows an expression to go on."""
        while self.tokens[self.position].kind == "newline":
            self.position += 1

    def is_op(self, *texts):
        """Is the next token one of these operators?"""
        token = self.peek()
        return token.kind == "op" and token.text in texts

    def expression(self, minimum=0):
        """Operator-precedence parsing of one expression; `minimum` is the weakest binding still accepted."""
        left = self.prefix()
        while True:
            token = self.peek()
            if token.kind != "op":
                return left
            if token.text in ("(", "[", "[["):
                left = self.call_or_index(left)
            elif token.text in ("$", "@", "::", ":::"):
                self.take()
                self.skip_newlines()
                right = self.take()
                kind = "dollar" if token.text in ("$", "@") else "ns"
                right_node = Node("paren", args=(self.finish_paren(),)) if right.text == "(" else Node(right.kind, right.text, line=right.line)
                left = Node(kind, token.text, (left, right_node), line=left.line, end_line=self.last_line)
            else:
                power = 12 if token.text.startswith("%") else BINARY_POWER.get(token.text)
                if power is None or power < minimum:
                    return left
                self.take()
                self.skip_newlines()
                right = self.expression(power if token.text in RIGHT_TO_LEFT else power + 1)
                left = Node("binary", "^" if token.text == "**" else token.text, (left, right), line=left.line, end_line=self.last_line)

    def finish_paren(self):
        """A bracketed expression, after its opening bracket."""
        self.open_brackets.append("(")
        inner = self.expression()
        self.open_brackets.pop()
        self.take(")")
        return inner

    def prefix(self):
        """What an expression can start with: a literal, a name, a unary sign, a bracket, a block or a keyword."""
        token = self.take()
        if token.kind in ("num", "str"):
            return Node(token.kind, token.text, line=token.line, end_line=token.line)
        if token.kind == "name" and token.text not in KEYWORDS:
            return Node("name", token.text, line=token.line, end_line=token.line)
        if token.kind == "name":
            return self.keyword(token)
        if token.kind == "op" and token.text == "(":
            self.open_brackets.append("(")
            inner = self.expression()
            self.open_brackets.pop()
            self.take(")")
            return Node("paren", args=(inner,), line=token.line, end_line=self.last_line)
        if token.kind == "op" and token.text == "{":
            return self.block(token)
        if token.kind == "op" and token.text == "\\":
            return self.function(token)
        if token.kind == "op" and token.text in UNARY_POWER:
            self.skip_newlines()
            operand = self.expression(UNARY_POWER[token.text])
            return Node("unary", token.text, (operand,), line=token.line, end_line=self.last_line)
        raise NotParsed("line %d: '%s' stands where an expression should start" % (token.line, token.text or "the end of the file"))

    def block(self, opening):
        """The expressions between curly brackets."""
        self.open_brackets.append("{")
        statements = []
        while True:
            while self.tokens[self.position].kind == "newline" or self.is_op(";"):
                self.position += 1
            if self.is_op("}"):
                break
            if self.peek().kind == "end":
                raise NotParsed("the '{' on line %d is never closed" % opening.line)
            statements.append(self.expression())
        self.open_brackets.pop()
        self.take("}")
        return Node("block", args=tuple(statements), line=opening.line, end_line=self.last_line)

    def condition(self):
        """The bracketed condition of if and while."""
        self.take("(")
        self.open_brackets.append("(")
        inner = self.expression()
        self.open_brackets.pop()
        self.take(")")
        self.skip_newlines()
        return inner

    def keyword(self, token):
        """if, for, while, repeat, function and the other reserved words."""
        if token.text == "function":
            return self.function(token)
        if token.text == "if":
            parts = [self.condition(), self.expression()]
            mark = self.position
            self.skip_newlines()
            if self.peek().kind == "name" and self.peek().text == "else":
                self.take()
                self.skip_newlines()
                parts.append(self.expression())
            else:
                self.position = mark
            return Node("if", args=tuple(parts), line=token.line, end_line=self.last_line)
        if token.text == "for":
            self.take("(")
            self.open_brackets.append("(")
            variable = self.take()
            if not (self.peek().kind == "name" and self.peek().text == "in"):
                raise NotParsed("line %d: 'in' was expected in the for loop" % token.line)
            self.take()
            sequence = self.expression()
            self.open_brackets.pop()
            self.take(")")
            self.skip_newlines()
            body = self.expression()
            return Node("for", variable.text, (sequence, body), line=token.line, end_line=self.last_line)
        if token.text == "while":
            return Node("while", args=(self.condition(), self.expression()), line=token.line, end_line=self.last_line)
        if token.text == "repeat":
            self.skip_newlines()
            return Node("repeat", args=(self.expression(),), line=token.line, end_line=self.last_line)
        if token.text in ("break", "next"):
            return Node("name", token.text, line=token.line, end_line=token.line)
        raise NotParsed("line %d: '%s' stands where an expression should start" % (token.line, token.text))

    def function(self, token):
        """A function definition: its formal arguments with their defaults as written, and its body."""
        self.take("(")
        self.open_brackets.append("(")
        names, defaults = [], []
        while not self.is_op(")"):
            formal = self.take()
            if formal.kind != "name" and formal.text != "...":
                raise NotParsed("line %d: an argument name was expected in the function header" % formal.line)
            names.append(formal.text)
            if self.is_op("="):
                self.take()
                defaults.append(self.expression(3))
            else:
                defaults.append(Node("missing", line=formal.line))
            if self.is_op(","):
                self.take()
        self.open_brackets.pop()
        self.take(")")
        self.skip_newlines()
        body = self.expression(1)
        return Node("function", args=tuple(defaults) + (body,), names=tuple(names), line=token.line, end_line=self.last_line)

    def call_or_index(self, target):
        """Calls and the three kinds of indexing that may follow an expression."""
        opening = self.take()
        closer = ")" if opening.text == "(" else "]"
        self.open_brackets.append("(" if opening.text == "(" else "[")
        arguments, names = [], []
        while not self.is_op(closer):
            if self.is_op(","):
                self.take()
                arguments.append(Node("missing", line=self.last_line))
                names.append("")
                continue
            name = ""
            following = self.tokens[self.position + 1] if self.position + 1 < len(self.tokens) else None
            if self.peek().kind in ("name", "str") and following is not None and following.kind == "op" and following.text == "=":
                name = self.take().text
                self.take("=")
            if self.is_op(",") or self.is_op(closer):
                arguments.append(Node("missing", line=self.last_line))
            else:
                arguments.append(self.expression(3))
            names.append(name)
            if self.is_op(","):
                self.take()
                if self.is_op(closer) and opening.text != "(":
                    arguments.append(Node("missing", line=self.last_line))
                    names.append("")
        self.open_brackets.pop()
        self.take(closer)
        if opening.text == "[[":
            self.take("]")
        kind = "call" if opening.text == "(" else "index"
        return Node(kind, opening.text, (target,) + tuple(arguments), tuple(names), target.line, self.last_line)

def parse_r_source(source):
    """Parse a file ONE top-level expression at a time. An expression that cannot be read
    becomes ("not read", first line, last line, reason) and reading continues with the next
    one, so a single odd construct never costs the rest of the file. Enforces: R2, R7"""
    try:
        tokens = tokenize_r(source)
    except NotParsed as problem:
        return [("not read", 1, source.count("\n") + 1, str(problem))]
    parser, results = RParser(tokens), []
    while True:
        while parser.tokens[parser.position].kind == "newline" or (parser.tokens[parser.position].kind == "op" and
                                                                   parser.tokens[parser.position].text == ";"):
            parser.position += 1
        if parser.tokens[parser.position].kind == "end":
            return results
        start = parser.position
        try:
            parser.open_brackets = []
            node = parser.expression()
            follower = parser.tokens[parser.position]
            if follower.kind not in ("newline", "end") and not (follower.kind == "op" and follower.text == ";"):
                raise NotParsed("line %d: '%s' stands where the expression should have ended" % (follower.line, follower.text))
            results.append(node)
        except NotParsed as problem:
            depth, position = 0, start
            while tokens[position].kind != "end":               # skip to where the next statement starts
                text = tokens[position].text if tokens[position].kind == "op" else ""
                depth += 1 if text in ("(", "{", "[") else 2 if text == "[[" else -1 if text in (")", "}", "]") else 0
                if tokens[position].kind == "newline" and position >= parser.position:
                    first, second = tokens[position + 1], tokens[min(position + 2, len(tokens) - 1)]
                    fresh_start = (first.column == 0 and first.kind == "name" and second.kind == "op"
                                   and second.text in ASSIGNMENT_SIGNS)
                    if depth <= 0 or fresh_start:
                        break
                position += 1
            parser.position = position
            results.append(("not read", tokens[start].line, tokens[max(start, position - 1)].line, str(problem)))

# ---------------------------------------------------------------- facts read from a syntax tree
ARITHMETIC_SIGNS = ("+", "-", "*", "/", "^", "%%", "%/%")
COMPARISON_SIGNS = ("==", "!=", "<", ">", "<=", ">=")
CONSTANT_NAMES = ("TRUE", "FALSE", "NULL", "NA", "NA_integer_", "NA_real_", "NA_character_", "Inf", "NaN",
                  "T", "F", "break", "next", "...")

class CannotConvert(Exception):
    """A piece of code that cannot become a formula tree. The message is a plain reason."""

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
    parsed = core.parse_number(text) or {"value": text, "as_written": text, "decimals": 0, "unit": ""}
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
    """Calls, symbols read and written, numbers and strings of a piece of code, in order of
    appearance. Nested function definitions are left to their own units."""
    calls, read, written, numbers, strings = [], [], [], [], []
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
        if inner.kind == "name" and inner.value not in CONSTANT_NAMES:
            read.append(inner.value)
        elif inner.kind == "num":
            numbers.append(number_token(inner))
        elif inner.kind == "str":
            strings.append(inner.value)
        for child in inner.args:
            visit(child, False)
    visit(node, True)
    unique = lambda values: tuple(dict.fromkeys(values))
    return {"calls": unique(calls), "symbols_read": unique(read), "symbols_written": unique(written),
            "numbers": tuple(numbers), "strings": unique(strings)}

# ---------------------------------------------------------------- from R code to a formula tree
SIGN_TO_OP = {"+": "add", "-": "sub", "*": "mul", "/": "div", "^": "pow"}

def to_expr(node, function_map, known):
    """One R expression to the tool's neutral formula tree, through r_function_map.yaml. `known`
    holds local variables already assigned in the same function: they are substituted, so a
    change three lines above the return still reaches the comparison. Anything the tool cannot
    evaluate raises CannotConvert; nothing is guessed and nothing is run. Enforces: R7"""
    kind = node.kind
    if kind == "num":
        return core.Expr("num", value=number_token(node)["value"])
    if kind == "name":
        if node.value in known:
            return known[node.value]
        if node.value in CONSTANT_NAMES:
            raise CannotConvert("it uses the constant %s" % node.value)
        return core.Expr("sym", name=core.normalise_symbol(node.value))
    if kind == "paren" or (kind == "block" and len(node.args) == 1):
        return to_expr(node.args[0], function_map, known)
    if kind == "unary" and node.value in ("-", "+"):
        inner = to_expr(node.args[0], function_map, known)
        return core.Expr("neg", args=(inner,)) if node.value == "-" else inner
    if kind == "binary" and node.value in SIGN_TO_OP:
        return core.Expr(SIGN_TO_OP[node.value], args=tuple(to_expr(arg, function_map, known) for arg in node.args))
    if kind == "binary" and node.value in COMPARISON_SIGNS:
        return core.Expr("cmp", name=node.value, args=tuple(to_expr(arg, function_map, known) for arg in node.args))
    if kind == "if" and len(node.args) == 3:
        return core.Expr("piecewise", args=tuple(to_expr(arg, function_map, known) for arg in node.args))
    if kind == "dollar" and node.args[0].kind == "name":
        return core.Expr("sym", name="%s$%s" % (node.args[0].value, node.args[1].value))
    if kind == "index" and node.args[0].kind == "name" and node.args[-1].kind == "str" and len(node.args) == 3:
        return core.Expr("sym", name="%s$%s" % (node.args[0].value, node.args[-1].value))   # table[rows, "column"]
    if kind == "call":
        return call_to_expr(node, function_map, known)
    raise CannotConvert("it uses '%s', which the tool cannot turn into a formula" % unparse(node)[:40])

def call_to_expr(node, function_map, known):
    """A call in R to the neutral expression tree, through r_function_map.yaml; anything else cannot be converted."""
    name = callee_name(node)
    if name == "return" and len(node.args) == 2:
        return to_expr(node.args[1], function_map, known)
    entry = function_map["r_functions"].get(name)
    if entry is None:
        raise CannotConvert("it calls %s(), which the tool cannot evaluate" % (name or "a computed function"))
    expected = entry.get("arguments", [])
    placed, extra = {}, []
    for argument_name, argument in zip(node.names, node.args[1:]):
        if argument_name == "na.rm" or argument.kind == "missing":
            continue
        if argument_name in entry.get("only_defaults", []) or (argument_name and argument_name not in expected):
            raise CannotConvert("it calls %s() with '%s', which the tool does not evaluate" % (name, argument_name))
        if argument_name:
            placed[expected.index(argument_name)] = argument
        else:
            extra.append(argument)
    ordered = []
    for position in range(len(placed) + len(extra)):
        ordered.append(placed[position] if position in placed else extra.pop(0))
    enough = len(expected) - entry.get("optional", 0) <= len(ordered) <= len(expected)
    if not entry.get("variadic") and not enough:
        raise CannotConvert("it calls %s() with %d argument(s) where the tool knows it with %d"
                            % (name, len(ordered), len(expected)))
    return core.Expr("call", name=entry["neutral"], args=tuple(to_expr(arg, function_map, known) for arg in ordered))

def is_guard(node, function_map):
    """An argument check that does not change the value: stop(...), stopifnot(...), or an `if`
    without `else` whose body only holds such calls."""
    if node.kind == "call":
        return callee_name(node) in function_map["plumbing_calls"]
    if node.kind == "if" and len(node.args) == 2:
        body = node.args[1]
        return all(is_guard(statement, function_map) for statement in (body.args if body.kind == "block" else (body,)))
    return False

def compose_function(function_node, function_map):
    """The value a straight-line function returns, as one formula in its arguments: local
    assignments are substituted in order. Branches that assign, loops and anything the tool
    cannot evaluate raise CannotConvert ("the function could not be composed")."""
    body = function_node.args[-1]
    statements = body.args if body.kind == "block" else (body,)
    known, result = {}, None
    for position, statement in enumerate(statements):
        parts = assignment_parts(statement)
        if parts and parts[0].kind == "name" and parts[1].kind != "function":
            known[parts[0].value] = result = to_expr(parts[1], function_map, known)
        elif statement.kind == "call" and callee_name(statement) == "return":
            return to_expr(statement, function_map, known), known
        elif position == len(statements) - 1:
            result = to_expr(statement, function_map, known)
        elif is_guard(statement, function_map):
            continue
        else:
            raise CannotConvert("it has steps that the tool cannot follow in a straight line")
    if result is None:
        raise CannotConvert("it returns nothing that the tool can follow")
    return result, known

# ---------------------------------------------------------------- units from R source
def draft(kind, path, lines, name, text, **more):
    """A unit before it has its reference. References are given at the end, in reading order."""
    unit = {"kind": kind, "file": path, "lines": lines, "name": name, "inside": "", "text": text,
            "parent_key": None, "key": "%s:%s:%s:%s" % (path, lines[0] if lines else 0, kind, name),
            "code": None, "data": None, "roxygen": None, "helppage": None, "read_problem": None, "node": None}
    unit.update(more)
    return unit

def code_detail(node, function_map, settings, **more):
    """The facts about a piece of code that later steps use: symbols, numbers, calls, strings, expression."""
    facts = code_facts(node)
    return dict(facts, formals=(), exported=None, expression=None, reads_data=(), plumbing=False,
                plumbing_reason="", composed=None, not_composed_reason="", **more)

def formula_statements(function_node, function_name, parent_key, path, source_lines, context):
    """The formula statements inside one function: assignments, return(...) calls and the last
    expression, when they compute something. Statements at the top of the body also get
    their composed form, with the local variables before them substituted."""
    function_map, trivial = context["function_map"], context["trivial"]
    body = function_node.args[-1]
    top_statements = body.args if body.kind == "block" else (body,)
    units, known = [], {}
    def visit(statement, at_top, is_last):
        if statement.kind in ("block", "if", "for", "while", "repeat"):
            inner = statement.args if statement.kind == "block" else statement.args[1 if statement.kind in ("if", "for", "while") else 0:]
            for position, child in enumerate(inner):
                visit(child, False, is_last and statement.kind == "block" and position == len(inner) - 1)
            return
        parts = assignment_parts(statement)
        value = parts[1] if parts else statement
        if value.kind == "function":
            return
        returned = statement.kind == "call" and callee_name(statement) == "return"
        if not (parts or returned or is_last) or not has_arithmetic(value, function_map, trivial) or is_guard(statement, function_map):
            return
        target = parts[0].value if parts and parts[0].kind == "name" else function_name
        detail = code_detail(statement, function_map, context["settings"])
        for form, table in (("expression", {}), ("composed", known if at_top else None)):
            if table is None:
                detail["not_composed_reason"] = "the statement sits inside a branch or a loop"
                continue
            try:
                tree = to_expr(value, function_map, table)
                detail[form] = core.to_plain(core.Expr("eq", args=(core.Expr("sym", name=core.normalise_symbol(target)), tree)))
            except CannotConvert as problem:
                detail["not_composed_reason"] = str(problem)
        lines = (statement.line, statement.end_line)
        units.append(draft(core.KIND_FORMULA, path, lines, target, "\n".join(source_lines[lines[0] - 1:lines[1]]),
                           inside=function_name, parent_key=parent_key, code=detail, node=statement))
    for position, statement in enumerate(top_statements):
        visit(statement, True, position == len(top_statements) - 1)
        parts = assignment_parts(statement)
        if parts and parts[0].kind == "name" and parts[1].kind != "function":
            try:
                known[parts[0].value] = to_expr(parts[1], function_map, known)
            except CannotConvert:
                known.pop(parts[0].value, None)
    return units

def function_units(name, function_node, lines, path, source_lines, context, inside="", parent_key=None):
    """A function, the formula statements inside it, and any functions defined inside it."""
    function_map = context["function_map"]
    formals = tuple((formal, unparse(default)) for formal, default in zip(function_node.names, function_node.args[:-1]))
    detail = code_detail(function_node, function_map, context["settings"], )
    detail.update(formals=formals, exported=is_exported(name, context["namespace"]) if not inside else False)
    try:
        tree, _ = compose_function(function_node, function_map)
        detail["composed"] = core.to_plain(core.Expr("eq", args=(core.Expr("sym", name=core.normalise_symbol(name)), tree)))
    except CannotConvert as problem:
        detail["not_composed_reason"] = str(problem)
    computes = any(has_arithmetic(part, function_map, context["trivial"]) for part in function_node.args if part.kind != "missing")
    if not computes:                                     # the body AND the defaults: a non-trivial default is never "supporting"
        detail.update(plumbing=True, plumbing_reason="no arithmetic and no number other than the trivial ones: it only "
                                                     "checks, converts or passes values on")
    unit = draft(core.KIND_FUNCTION, path, lines, name, "\n".join(source_lines[lines[0] - 1:lines[1]]),
                 inside=inside, parent_key=parent_key, code=detail, node=function_node)
    units = [unit] + formula_statements(function_node, name, unit["key"], path, source_lines, context)
    for inner in walk(function_node.args[-1]):
        parts = assignment_parts(inner)
        if parts and parts[1].kind == "function" and parts[0].kind == "name":
            units.extend(function_units(parts[0].value, parts[1], (inner.line, inner.end_line), path, source_lines,
                                        context, inside=name, parent_key=unit["key"]))
    return units

def statement_units(node, path, source_lines, context, in_tests):
    """The unit(s) of one top-level expression."""
    function_map, lines = context["function_map"], (node.line, node.end_line)
    text = "\n".join(source_lines[lines[0] - 1:lines[1]])
    parts = assignment_parts(node)
    if parts and parts[1].kind == "function" and parts[0].kind in ("name", "str"):
        return function_units(parts[0].value, parts[1], lines, path, source_lines, context)
    if node.kind == "call" and callee_name(node) in ("test_that", "it", "describe") and len(node.args) >= 2:
        label = node.args[1].value if node.args[1].kind == "str" else "test"
        return [draft(core.KIND_TEST, path, lines, label, text, code=code_detail(node, function_map, context["settings"]), node=node)]
    detail = code_detail(node, function_map, context["settings"])
    if parts and parts[0].kind == "name" and has_arithmetic(parts[1], function_map, context["trivial"]):
        try:
            tree = to_expr(parts[1], function_map, {})
            detail["expression"] = core.to_plain(core.Expr("eq", args=(core.Expr("sym", name=core.normalise_symbol(parts[0].value)), tree)))
        except CannotConvert as problem:
            detail["not_composed_reason"] = str(problem)
        return [draft(core.KIND_FORMULA, path, lines, parts[0].value, text, code=detail, node=node)]
    kind = core.KIND_TEST if in_tests and node.kind == "call" and callee_name(node).startswith("expect_") else core.KIND_TOPLEVEL
    detail.update(plumbing=True, plumbing_reason="a statement without arithmetic (it loads, declares or sets something up)")
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
            units.append(draft(core.KIND_NOT_READ, path, (first, last), "", "\n".join(source_lines[first - 1:last]),
                               read_problem="the tool's R reader could not read this expression: %s" % reason))
        else:
            units.extend(statement_units(result, path, source_lines, context, in_tests))
    units.extend(roxygen_units(path, source_lines, parsed, context))
    units.sort(key=lambda unit: (unit["lines"][0], 0 if unit["kind"] == core.KIND_ROXYGEN else 1, unit["lines"][1] * -1))
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
        units.append(draft(core.KIND_TOPLEVEL, path, (1, len(source_lines)), "", source, code=None))
    for unit in units:
        if unit["parent_key"] is None or unit["kind"] == core.KIND_FUNCTION:
            unit["text"] = "\n".join(source_lines[unit["lines"][0] - 1:unit["lines"][1]])
        unit["lines"] = (unit["lines"][0] + line_offset, unit["lines"][1] + line_offset)
    return units

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
        formulas = []
        text = "\n".join(block_lines)
        for found in re.finditer(r"\\d?eqn(?=\{)", text):
            latex, _ = braces_content(text, found.end())
            try:
                equation = read_equation("latex", latex_to_linear(latex), context["notation"])
            except NotReadable as problem:
                equation = core.EquationData("latex", latex, False, str(problem), None, "")
            formulas.append(dict(core.to_plain(equation), line=first + 1 + text[:found.start()].count("\n")))
        follower = next((r for r in parsed if not isinstance(r, tuple) and r.line >= number + 1), None)
        documents = ""
        if follower is not None:
            parts = assignment_parts(follower)
            if parts and parts[0].kind in ("name", "str"):
                documents = parts[0].value
            elif follower.kind == "str":
                documents = follower.value
        documents = documents or next((tag["text"].split()[0] for tag in tags if tag["tag"] == "name" and tag["text"]), "")
        detail = {"documents_ref": None, "documents_name": documents, "tags": tuple(tags), "formulas": tuple(formulas)}
        units.append(draft(core.KIND_ROXYGEN, path, (first + 1, number), documents, "\n".join(source_lines[first:number]),
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
    first = lambda macro: next((core.normalise_text(content) for name, content in sections if name == macro), "")
    arguments = []
    for name, content in sections:
        if name == "arguments":
            for item in re.finditer(r"\\item\s*(?=\{)", content):
                argument, after = braces_content(content, item.end())
                description, _ = braces_content(content, after) if content[after:after + 1] == "{" else ("", after)
                arguments.append((core.normalise_text(argument), core.normalise_text(description)))
    detail = {"rd_name": first("name"), "aliases": tuple(core.normalise_text(c) for n, c in sections if n == "alias"),
              "title": first("title"), "usage": first("usage"), "arguments": tuple(arguments),
              "generated_from_ref": None, "in_step_with_source": None,
              "generated_from_file": generated_from.group(1) if generated_from else ""}
    return draft(core.KIND_HELP, path, (1, text.count("\n") + 1), detail["rd_name"] or os.path.basename(path), text, helppage=detail)

def vignette_units(path, text, context):
    """A vignette: prose becomes "Vignette text" units, one per stretch between code chunks;
    code chunks are read as R code (and never run)."""
    units, lines, prose_start, number = [], text.split("\n"), 0, 0
    def close_prose(end):
        prose = "\n".join(lines[prose_start:end]).strip()
        if prose:
            units.append(draft(core.KIND_VIGNETTE, path, (prose_start + 1, end), "", prose))
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
        return core.plain_decimal(core.Decimal(repr(number)))
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

def column_kind(cells):
    """Is a column made of numbers, of text, or of both?"""
    values = [cell for cell in cells if cell != "NA"]
    if values and all(re.fullmatch(r"-?\d+", cell) for cell in values):
        return "integer"
    if values and all(re.fullmatch(r"-?\d+(\.\d+)?|-?Inf", cell) for cell in values):
        return "decimal"
    return "logical" if values and all(cell in ("TRUE", "FALSE") for cell in values) else "text"

def row_key_columns(header, rows, kinds):
    """How a row is identified: real row names if present; otherwise the left-most single
    column, or the smallest left-most combination of up to three non-numeric columns, whose
    values are unique; otherwise the row number. The choice is shown in the workbook."""
    import itertools
    if header and header[0] in ("(row name)", "name", "path"):
        return (header[0],)
    candidates = [i for i, kind in enumerate(kinds) if kind in ("text", "logical")]
    for size in (1, 2, 3):
        for combination in itertools.combinations(candidates, size):
            seen = {tuple(row[i] for i in combination) for row in rows}
            if len(seen) == len(rows) and rows:
                return tuple(header[i] for i in combination)
    return ()

def table_display(header, rows):
    """The one-cell display form: at most 50 rows, always below Excel's limit for one cell."""
    shown = ["; ".join(header)] + ["; ".join(row) for row in rows[:50]]
    if len(rows) > 50:
        shown.append("... %d more rows; the full table is in the audit files" % (len(rows) - 50))
    text = "\n".join(shown)
    return text if len(text) < 30000 else text[:30000] + "\n... (cut here; the full table is in the audit files)"

def data_object_unit(name, value, path, settings, decoded_by):
    """One stored object to a unit and, when it is assessable, its full values."""
    found = table_of(value)
    if found is None:
        described = "An object of Python type %s after decoding; it has no tabular meaning, so it is described and not compared." % type(value).__name__
        detail = {"object_name": name, "container_file": path, "r_class": (), "r_type": type(value).__name__, "dims": (),
                  "attributes": {}, "columns": (), "row_keys": (), "n_cells": 0, "canonical_value_hash": "",
                  "decoded_by": decoded_by, "assessable": False,
                  "not_assessable_reason": "it is not a table, a vector or a list of short values"}
        return draft(core.KIND_OBJECT, path, None, name, described, data=detail), None
    header, rows, shape = found
    kinds = [column_kind([row[i] for row in rows]) for i in range(len(header))]
    n_cells = len(rows) * len(header)
    value_hash = core.sha256_text("\x1f".join(header + [cell for row in rows for cell in row]))
    too_large = n_cells > settings["max_parameter_cells"] or len(header) > settings["max_parameter_columns"]
    reason = "too large to be a parameter table (%d cells); it looks like a dataset" % n_cells if too_large else None
    keys = row_key_columns(header, rows, kinds)
    detail = {"object_name": name, "container_file": path, "r_class": (shape,), "r_type": shape,
              "dims": (len(rows), len(header)), "attributes": {}, "columns": tuple(zip(header, kinds)), "row_keys": keys,
              "n_cells": n_cells, "canonical_value_hash": value_hash, "decoded_by": decoded_by,
              "assessable": not too_large, "not_assessable_reason": reason}
    kind = core.KIND_OBJECT if shape == "list" else core.KIND_TABLE
    unit = draft(kind, path, None, name, table_display(header, rows), data=detail)
    values = None if too_large else {"object_name": name, "header": header, "rows": rows, "row_key": list(keys), "column_types": kinds}
    return unit, values

def decode_data_file(path, data, settings):
    """Decode one stored-data file without R. The file is parsed by `rdata`, which evaluates
    nothing; a function or another language object inside it is described, never called.
    Returns (units, full-value records, facts for Model_Package_Info). Enforces: R7"""
    cap = int(settings["max_file_mb"] * 1024 * 1024)
    stem = os.path.splitext(os.path.basename(path))[0]
    if path.lower().endswith((".csv", ".tsv")):
        delimiter = "\t" if path.lower().endswith(".tsv") else ","
        table = [row for row in csv.reader(io.StringIO(core.decode_text(data)), delimiter=delimiter) if row]
        frame_header, frame_rows = (table[0], table[1:]) if table else ([], [])
        unit, values = data_object_unit_from_rows(stem, frame_header, frame_rows, path, settings)
        return [unit], [values] if values else [], "%s: text table" % path
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
        unit = draft(core.KIND_NOT_READ, path, None, stem, "", read_problem="This data file was not read: %s." % reason)
        return [unit], [], "%s: not decoded (%s)" % (path, type(problem).__name__ if not isinstance(problem, NotParsed) else reason)
    objects = converted if container.startswith("several") and isinstance(converted, dict) else {stem: converted}
    units, tables = [], []
    for name in objects:
        unit, values = data_object_unit(str(name), objects[name], path, settings, decoded_by)
        units.append(unit)
        if values:
            tables.append(values)
    fact = "%s: %s, %s layout, %s compression, %d object(s), decoded by %s" % (path, container, layout, method, len(units), decoded_by)
    return units, tables, fact

def data_object_unit_from_rows(name, header, rows, path, settings):
    """A unit for a table given as header and rows (delimited text files under data/ or inst/extdata/)."""
    import pandas
    width = len(header)
    frame = pandas.DataFrame([list(row) + [""] * (width - len(row)) for row in rows], columns=header)
    return data_object_unit(name, frame, path, settings, "the standard csv reader")

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

def built_in_reader(path, data):
    """Which reader the built-in tests give a member, or "" where they give none. A member with
    no reader is read as two thousand characters of running text and the rest of it reaches
    nothing, which is what the plan exists to ask about. Enforces: R13"""
    lowered = path.lower()
    if is_data_file(path):
        return "r-data"
    if lowered.startswith("src/") or b"\x00" in data[:4096]:
        return "not read"                            # compiled or binary: named as such, never guessed at
    if is_parsed_r_file(path):
        return "r-source"
    if lowered.endswith(".rd") and lowered.startswith("man/"):
        return "help-page"
    if lowered.endswith((".rmd", ".rnw", ".qmd")):
        return "vignette"
    if path in ("DESCRIPTION", "NAMESPACE") or lowered.endswith((".md", ".txt")) and "/" not in path:
        return "prose"
    return ""

def file_units(path, data, context, facts, reader=""):
    """The units of one file of the package, by where it lies and what it is. A reader chosen
    for this member overrides only where the built-in tests give none."""
    lowered = path.lower()
    if reader and not is_data_file(path) and not lowered.startswith("src/"):
        text = core.decode_text(data) if b"\x00" not in data[:4096] else None
        if text is not None:
            if reader == "r-source":
                return units_from_r_source(path, text, context)
            if reader == "help-page":
                return [help_page_unit(path, text)]
            if reader == "vignette":
                return vignette_units(path, text, context)
            if reader in ("r-data", "table-file"):
                units, tables, fact = decode_data_file(path, data, context["settings"])
                context["tables"].extend(tables)
                facts["data"].append(fact)
                return units
    if is_data_file(path):
        units, tables, fact = decode_data_file(path, data, context["settings"])
        context["tables"].extend(tables)
        facts["data"].append(fact)
        return units
    if lowered.startswith("src/"):
        return [draft(core.KIND_COMPILED, path, None, os.path.basename(path), "",
                      read_problem="Compiled code is not read by the tool; it needs a manual review.")]
    text = core.decode_text(data) if b"\x00" not in data[:4096] else None
    if text is None:
        return [draft(core.KIND_NOT_READ, path, None, os.path.basename(path), "",
                      read_problem="A binary file of a kind the tool does not know; it needs a manual review.")]
    if is_parsed_r_file(path):
        return units_from_r_source(path, text, context)
    if lowered.endswith(".rd") and lowered.startswith("man/"):
        return [help_page_unit(path, text)]
    if lowered.endswith((".rmd", ".rnw", ".qmd")):
        return vignette_units(path, text, context)
    return [draft(core.KIND_OTHER, path, (1, text.count("\n") + 1), os.path.basename(path), text[:2000])]

def link_documentation_units(units):
    """Tie each roxygen block to the object it documents and each help page to the block that
    generated it (by name and aliases), and say whether the page is still in step with it."""
    by_name = {}
    for unit in units:
        if unit["kind"] in (core.KIND_FUNCTION, core.KIND_TABLE, core.KIND_OBJECT) and not unit["inside"]:
            by_name.setdefault(unit["name"], unit)
    blocks = {}
    for unit in units:
        if unit["kind"] == core.KIND_ROXYGEN:
            target = by_name.get(unit["roxygen"]["documents_name"])
            unit["roxygen"]["documents_ref"] = target["key"] if target else None
            blocks.setdefault(unit["roxygen"]["documents_name"], unit)
    for unit in units:
        if unit["kind"] == core.KIND_HELP:
            page = unit["helppage"]
            block = next((blocks[name] for name in (page["rd_name"],) + tuple(page["aliases"]) if name in blocks), None)
            if block is not None:
                page["generated_from_ref"] = block["key"]
                parameters = [tag["name"] for tag in block["roxygen"]["tags"] if tag["tag"] == "param"]
                documented = [name for names in parameters for name in names.split(",")]
                page["in_step_with_source"] = sorted(documented) == sorted(name for a, _ in page["arguments"] for name in a.split(", "))

def finalise_units(drafts, file_hashes):
    """Give every draft its reference, in reading order, and turn keys into references."""
    refs = {unit["key"]: core.make_ref("M", number) for number, unit in enumerate(drafts, start=1)}
    units = []
    for unit in drafts:
        for part, field_name in (("roxygen", "documents_ref"), ("helppage", "generated_from_ref")):
            if unit[part] and unit[part][field_name]:
                unit[part][field_name] = refs.get(unit[part][field_name])
        helppage = dict(unit["helppage"]) if unit["helppage"] else None
        if helppage:
            helppage.pop("generated_from_file", None)
        units.append(core.ModelUnit(
            ref=refs[unit["key"]], kind=unit["kind"], file=unit["file"], lines=unit["lines"], name=unit["name"],
            inside=unit["inside"], text=unit["text"], parent_ref=refs.get(unit["parent_key"]),
            file_sha256=file_hashes[unit["file"]], content_hash=core.content_hash(unit["text"]),
            code=core.CodeDetail(**unit["code"]) if unit["code"] else None,
            data=core.ParameterDataDetail(**unit["data"]) if unit["data"] else None,
            roxygen=core.RoxygenDetail(**unit["roxygen"]) if unit["roxygen"] else None,
            helppage=core.HelpPageDetail(**helppage) if helppage else None, read_problem=unit["read_problem"]))
    return units, refs

def package_rows(description, namespace, units, facts, refused):
    """The package lines of Model_Package_Info."""
    rows = [("Package", "Name", description.get("Package", "not stated")),
            ("Package", "Version", description.get("Version", "not stated")),
            ("Package", "Title", description.get("Title", "")), ("Package", "Parser", PARSER_NAME)]
    counts = {}
    for unit in units:
        counts[unit.kind] = counts.get(unit.kind, 0) + 1
    rows.extend(("Package", "Units of kind %s" % kind, counts[kind]) for kind in core.UNIT_KINDS if kind in counts)
    exported = sorted(u.name for u in units if u.kind == core.KIND_FUNCTION and u.code and u.code.exported)
    rows.append(("Package", "Exported functions", ", ".join(exported) or "none found"))
    rows.extend(("Package data", "Data file", fact) for fact in facts["data"])
    rows.extend(("Package data", "Not assessed", "%s (%s): %s" % (u.ref, u.name, u.data.not_assessable_reason))
                for u in units if u.data and not u.data.assessable)
    rows.extend(("Package", "Could not be read", "%s %s lines %s" % (u.ref, u.file, "-".join(str(n) for n in u.lines or ())))
                for u in units if u.kind == core.KIND_NOT_READ)
    rows.extend(("Package", "Member of the tarball refused", "%s: %s" % entry) for entry in refused)
    return [{"group": group, "item": item, "value": value} for group, item, value in rows if value != ""]

def package_plan(ctx, files, placed, package_name):
    """Ask which existing reader should take each member the built-in tests leave unplaced.

    The answer chooses among readers the tool already has. It never reaches the R tokenizer, the
    parser, the expression trees or the decoder of stored data: a model's reading of code is an
    assertion about the code, not a parse of it. A file sent to a reader that cannot make sense
    of it becomes a unit saying so, exactly as today, and there is no answer that leaves a
    member unread. Enforces: R3, R7, R13"""
    unplaced = [path for path in sorted(files) if not placed.get(path)]
    if not unplaced or ctx.ask is None or ctx.settings.get("agentic_reading") == "off":
        return {}, [], []
    digest = core.manifest_digest(files, placed, safe_text, package_name)
    prompt = core.load_prompt("package-plan")
    question = core.package_plan_question(digest, prompt, ctx.settings)
    if question["too_large"]:
        return {}, [digest], ["The list of files in the package is too large to ask about, so the built-in tests read it."]
    found = ctx.ask([question]).get(question["question_id"])
    answer = (found or {}).get("answer")
    if not answer:
        return {}, [digest], ["The package was read by the built-in tests; a guided reading was not available."]
    readers, why = answer["readers"], answer.get("why") or {}
    notes = ["%s was read as %s on the model's proposal%s"
             % (path, readers[path], " (%s)" % why[path] if path in why else "")
             for path in sorted(readers)]
    return readers, [digest], notes

def safe_text(data):
    """A member as text, or None where it holds bytes the tool cannot decode."""
    return core.decode_text(data) if b"\x00" not in data[:4096] else None

def read_package(ctx):
    """Step 04, read-package. Files are taken in a fixed order (DESCRIPTION, NAMESPACE, R/,
    data, man/, tests/, vignettes/, the rest; by name inside each), so references are stable
    for an unchanged tarball. Enforces: R2, R5"""
    tarballs = ctx.options["inputs"]["package"]
    if not tarballs:
        return core.StepResult({}, {"units": 0}, ["No package was found in Inputs/2_Model_Package."])
    limit, root = int(ctx.settings["max_file_mb"] * 1024 * 1024), (ctx.options["inputs"].get("roots") or {}).get("package")
    archives = [path for path in tarballs if is_archive(path)]
    try:
        files, refused = unpack_package(archives[0], limit) if archives else loose_package(tarballs, root, limit)
    except Exception as problem:                     # a package that cannot be opened is named, never a stopped run (R2)
        return core.StepResult({}, {"units": 0}, ["The package could not be opened: %s." % core.reason_for(problem)])
    tarballs = archives or tarballs
    files = strip_top_folder(files)
    function_map = yaml.safe_load(R_FUNCTION_MAP_YAML)
    description = read_description(core.decode_text(files["DESCRIPTION"])) if "DESCRIPTION" in files else {}
    namespace = read_namespace(core.decode_text(files["NAMESPACE"])) if "NAMESPACE" in files else None
    context = {"function_map": function_map, "notation": function_map["notation"], "namespace": namespace,
               "trivial": set(ctx.settings["trivial_numbers"]), "settings": ctx.settings, "tables": []}
    order = ("description", "namespace", "r", "data", "inst", "man", "tests", "vignettes")
    def rank(path):
        top = path.split("/")[0].lower()
        return (order.index(top) if top in order else len(order), path)
    placed = {path: built_in_reader(path, files[path]) for path in files}
    chosen, digests, plan_notes = package_plan(ctx, files, placed, description.get("Package", ""))
    drafts, facts = [], {"data": []}
    for path in sorted(files, key=rank):
        drafts.extend(file_units(path, files[path], context, facts, chosen.get(path, "")))
    data_names = {unit["name"] for unit in drafts if unit["data"]}
    data_files = {}
    for unit in drafts:
        if unit["data"]:
            data_files.setdefault(os.path.splitext(os.path.basename(unit["file"]))[0], []).append(unit["name"])
    for unit in drafts:
        if unit["kind"] == core.KIND_FUNCTION:
            formals = [name for name, _ in unit["code"]["formals"]]
            unit["code"]["reads_data"] = data_reads(unit["node"], formals, data_names, data_files)
    link_documentation_units(drafts)
    hashes = {path: core.sha256_bytes(data) for path, data in files.items()}
    units, refs = finalise_units(drafts, hashes)
    tables = []
    for unit in units:
        if unit.data and unit.data.assessable:
            values = next(t for t in context["tables"] if t["object_name"] == unit.name)
            tables.append(dict(values, unit_ref=unit.ref))
    inventory = [{"file": path, "bytes": len(files[path]), "sha256": hashes[path], "swhid": core.swhid_content(files[path])}
                 for path in sorted(files)]
    for entry in inventory:                              # for identity part 3: the lines that must lie inside a unit
        if is_parsed_r_file(entry["file"]):
            lines = core.decode_text(files[entry["file"]]).split("\n")
            entry["nonblank_lines"] = [number for number, line in enumerate(lines, start=1) if line.strip()]
    info = {"name": description.get("Package", ""), "version": description.get("Version", ""), "parser": PARSER_NAME,
            "tarball": os.path.basename(tarballs[0]), "files": inventory,
            "rows": package_rows(description, namespace, units, facts, refused)}
    messages = ["%d units read from %d files of the package." % (len(units), len(files))]
    r_files = sum(1 for path in files if path.lower().endswith(".r"))
    other_code = sum(1 for path in files if path.lower().endswith((".py", ".sas", ".m", ".jl", ".scala", ".java", ".cpp", ".c")))
    is_r_package = ("DESCRIPTION" in files and "Package:" in core.decode_text(files["DESCRIPTION"])) or (r_files and r_files >= other_code)
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
    plain_units = [core.to_plain(unit) for unit in units]
    account = core.account_of_package(files, plain_units, refused, lambda path: is_parsed_r_file(path) or os.path.splitext(path)[1].lower() in TEXT_MEMBERS or "/" not in path)
    info["rows"].extend({"group": "The package", "item": "content account", "value": line}
                        for line in core.account_lines(account))
    if not account["closed"]:
        messages.append("The content account of the package is open; Model_Package_Info says what could not be placed.")
    info["rows"].extend({"group": "The package", "item": "how it was read", "value": note} for note in plan_notes)
    return core.StepResult({"model_units": units, "parameter_tables": tables, "package_info": [info],
                              "content_accounts": [account], "shape_digests": digests},
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

class Dataflow:
    """The data flow of one package, traced function by function. Node ids:
    'f:v' a value v set in function f; 'f:arg:a' a parameter; 'f:return' what f returns;
    'call:f:line:g' one call of g from f; 'column:c' a data-frame column; 'data:t' a stored table;
    'file:path'; 'number:value:f:line'; 'guard:f:line' a call whose value is not kept;
    'outside:name' a name from outside the package (R itself, another package, the session)."""

    def __init__(self, units, trivial=()):
        self.units, self.trivial = units, set(trivial)
        self.functions = {u["name"]: u for u in units if u["kind"] == core.KIND_FUNCTION and not u.get("inside")}
        self.tables = {u["data"]["object_name"]: u for u in units if (u.get("data") or {}).get("object_name")}
        self.nodes, self.records, self.parsed = {}, [], {}
        for name, unit in self.functions.items():
            found = parse_r_source(unit["text"])
            node = found[0] if found and not isinstance(found[0], tuple) else None
            parts = assignment_parts(node) if node is not None else None
            self.parsed[name] = parts[1] if parts and parts[1].kind == "function" else node if node is not None and node.kind == "function" else None

    # ------------------------------------------------ records
    def node(self, node_id, kind, name, env=None, at=None, sources=(), **extra):
        record = self.nodes.get(node_id)
        if record is None:
            record = {"record_type": "node", "node": node_id, "kind": kind, "name": name, "function": env["function"] if env else "",
                      "function_ref": self.functions[env["function"]]["ref"] if env else "", "line": self.line_of(env, at),
                      "code": self.code_of(env, at), "from": []}
            self.nodes[node_id] = record
        for source in sources:
            if source not in record["from"] and source != node_id:
                record["from"].append(source)
        record.update(extra)
        return node_id

    def gap(self, env, at, why):
        self.records.append({"record_type": "gap", "function": env["function"], "function_ref": self.functions[env["function"]]["ref"],
                             "line": self.line_of(env, at), "code": self.code_of(env, at), "why": why})

    def line_of(self, env, at):
        return self.functions[env["function"]]["lines"][0] + at.line - 1 if env and at is not None and at.line else 0

    def code_of(self, env, at):
        """The code as written: the lines of the unit's own text that the node spans."""
        if not env or at is None or not at.line:
            return ""
        lines = self.functions[env["function"]]["text"].split("\n")
        return "\n".join(lines[at.line - 1:max(at.line, at.end_line or at.line)]).strip()

    # ------------------------------------------------ one function
    def trace(self, name):
        function = self.parsed.get(name)
        env = {"function": name, "formals": set(), "locals": set(), "lambda": set()}
        if function is None:
            self.records.append({"record_type": "gap", "function": name, "function_ref": self.functions[name]["ref"], "line": self.functions[name]["lines"][0],
                                 "code": self.functions[name]["text"].split("\n")[0], "why": "the function could not be read"})
            return
        env["formals"] = set(function.names)
        env["locals"] = {parts[0].value for inner in walk_nodes(function.args[-1]) for parts in [assignment_parts(inner)]
                         if parts and parts[0].kind in ("name", "str")}
        for formal, default in zip(function.names, function.args[:-1]):
            defaults = self.sources(default, env) if default.kind != "missing" else []
            self.node("%s:arg:%s" % (name, formal), "argument", formal, env, function, default_from=defaults,
                      default_code=self.code_of(env, default) if default.kind != "missing" else "")
        returned = self.body(function.args[-1], env)
        for inner in walk_nodes(function.args[-1]):
            if inner.kind == "call" and callee_name(inner) == "return" and len(inner.args) > 1:
                returned += self.sources(inner.args[1], env)
        self.node("%s:return" % name, "return", "the value %s returns" % name, env, function, list(dict.fromkeys(returned)))

    def body(self, block, env):
        """The statements of a body, each set value a node; returns the sources of what the body gives."""
        items = list(block.args) if block.kind == "block" else [block]
        given = []
        for position, item in enumerate(items):
            last = position == len(items) - 1
            parts = assignment_parts(item)
            if parts:
                target = parts[0]
                while target.kind in ("dollar", "index") and target.args:
                    target = target.args[0]                 # x$c <- v and x[i] <- v change x
                if item.value in ("<<-", "->>"):
                    self.gap(env, item, "a value assigned outside the function with <<-")
                if target.kind in ("name", "str"):
                    extra = self.sources(parts[0], env) if parts[0] is not target else []
                    node = self.node("%s:%s" % (env["function"], target.value), "value", target.value, env, item,
                                     self.sources(parts[1], env) + extra)
                    given = [node] if last else given
            elif item.kind == "if" and not last:
                self.sources(item.args[0], env)
                for branch in item.args[1:]:
                    self.body(branch, env)
            elif item.kind in ("for", "while", "repeat"):
                self.sources(item.args[0], env) if item.kind != "repeat" else None
                self.body(item.args[-1], env)
            elif last:
                given = self.sources(item, env)
            elif not (item.kind == "call" and callee_name(item) == "return"):
                self.node("guard:%s:%d" % (env["function"], item.line), "guard", self.code_of(env, item).split("\n")[0][:80], env, item,
                          self.sources(item, env))
        return given

    # ------------------------------------------------ what a value is computed from
    def sources(self, node, env, masked=False):
        kind = node.kind
        if kind == "num":
            value = node.value.rstrip("Li")
            return [self.node("number:%s:%s:%d" % (value, env["function"], node.line), "number", value, env, node, trivial=value in self.trivial)]
        if kind in ("str", "missing"):
            return []
        if kind == "name":
            return self.resolve(node.value, env, masked)
        if kind == "binary" and node.value in ("%>%", "|>"):
            left, right = node.args
            call = right if right.kind == "call" else Node("call", "(", (right,), (), right.line, right.end_line)
            return self.sources(Node("call", "(", (call.args[0], left) + tuple(call.args[1:]), ("",) + tuple(call.names),
                                     call.line, call.end_line), env, masked)
        if kind == "binary" and node.value in ASSIGNMENT_SIGNS:
            self.body(Node("block", "", (node,), (), node.line, node.end_line), env)
            parts = assignment_parts(node)
            return self.resolve(parts[0].value, env, masked) if parts and parts[0].kind == "name" else []
        if kind == "dollar":
            holder, field = node.args[0], node.args[1] if len(node.args) > 1 else None
            if holder.kind == "name" and holder.value == ".data" and field is not None:
                return self.resolve(field.value, dict(env, locals=set(), formals=set()), True)   # dplyr's pronoun: a column
            if holder.kind == "name" and holder.value == ".env" and field is not None:
                return self.resolve(field.value, env, False)                                   # dplyr's pronoun: not a column
            return self.sources(holder, env, masked)
        if kind == "ns":
            return []
        if kind == "function":
            self.gap(env, node, "a function written in place, whose arguments are given at run time")
            inner = dict(env, **{"lambda": set(env["lambda"]) | set(node.names)})
            return self.sources(node.args[-1], inner, masked)
        if kind == "call":
            return self.call(node, env, masked)
        return [source for child in node.args for source in self.sources(child, env, masked)]

    def resolve(self, name, env, masked):
        if name in CONSTANT_NAMES or name in env["lambda"]:
            return []
        if name in env["locals"]:
            return ["%s:%s" % (env["function"], name)]
        if name in env["formals"]:
            return ["%s:arg:%s" % (env["function"], name)]
        if name in self.tables:
            return [self.table_node(name)]
        if name in self.functions:
            return []                                        # a function passed as a value: its call is what counts
        if masked:                                           # inside dplyr, a bare name is a column of the data
            return [self.node("column:%s" % name, "column", name, created_in=self.nodes.get("column:%s" % name, {}).get("created_in", []))]
        return [self.node("outside:%s" % name, "outside", name)]

    def table_node(self, name):
        table = self.tables[name]
        return self.node("data:%s" % name, "stored data", name, file=table["data"].get("container_file", ""), unit_ref=table["ref"],
                         columns=[column for column, _ in table["data"].get("columns") or []])

    def call(self, node, env, masked):
        name = callee_name(node)
        args = list(node.args[1:])
        names = list(node.names) + [""] * (len(args) - len(node.names))
        if name in OPAQUE_CALLS:
            self.gap(env, node, OPAQUE_CALLS[name])
            return [source for arg in args for source in self.sources(arg, env, masked)]
        if name in FILE_READERS:
            path = self.file_path(args[0]) if args else ""
            if not path:
                self.gap(env, node, "a file read from a path built at run time")
                return [source for arg in args for source in self.sources(arg, env, masked)]
            table = next((t for t, u in self.tables.items() if u["data"].get("container_file") == path), None)
            return [self.node("file:%s" % path, "file", path, unit_ref=self.tables[table]["ref"] if table else "")]
        if name in DPLYR_CREATE:
            frame = self.sources(args[0], env, masked) if args and not names[0] else []
            created = []
            for arg, column in zip(args, names):
                if column:
                    created.append(self.node("column:%s" % column, "column", column, env, node, self.sources(arg, env, True)))
                    self.nodes["column:%s" % column].setdefault("created_in", [])
                    if env["function"] not in self.nodes["column:%s" % column]["created_in"]:
                        self.nodes["column:%s" % column]["created_in"].append(env["function"])
                elif arg is not args[0]:
                    self.gap(env, node, "columns created by an expression that does not name them")
            return frame + created
        if name in DPLYR_JOIN:
            keys = {inner.value for arg, label in zip(args, names) if label == "by" for inner in walk_nodes(arg) if inner.kind == "str"}
            joined = []
            for arg in args[:2]:
                joined += self.sources(arg, env, masked)
                if arg.kind == "name" and arg.value in self.tables:     # the table's columns join the data; its keys only match
                    for column in self.nodes[self.table_node(arg.value)]["columns"]:
                        if column not in keys:
                            joined.append(self.node("column:%s" % column, "column", column, env, node, ["data:%s" % arg.value]))
            return joined
        if name in APPLIERS:
            found = []
            for arg in args:
                if arg.kind == "name" and arg.value in self.functions:
                    found.append(self.record_call(arg.value, env, node, [], [], masked))
                else:
                    found += self.sources(arg, env, masked)
            return found
        inner = masked or name in DPLYR_MASKING
        values = [self.sources(arg, env, inner) for arg in args]
        if name in self.functions:
            return [self.record_call(name, env, node, values, names, inner)]
        return [source for value in values for source in value]

    def record_call(self, callee, env, node, values, names, masked):
        """One call of a package function: its node, the parameter each argument goes to there - by name
        first, then by position, R's own order - and what a parameter left out takes: its default."""
        formals = list(self.parsed[callee].names) if self.parsed.get(callee) is not None else []
        bound, free = {}, [f for f in formals if f not in names and f != "..."]
        for value, name in zip(values, names):
            if name in formals:
                bound[name] = value
            elif free:
                bound[free.pop(0)] = value
            elif "..." in formals:
                bound.setdefault("...", []).extend(value)
        bindings = {formal: bound.get(formal, ["default"]) for formal in formals}
        call_id = "call:%s:%d:%s" % (env["function"], node.line, callee)
        self.node(call_id, "call", "%s()" % callee, env, node, [source for value in values for source in value] + ["%s:return" % callee],
                  callee=callee, bindings=bindings)
        return call_id

    def file_path(self, arg):
        """The path a reader is given: a string as written, or system.file(...), which names a file under inst/."""
        if arg.kind == "str":
            return arg.value
        if arg.kind == "call" and callee_name(arg) == "system.file":
            parts = [a.value for a, n in zip(arg.args[1:], list(arg.names) + [""] * len(arg.args)) if a.kind == "str" and not n]
            return "inst/" + "/".join(parts) if parts else ""
        return ""

    # ------------------------------------------------ the whole package
    def run(self):
        for name in sorted(self.functions, key=lambda n: self.functions[n]["ref"]):
            self.trace(name)
        calls = [r for r in self.nodes.values() if r["kind"] == "call"]
        called = {r["callee"] for r in calls if r["callee"] != r["function"]}
        entry = set()
        for unit in self.units:                          # the tests and vignettes that call a package function
            if unit["kind"] in (core.KIND_TEST, core.KIND_TOPLEVEL, core.KIND_VIGNETTE):
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
    vignettes call. Enforces: R2, R4, R7"""
    flow = Dataflow(ctx.read("model_units"), ctx.settings["trivial_numbers"])
    records = flow.run()
    count = lambda kind: sum(1 for r in records if r.get("kind") == kind)
    gaps = [r for r in records if r["record_type"] == "gap"]
    roots = records[-1]
    return core.StepResult({"dataflow": records},
                           {"values": count("value"), "calls": count("call"), "columns": count("column"), "gaps": len(gaps),
                            "proposed final outputs": len(roots["proposed"])},
                           ["Traced %d functions: %d values, %d calls, %d columns; %d gaps for the agents. Proposed final outputs: %s."
                            % (len(flow.functions), count("value"), count("call"), count("column"), len(gaps), ", ".join(roots["proposed"]) or "none")])

def walk_dataflow(records, function):
    """Everything the value a function returns is computed from, followed into every call with that call's
    own arguments: (leaves, loops, functions reached). A parameter of a called function is what the call
    passed it there, or its default; a parameter of the function the walk began in is a raw input. A
    leaf is where the flow starts: such a parameter, a stored table, a file, a number, a column nothing
    creates, or a name from outside the package. A function already being walked is a loop. Enforces: R2"""
    nodes = {r["node"]: r for r in records if r["record_type"] == "node"}
    leaves, loops, reached, seen = set(), set(), {function}, set()
    def visit(node_id, frames):
        key = (node_id, tuple(frame for frame, _ in frames))
        if key in seen:
            return
        seen.add(key)
        node = nodes.get(node_id)
        if node is None or node["kind"] in ("stored data", "file", "number", "outside"):
            leaves.add(node_id)
            return
        if node["kind"] == "call":
            if node["callee"] in (frame for frame, _ in frames):
                loops.add(node_id)                           # a loop stops the descent, not what the call is given
                for source in node["from"]:
                    if source != "%s:return" % node["callee"]:
                        visit(source, frames)
                return
            reached.add(node["callee"])
            visit("%s:return" % node["callee"], frames + [(node["callee"], node["bindings"])])
            return
        if node["kind"] == "argument" and node["function"] == frames[-1][0]:
            bound = frames[-1][1]
            if bound is None:
                leaves.add(node_id)                          # a parameter of the final output: a raw input
                return
            given = bound.get(node["name"], ["default"])
            for source in (node.get("default_from") or [] if given == ["default"] else given):
                visit(source, frames if given == ["default"] else frames[:-1])
            if given == ["default"] and not node.get("default_from"):
                leaves.add(node_id)
            return
        if node["kind"] == "column" and not node["from"]:
            leaves.add(node_id)                              # a column no verb creates: it came in with the data
            return
        for source in node["from"]:
            visit(source, frames)
    visit("%s:return" % function, [(function, None)])
    return leaves, loops, reached
