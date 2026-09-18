"""
AIVA 0.0.1 - aiva1_documents.py - reading the methodology and the model documentation. For Reviewer 1.

WHAT THIS FILE DOES
  It turns every document in Inputs/1_Methodology and Inputs/3_Model_Documentation into
  citable chunks: paragraphs, tables, figures and equations, each with its place in the
  outline (level, heading chain, numbering as written, paragraph number) and a content
  hash. Whatever the file format, the path is the same:
      bytes -> format found from the content -> repairs (each one recorded)
            -> blocks in reading order -> levels -> chunks.
  It also holds the one parser for written formulas ("K = LGD * N(x)") and the converters
  that bring Office Math, MathML and a LaTeX subset into that linear notation.

WHAT IT TAKES IN AND PRODUCES
  In: the input files of two corners, references/tag_rules.yaml (a project may override it
  with Inputs/tag_rules.yaml) and the notation part of references/r_function_map.yaml.
  Out: chunks_canon, chunks_doc, read_repairs, outline and info_rows records.

WHICH SHEETS SHOW ITS RESULTS
  Chunks_Canon and Chunks_Doc (one row per chunk), the text columns of both mapping sheets,
  and the file, repair and unrecognised-tag lines on Model_Package_Info.

DESIGN RULES ENFORCED HERE (function names in brackets)
  R2  nothing is dropped: a figure, an image equation or an unreadable file is still a
      chunk, so that it gets a status and a flagged item            [blocks_to_chunks, not_read_block]
  R4  citations can be re-verified: every chunk carries a content hash  [blocks_to_chunks]
  R5  same input, same output: reading order only, no clocks, no random choices
  R6  inputs are opened for reading only                            [read_corner]
  R7  no input text is ever executed; formulas are parsed by AIVA's own small parser and
      ambiguous notation is never guessed                           [parse_formula]
  R9  no domain concept: tags, numbering schemes and phrases live in tag_rules.yaml

HOW TO SANITY-CHECK IT
  Run `python -m unittest engine/tests/test_aiva1_documents.py`. In the notebook run the
  appendix cell "Reviewer 1 sanity check" (it runs steps 01 to 03 on sample A_minimal), then
  open Output.xlsx: on Chunks_Canon every table sits in ONE cell, every figure and equation
  has its own row, and Level and Section follow the document's own table of contents.
"""
import email
import html.entities
import html.parser
import io
import os
import re
import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal

import yaml

import aiva0_shared as shared
import aiva0r_reading as reading

SKILL_VERSIONS = {"read-methodology": "0.0.2", "read-documentation": "0.0.2"}

class NotReadable(Exception):
    """A formula or a file that AIVA cannot read. The message is a plain reason for the analyst."""

# ---------------------------------------------------------------- the linear-notation parser
SUPERSCRIPTS = {"\u207b\u00b9": "^-1", "\u00b2": "^2", "\u00b3": "^3", "\u00b9": "^1"}
SIGNS = {"\u2212": "-", "\u00d7": "*", "\u00b7": "*", "\u22c5": "*", "\u2217": "*", "\u00f7": "/",
         "\u2264": "<=", "\u2265": ">=", "**": "^", "\u2061": "", "\u2062": "*", "\u2009": " "}
_TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?P<percent>\s?%)?"
    r"|(?P<name>[^\W\d_][\w]*(?:\.[^\W\d_]\w*)*(?:_\{[^{}]+\}|\[[^\[\]]+\])?)"
    r"|(?P<sign><=|>=|[-+*/^(),=<>\u221a]))")

def load_notation(references_dir):
    """The names AIVA reads as functions in a written formula, from r_function_map.yaml."""
    with open(os.path.join(references_dir, "r_function_map.yaml"), encoding="utf-8") as handle:
        return yaml.safe_load(handle)["notation"]

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
            raise NotReadable("it contains '%s', which AIVA does not read in a formula" % text[position:position + 12].strip())
        if match.group("number"):
            value = Decimal(match.group("number"))
            tokens.append(("number", shared.plain_decimal(value / 100 if match.group("percent") else value)))
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
            left = shared.Expr("eq", args=(left, self.comparison()))
            if self.peek() == ("sign", "="):
                raise NotReadable("it has more than one equals sign")
        return left

    def comparison(self):
        """An expression, optionally compared with another one."""
        left = self.sum()
        if self.peek()[0] == "sign" and self.peek()[1] in ("<", ">", "<=", ">="):
            sign = self.take()[1]
            left = shared.Expr("cmp", name=sign, args=(left, self.sum()))
        return left

    def sum(self):
        """Terms joined by + and -, from left to right."""
        left = self.product()
        while self.peek() in (("sign", "+"), ("sign", "-")):
            op = "add" if self.take()[1] == "+" else "sub"
            left = shared.Expr(op, args=(left, self.product()))
        return left

    def product(self):
        """Factors joined by * and /, from left to right; juxtaposition only where the source allows it."""
        left = self.unary()
        while True:
            if self.peek() in (("sign", "*"), ("sign", "/")):
                op = "mul" if self.take()[1] == "*" else "div"
                left = shared.Expr(op, args=(left, self.unary()))
            elif self.implicit_product and self.term_follows():
                left = shared.Expr("mul", args=(left, self.power()))
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
            return shared.Expr("neg", args=(self.unary(),))
        if self.peek() == ("sign", "+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        """A base with an optional power (right-associative), an inverse-function mark or a percent sign."""
        base = self.atom()
        if self.peek() == ("sign", "^"):
            self.take()
            base = shared.Expr("pow", args=(base, self.unary()))
        if self.term_follows() and not self.implicit_product:
            raise NotReadable("two terms stand side by side without a sign between them, which could "
                              "mean a product or something else; AIVA does not guess")
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
            return shared.Expr("num", value=text)
        if kind == "sign" and text == "(":
            inner = self.statement()
            self.take(")")
            return inner
        if kind == "sign" and text == "\u221a":
            return shared.Expr("call", name="sqrt", args=(self.atom(),))
        if kind != "name":
            raise NotReadable("'%s' stands where a number or a symbol was expected" % (text or "the end"))
        function = self.functions.get(text) or self.functions.get(shared.normalise_symbol(text))
        skip = self.minus_one_follows() if function else 0
        if skip:
            inverse = self.notation.get("inverse", {}).get(function)
            if not inverse:
                raise NotReadable("the inverse of '%s' is not a function AIVA knows" % text)
            self.position += skip
            function = inverse
        if self.peek() == ("sign", "("):
            if not function:
                raise NotReadable("'%s(' could be a product or a function; AIVA does not guess" % text)
            self.take()
            arguments = [self.statement()]
            while self.peek() == ("sign", ","):
                self.take()
                arguments.append(self.statement())
            self.take(")")
            return shared.Expr("call", name=function, args=tuple(arguments))
        return shared.Expr("sym", name=shared.normalise_symbol(text))

def parse_formula(text, notation, implicit_product=False):
    """Read a formula written in linear notation into AIVA's expression tree. Raises NotReadable
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
    linear = shared.normalise_text(linear)
    if not linear:
        reason = shared.UNDECIDED_REASONS[0] if image_sha256 or source_form == "image" else "no formula text was found"
        return shared.EquationData(source_form, "", False, reason, None, image_sha256)
    try:
        tree = parse_formula(linear, notation, implicit_product=source_form in ("omml", "mathml", "latex"))
    except NotReadable as problem:
        return shared.EquationData(source_form, linear, False, str(problem), None, image_sha256)
    return shared.EquationData(source_form, shared.expr_to_text(tree), True, "", shared.to_plain(tree), image_sha256)

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
        return shared.EquationData("inline", shared.expr_to_text(tree), True, "", shared.to_plain(tree), "")
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
    name = reading.local_name(element.tag)
    def part(child_name):
        child = reading.child_named(element, child_name)
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
        return "(%s)" % ", ".join(math_children(child) for child in element if reading.local_name(child.tag) == "e")
    if name == "func":
        return "%s(%s)" % (part("fname").strip(), strip_outer_brackets(part("e")))
    if name == "nary":
        properties = reading.child_named(element, "narypr")
        sign = reading.child_named(properties, "chr") if properties is not None else None
        kind = NARY_NAMES.get(reading.attribute(sign, "val"), "sum_over") if sign is not None else "integral_over"
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
            elif word in shared.GREEK:
                output.append(shared.GREEK[word])
            elif word in LATEX_WORDS:
                output.append(LATEX_WORDS[word])
            else:
                raise NotReadable("it uses the LaTeX command '\\%s', which AIVA does not read" % word)
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
def detect_format(data):
    """The format of a file from its first bytes, whatever its extension says."""
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n")
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "docx"
    lowered = head.lower()
    if lowered.startswith((b"mime-version:", b"from:", b"content-type:")) or b"multipart/related" in lowered[:1024]:
        return "mhtml"
    if lowered.startswith(b"<"):
        return "html" if re.match(rb"<(!doctype\s+html|html)\b", lowered) else "xml"
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

XML_ENTITIES = ("amp", "lt", "gt", "quot", "apos")

def repair_markup(text, file_name, repairs):
    """The repairs AIVA makes before strict parsing. Each one is recorded with its position, its
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
        text = text[:start] + "<aiva-root>" + text[start:] + "</aiva-root>"
        record("several top elements wrapped in one", start, "%d top elements" % roots, "<aiva-root>")
    return text

VOID_TAGS = ("img", "br", "hr", "meta", "link", "input", "col", "area", "base", "wbr")
BLOCK_STARTS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "div", "li", "tr")
IMPLIED_END = dict({tag: ("p",) for tag in BLOCK_STARTS}, li=("li", "p"), tr=("tr", "td", "th", "p"), td=("td", "th", "p"), th=("td", "th", "p"))

class TolerantReader(html.parser.HTMLParser):
    """Builds the same kind of element tree as the strict XML parser, from start, end and text
    events of the standard library's HTML parser. It forgives what real exports contain: tags
    never closed, tags closed in the wrong order, attributes without quotes. Equation markup
    that Word's web export hides inside conditional comments is read too. (This is the one
    place where AIVA subclasses: the standard parser offers no other way to receive events.)"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.builder, self.open_tags = ElementTree.TreeBuilder(), []
        self.builder.start("aiva-root", {})

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
            self.builder.start("aiva-preserved-equation", {})
            self.feed_inner(preserved.group(1))
            self.builder.end("aiva-preserved-equation")

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
        self.builder.end("aiva-root")
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
def load_tag_rules(references_dir, override_path=None):
    """The default tag rules, with any part replaced by the project's own Inputs/tag_rules.yaml."""
    with open(os.path.join(references_dir, "tag_rules.yaml"), encoding="utf-8") as handle:
        rules = yaml.safe_load(handle)
    if override_path:
        with open(override_path, encoding="utf-8") as handle:
            override = yaml.safe_load(handle) or {}
        for key, value in override.items():
            if key == "families":
                rules["families"].update(value or {})
            else:
                rules[key] = value
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
    "no fine" giving "twiceno"), which is text AIVA made up. Enforces: R13"""
    pieces = [element.text or ""]
    for child in element:
        if rules["family_of"].get(reading.local_name(child.tag)) not in skip:
            if rules["family_of"].get(reading.local_name(child.tag)) in BLOCKS_INSIDE and "".join(pieces).strip():
                pieces.append(" ")
            pieces.append(element_text(child, rules, skip))
        pieces.append(child.tail or "")
    return "".join(pieces)

def new_block(kind, text="", locator="", **more):
    """One block of a document before numbering: kind, text, where it was found, and what its kind needs."""
    block = {"type": kind, "text": shared.normalise_text(text), "locator": locator, "level_hint": None,
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
    name = reading.local_name(element.tag)
    family = state.family(name)
    here = "%s/%s" % (path, name)
    if name == "aiva-preserved-equation":
        state.blocks.append(equation_block(element, here, state))
        state.skip_next_image = True                     # the picture that follows shows the same equation
        return
    if family == "ignore" or not name:
        return
    if family is None:                                   # discovery names every tag it reaches; this is the net under it
        family = "container" if len(element) else "paragraph"
    numbering = reading.written_numbering(element, state.rules)
    if family == "heading":
        text = element_text(element, state.rules)
        digit = re.fullmatch(r"h([1-6])", name)
        state.blocks.append(new_block("heading", text, here, numbering=numbering,
                                      level_hint=int(digit.group(1)) if digit else depth))
    elif family in ("container", "list_container", "inline"):
        # A container that carries its own heading in an attribute (<section name="4. Market">)
        # gives that heading a block of its own, so the chain below it is not lost.
        heading, _ = reading.attribute_text(element, state.rules["heading_attributes"]) if family == "container" else ("", "")
        if heading:
            state.blocks.append(new_block("heading", heading, here, numbering=numbering, level_hint=depth))
        if family == "list_container":                   # <ol>, or <list type="numbered">: its items are counted
            kind = " ".join([name] + [element.get(a) or "" for a in ("type", "style", "numeration", "class")]).lower()
            state.lists.append([bool(re.search(r"\bol\b|order|num|decimal|arabic|alpha|roman", kind)), 0])
        walk_mixed(element, here, depth + (1 if family == "container" else 0), state)
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
        state.blocks.append(figure_block(element, here, state))
    elif family == "equation":
        state.blocks.append(equation_block(element, here, state))
    elif family == "caption" and state.blocks and state.blocks[-1]["type"] in ("figure", "table", "equation"):
        state.blocks[-1]["caption"] = shared.normalise_text(element_text(element, state.rules, skip=()))

def walk_mixed(element, here, depth, state, own_kind=None, numbering="", marker=""):
    """An element that may hold both running text and blocks. Its own text becomes one
    paragraph; a formula that fills the paragraph alone becomes an Equation block instead."""
    block_families = ("heading", "container", "list_container", "paragraph", "list_item", "table",
                      "figure", "equation", "caption", None)
    children = [c for c in element if reading.local_name(c.tag) and
                (state.family(reading.local_name(c.tag)) in block_families or reading.local_name(c.tag) == "aiva-preserved-equation")]
    inline_only = [c for c in children if state.family(reading.local_name(c.tag)) is None and not len(c)
                   and own_kind]
    children = [c for c in children if c not in inline_only]
    text = shared.normalise_text(element_text(element, state.rules, skip=("figure", "equation", "ignore", "caption",
                                 "table", "list_container")) if own_kind or not children else (element.text or ""))
    equations = [c for c in children if state.family(reading.local_name(c.tag)) == "equation"]
    if own_kind and text and equations:                  # text around a formula: show the formula in place
        text = shared.normalise_text(text + " " + " ".join(math_to_linear(c) for c in equations))
        children = [c for c in children if c not in equations]
    if text and (own_kind or not children):
        state.blocks.append(new_block(own_kind or "paragraph", text, here, numbering=numbering, marker=marker))
    for position, child in enumerate(children, start=1):
        if own_kind and state.family(reading.local_name(child.tag)) in ("paragraph", "inline"):
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
    family = lambda node: state.family(reading.local_name(node.tag))
    found = [node for node in element.iter() if family(node) == "row"] or reading.table_rows(element, state.rules)
    rows, captions = [], []
    for node in element.iter():
        part = shared.normalise_text(element_text(node, state.rules, skip=())) if family(node) == "caption" else ""
        if part and part not in captions:
            captions.append(part)
    for row in found:
        cells = [shared.normalise_text(element_text(cell, state.rules, skip=())) for cell in row
                 if reading.local_name(cell.tag) and family(cell) not in ("caption", "ignore")]
        if any(cells):
            rows.append(cells)
    block = table_from_rows(rows, here, ". ".join(captions))
    words = "" if rows else shared.normalise_text(element_text(element, state.rules, skip=("ignore", "caption")))
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
        numeric = values and all(shared.find_numbers(v) and len(shared.find_numbers(v)) == 1 and
                                 len(re.sub(r"[\d.,%\s+-]|bps?|basis points?", "", v)) == 0 for v in values)
        types.append("number" if numeric else "text")
    row_key = header[0] if header and types and types[0] == "text" else ""
    table = shared.TableData(tuple(header), tuple(tuple(row) for row in body), row_key, tuple(types))
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
    caption = next((shared.normalise_text(element_text(n, state.rules, skip=())) for n in element.iter()
                    if state.rules["family_of"].get(reading.local_name(n.tag)) == "caption"), "")
    fingerprint = state.images.get(source) or state.images.get(source.replace("cid:", "")) or ""
    return new_block("figure", label or caption or source, here, caption=caption, image_sha256=fingerprint,
                     source=source)

def equation_block(element, here, state):
    """An equation element: MathML or Office Math is converted; LaTeX or linear text is read as
    written; an equation that is only a picture stays an Equation chunk that could not be read."""
    markup = next((n for n in element.iter() if reading.local_name(n.tag) in ("math", "omath")), None)
    picture = next((n for n in element.iter() if reading.local_name(n.tag) in ("img", "image", "graphic", "imagedata")), None)
    if markup is not None:
        form = "mathml" if reading.local_name(markup.tag) == "math" else "omml"
        equation = read_equation(form, math_to_linear(markup), state.notation)
    elif picture is not None and not shared.normalise_text(element_text(element, state.rules)):
        source = picture.get("src") or picture.get("fileref") or ""
        equation = read_equation("image", "", state.notation, state.images.get(source, "") or shared.sha256_text(source))
    else:
        written = shared.normalise_text(element_text(element, state.rules, skip=("caption", "ignore")))
        try:
            linear = latex_to_linear(written) if "\\" in written else written
            equation = read_equation("latex" if "\\" in written else "inline", linear, state.notation)
        except NotReadable as problem:
            equation = shared.EquationData("latex", written, False, str(problem), None, "")
    label = picture.get("alt") if picture is not None and picture.get("alt") else ""
    text = equation.linear or label or "Equation shown as a picture"
    return new_block("equation", text, here, equation=equation)

def blocks_from_markup(text, file_name, state, repairs, tolerant_only=False):
    """XML or HTML text to blocks: parse (repairing where needed), then walk the tree by the tag rules."""
    root = parse_markup(text, file_name, repairs, tolerant_only)
    state.rules["family_of"].update(reading.discover_families(root, state.rules, state.unknown_tags))
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
            fingerprint = shared.sha256_bytes(payload)
            for key in (part.get("Content-Location", ""), (part.get("Content-ID", "") or "").strip("<>")):
                if key:
                    state.images[key] = fingerprint
                    state.images[key.rsplit("/", 1)[-1]] = fingerprint
    if page is None:
        return [not_read_block(file_name, "the file holds no web page part")]
    return blocks_from_markup(page, file_name, state, repairs, tolerant_only=True)

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
        name = reading.local_name(node.tag)
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
                        if reading.local_name(n.tag) == "docpr"), "")
    fingerprint, words = "", ""
    for node in picture.iter():
        for key, value in node.attrib.items():
            if key.startswith("{%s}" % WORD_NS["r"]) and value in related:
                fingerprint, words = shared.sha256_bytes(related[value]), read_picture(related[value], state)
    fingerprint = fingerprint or shared.sha256_bytes(ElementTree.tostring(picture))
    said = (description or "Picture without a description") + words
    return new_block("figure", said, locator, image_sha256=fingerprint, display=said)

def safe_xml(data):
    """Parse one XML part of an Office file. Any document-type declaration is removed first,
    so no entity can be defined inside the file (no entity expansion, no outside fetch)."""
    text = re.sub(rb"<!DOCTYPE[^>\[]*(\[.*?\])?\s*>", b"", data, flags=re.S | re.I)
    return ElementTree.fromstring(text)

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
    formats, counts, page, on_page = docx_number_formats(archive), {}, 1, {}
    paged = b"lastRenderedPageBreak" in archive.read("word/document.xml")     # Word noted where its pages ended
    for position, element in enumerate(body, start=1):
        locator, name = "body element %d" % position, reading.local_name(element.tag)
        if name == "tbl":
            rows = []
            for row in element.findall("w:tr", WORD_NS):
                rows.append([shared.normalise_text(docx_paragraph_parts(cell)[0]) for cell in row.findall("w:tc", WORD_NS)])
            blocks.append(table_from_rows(rows, locator, pending_caption))
            pending_caption = ""
            continue
        if name != "p":
            continue
        level, numbered, style_name = docx_paragraph_facts(element, styles)
        text, formulas, pictures = docx_paragraph_parts(element)
        text = shared.normalise_text(text)
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
            if numbered and not reading.first_numbering(text, state.rules)[0]:
                counters[level - 1] += 1
                counters[level:] = [0] * (9 - level)
                block["numbering"] = ".".join(str(c) for c in counters[:level] if c)
                block["reconstructed"] = True
            blocks.append(block)
        elif formulas and not shared.normalise_text(re.sub(r"\s+", " ", text.replace(math_to_linear(formulas[0]), ""))):
            equation = read_equation("omml", math_to_linear(formulas[0]), state.notation)
            blocks.append(new_block("equation", equation.linear or text, locator, equation=equation))
        elif text:
            page += sum(1 for node in element.iter() if reading.local_name(node.tag) == "lastrenderedpagebreak")
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
    return blocks

# ---------------------------------------------------------------- .pdf
MATH_CHARACTERS = set("=+\u2212\u00d7\u00f7\u2211\u221a\u222b^/\u2264\u2265\u2248()") | set(shared.GREEK.values())

BULLET = re.compile(r"^(?:[\u2022\u25aa\u25cf\u25e6\u2023\u2043\u2013\u2014*o-]|\(cid:\d+\))\s+(?=\S)")

def pdf_lines(document, file_name):
    """Every line, table and picture of a PDF in reading order, each with its page, its place on
    the page, and whether it sits in the top or bottom margin ("edge")."""
    lines = []
    for number, page in enumerate(document.pages, start=1):
        edge = lambda top, bottom: "top" if bottom < 0.12 * page.height else "bottom" if top > 0.88 * page.height else ""
        tables = page.find_tables()
        for table in tables:
            rows = [[shared.normalise_text(cell or "") for cell in row] for row in table.extract()]
            lines.append({"page": number, "top": table.bbox[1], "table": rows, "edge": ""})
        for count, image in enumerate(page.images, start=1):
            mark = "%s page %d picture %d %s" % (file_name, number, count, image.get("srcsize"))
            lines.append({"page": number, "top": image["top"], "figure": shared.sha256_text(mark), "text": "picture %s" % (image.get("srcsize"),),
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
        lines = reading.without_page_furniture(pdf_lines(document, file_name), len(document.pages), state, file_name)
        sizes = sorted(entry["size"] for entry in lines if "size" in entry)
        body_size = sizes[len(sizes) // 2] if sizes else 10.0
        numbered = any("size" in entry and reading.first_numbering(entry["text"], state.rules)[0] for entry in lines)
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
                reading.first_numbering(text, state.rules)[0] or (len(text.split()) <= 14 and text[-1] not in ".,;:"))
            near = open_block and entry["page"] == open_block["page"] and entry["top"] - open_block["bottom"] < 0.7 * entry["size"]
            over_the_page = open_block and entry["page"] == open_block["page"] + 1 and not title and not bullet \
                and open_block["block"]["type"] != "heading" and open_block["block"]["text"][-1:] not in ".:;?!" and text[:1].islower()
            if title and near and open_block["block"]["type"] == "heading":       # a heading set over two lines
                kind = None
            elif title:
                kind, more = "heading", {"level_hint": None if numbered else -int(round(entry["size"] * 2)) + (0 if entry["size"] > body_size * 1.08 else 1)}
            elif dense > 0.25 and len(text.split()) <= 12:
                kind, more = "equation", {"equation": shared.EquationData("pdf", text, False, shared.UNDECIDED_REASONS[1], None, "")}
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
            text = shared.normalise_text(paragraph)
            if text:
                kind = "heading" if reading.first_numbering(text, state.rules)[0] and len(text) < 100 else "paragraph"
                blocks.append(new_block(kind, text, "page %d" % page_number))
    return blocks

# ---------------------------------------------------------------- levels, references, chunks

def cross_references(text, rules):
    """Cross-references as written: "Table 3", "section 4.2", "Annex A"."""
    labels = "|".join(re.escape(label) for label in rules["cross_reference_labels"])
    found = re.findall(r"\b((?:%s)\s+(?:[A-Z]\b|\d+(?:\.\d+)*[a-z]?|\([a-z0-9]+\)))" % labels, text or "", re.IGNORECASE)
    return tuple(dict.fromkeys(shared.normalise_text(reference) for reference in found))

def states_something_checkable(block, rules):
    """Does a documentation passage state something that can be checked against the methodology
    or the code: a number, a formula, a table, or a phrase from the rules file?"""
    if block["type"] in ("table", "equation"):
        return True
    if block["type"] == "figure" or block["not_read_reason"]:
        return None
    lowered = block["text"].lower()
    return bool(shared.find_numbers(block["text"]) or "=" in lowered or
                any(phrase in lowered for phrase in rules["checkable_phrases"]))

KIND_OF_BLOCK = {"paragraph": "Paragraph", "list_item": "Paragraph", "table": "Table", "figure": "Figure",
                 "equation": "Equation"}
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
    for block in fold_lists(reading.infer_levels(blocks, state.rules)):
        if block["type"] == "heading":
            while levels and levels[-1] >= block["level"]:
                levels.pop()
                chain.pop()
            levels.append(block["level"])
            chain.append(block["text"])
            paragraph_number, section_numbering = 0, block["numbering"]
            reconstructed = block["reconstructed"]
            if reconstructed:
                chain[-1] = "%s %s" % (block["numbering"], block["text"])
            continue
        kind = KIND_OF_BLOCK[block["type"]]
        text = block.get("display") or block["text"]
        if kind == "Paragraph" and not block["not_read_reason"]:
            paragraph_number += 1
        equation = block["equation"]
        if kind == "Paragraph" and equation is None:
            equation = inline_formula(text, state.notation)
        chunks.append(shared.Chunk(
            ref=shared.make_ref(prefix, first_number + len(chunks)), corner=corner, source_file=source_file,
            kind=kind, level=levels[-1] if levels else 0, heading_chain=tuple(chain), numbering=section_numbering,
            para_no=paragraph_number if kind == "Paragraph" and not block["not_read_reason"] else None,
            text=text, locator=block["locator"], content_hash=shared.content_hash(text + block.get("image_sha256", "")),
            table=block["table"], equation=equation, refs_out=cross_references(text + " " + block["caption"], state.rules),
            checkable=states_something_checkable(block, state.rules) if corner == "doc" else None,
            numbering_reconstructed=bool(chain) and block_is_under_reconstructed(blocks, block),
            caption=block["caption"], not_read_reason=block["not_read_reason"],
            para_label=block["numbering"] if kind == "Paragraph" else ""))
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
            return reading.atoms_of_docx(zipfile.ZipFile(io.BytesIO(data)), safe_xml, file_name)
        if found == "pdf":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as document:
                return reading.atoms_of_pdf(document, file_name)
        if found == "mhtml":
            message = email.message_from_bytes(data)
            for part in message.walk():
                payload = part.get_payload(decode=True)
                if part.get_content_type() == "text/html" and payload is not None:
                    text = payload.decode(part.get_content_charset() or "utf-8", "replace")
                    return reading.atoms_of_markup(parse_markup(repair_markup(text, file_name, []), file_name, [], tolerant_only=True), file_name, state.rules)
            return []
        if found in ("xml", "html"):
            text = repair_markup(decode_text(data), file_name, [])
            return reading.atoms_of_markup(parse_markup(text, file_name, [], tolerant_only=found == "html"), file_name, state.rules)
        return reading.atoms_of_plain_text(decode_text(data), file_name)
    except Exception:                          # an account that cannot be drawn is written down, never a stopped run
        state.notes.append("%s: the content account could not be drawn for this file." % file_name)
        return []

def read_file_blocks(path, file_name, state, repairs, max_bytes):
    """One input file to blocks, by the format found in its content. Enforces: R6"""
    if os.path.getsize(path) > max_bytes:
        return "too large", [not_read_block(file_name, "the file is larger than the size limit for one input file")]
    with open(path, "rb") as handle:
        data = handle.read()
    found = detect_format(data)
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
    rules = load_tag_rules(options["references_dir"], options["inputs"].get("tag_rules"))
    notation = load_notation(options["references_dir"])
    chunks, repairs, info_rows, outline, accounts = [], [], [], [], []
    for path in options["inputs"][input_key]:
        file_name = os.path.basename(path)
        state = WalkState(dict(rules, read_pictures=ctx.settings.get("read_pictures", True)), notation, {}, {}, [])
        found, blocks = read_file_blocks(path, file_name, state, repairs, int(ctx.settings["max_file_mb"] * 1024 * 1024))
        new_chunks = blocks_to_chunks(blocks, corner, file_name, len(chunks) + 1, state)
        chunks.extend(new_chunks)
        plain = [shared.to_plain(chunk) for chunk in new_chunks]
        found_account = reading.account(file_name, state.atoms, plain, state.dropped,
                                       reading.marks_of_rendering(plain) + [LIST_MARKER])
        accounts.append(found_account)
        info_rows.extend({"group": label, "item": "%s: content account" % file_name, "value": line}
                         for line in reading.account_lines(found_account))
        counts = {}
        for chunk in new_chunks:
            counts[chunk.kind] = counts.get(chunk.kind, 0) + 1
        summary = ", ".join("%d %s" % (counts[kind], kind.lower() + ("s" if counts[kind] != 1 else ""))
                            for kind in shared.CHUNK_KINDS if kind in counts) or "nothing could be read"
        info_rows.append({"group": label, "item": file_name, "value": "Read as %s: %d units (%s)" % (found, len(new_chunks), summary)})
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
    if unreadable:
        messages.append("%d equation(s) could not be read and will be raised for a person." % unreadable)
    open_accounts = [one for one in accounts if not one["closed"]]
    if open_accounts:
        messages.append("The content account is open on %d file(s); Model_Package_Info says what could not be placed."
                        % len(open_accounts))
    return shared.StepResult({kind: chunks, "read_repairs": repairs, "info_rows": info_rows, "outline": outline,
                              "content_accounts": accounts},
                             {"units": len(chunks), "repairs": len(repairs),
                              "content account open on": len(open_accounts)}, messages)

def read_methodology(ctx):
    """Step 02, skill read-methodology: the canonical methodology into chunks C-0001, C-0002, ..."""
    return read_corner(ctx, "canon", "methodology", "Methodology files")

def read_documentation(ctx):
    """Step 03, skill read-documentation: the model documentation into chunks D-0001, D-0002, ..."""
    return read_corner(ctx, "doc", "documentation", "Documentation files")
