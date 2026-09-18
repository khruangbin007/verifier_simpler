"""
AIVA 0.0.1 - aiva2_package.py - reading the R package without running any of it. For Reviewer 2.

WHAT THIS FILE DOES
  It unpacks the single .tar.gz safely, fingerprints every file in it, and turns the package
  into citable model units: functions, formula statements, top-level statements, test
  blocks, roxygen blocks, help pages, vignette text, stored parameter data, compiled code
  and every other file. R source is read by AIVA's own tokenizer and precedence parser (a
  few hundred plain lines that can be audited; no compiled grammar is needed). Stored data
  is decoded with the pure-Python `rdata` package, which parses and never evaluates.

WHAT IT TAKES IN AND PRODUCES
  In: Inputs/2_Model_Package/<one tarball>, references/r_function_map.yaml, settings.
  Out: model_units, parameter_tables, package_info and info_rows records.

WHICH SHEETS SHOW ITS RESULTS
  Chunks_Model (one row per unit), the first columns of Mapping_Model_to_Canon_and_Doc,
  and the package lines on Model_Package_Info.

DESIGN RULES ENFORCED HERE (function names in brackets)
  R2  no file and no line is lost: a file or expression that cannot be read becomes a unit
      of kind "File not read" with a plain reason      [units_from_r_source, read_package]
  R5  same tarball, same units in the same order       [read_package sorts the inventory]
  R6  the tarball is only read; it is unpacked in memory, member by member, refusing
      absolute paths, parent-directory escapes, links and oversized members [unpack_package]
  R7  nothing from the package is executed: code is parsed, data is decoded, example code
      is parsed only                                   [parse_r_source, decode_data_file]

HOW TO SANITY-CHECK IT
  Run `python -m unittest engine/tests/test_aiva2_package.py`. In the notebook run the
  appendix cell "Reviewer 2 sanity check", then open Output.xlsx, sheet Chunks_Model: every
  function of the package has a row of kind Function, formula statements show their
  expression in "Expression / arguments", "Numbers used" lists the numbers written in the
  code, and Model_Package_Info shows "Parser: AIVA R reader 0.0.1".
"""
import bz2
import csv
import io
import lzma
import os
import re
import tarfile
import zlib
from dataclasses import dataclass, field

import yaml

import aiva0_shared as shared
import aiva0r_reading
import aiva1_documents

SKILL_VERSIONS = {"read-package": "0.0.2"}
TEXT_MEMBERS = (".r", ".txt", ".md", ".rd", ".rmd", ".csv", ".tsv", ".yaml", ".yml", ".json", ".html")
PARSER_NAME = "AIVA R reader 0.0.1"

class NotParsed(Exception):
    """One R expression that AIVA's reader could not read. The message is a plain reason."""

# ---------------------------------------------------------------- safe unpacking and inventory
def unpack_package(tar_path, max_member_bytes):
    """Read the tarball member by member, into memory, never onto disk by path. A member with
    an absolute path, a path that climbs out with "..", a link, or a size over the cap is
    refused and reported; everything else is returned as {path: bytes}. Enforces: R6"""
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
            raise NotParsed("line %d holds the character '%s', which AIVA's R reader does not know"
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
    parsed = shared.parse_number(text) or {"value": text, "as_written": text, "decimals": 0, "unit": ""}
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
    """One R expression to AIVA's neutral formula tree, through r_function_map.yaml. `known`
    holds local variables already assigned in the same function: they are substituted, so a
    change three lines above the return still reaches the comparison. Anything AIVA cannot
    evaluate raises CannotConvert; nothing is guessed and nothing is run. Enforces: R7"""
    kind = node.kind
    if kind == "num":
        return shared.Expr("num", value=number_token(node)["value"])
    if kind == "name":
        if node.value in known:
            return known[node.value]
        if node.value in CONSTANT_NAMES:
            raise CannotConvert("it uses the constant %s" % node.value)
        return shared.Expr("sym", name=shared.normalise_symbol(node.value))
    if kind == "paren" or (kind == "block" and len(node.args) == 1):
        return to_expr(node.args[0], function_map, known)
    if kind == "unary" and node.value in ("-", "+"):
        inner = to_expr(node.args[0], function_map, known)
        return shared.Expr("neg", args=(inner,)) if node.value == "-" else inner
    if kind == "binary" and node.value in SIGN_TO_OP:
        return shared.Expr(SIGN_TO_OP[node.value], args=tuple(to_expr(arg, function_map, known) for arg in node.args))
    if kind == "binary" and node.value in COMPARISON_SIGNS:
        return shared.Expr("cmp", name=node.value, args=tuple(to_expr(arg, function_map, known) for arg in node.args))
    if kind == "if" and len(node.args) == 3:
        return shared.Expr("piecewise", args=tuple(to_expr(arg, function_map, known) for arg in node.args))
    if kind == "dollar" and node.args[0].kind == "name":
        return shared.Expr("sym", name="%s$%s" % (node.args[0].value, node.args[1].value))
    if kind == "index" and node.args[0].kind == "name" and node.args[-1].kind == "str" and len(node.args) == 3:
        return shared.Expr("sym", name="%s$%s" % (node.args[0].value, node.args[-1].value))   # table[rows, "column"]
    if kind == "call":
        return call_to_expr(node, function_map, known)
    raise CannotConvert("it uses '%s', which AIVA cannot turn into a formula" % unparse(node)[:40])

def call_to_expr(node, function_map, known):
    """A call in R to the neutral expression tree, through r_function_map.yaml; anything else cannot be converted."""
    name = callee_name(node)
    if name == "return" and len(node.args) == 2:
        return to_expr(node.args[1], function_map, known)
    entry = function_map["r_functions"].get(name)
    if entry is None:
        raise CannotConvert("it calls %s(), which AIVA cannot evaluate" % (name or "a computed function"))
    expected = entry.get("arguments", [])
    placed, extra = {}, []
    for argument_name, argument in zip(node.names, node.args[1:]):
        if argument_name == "na.rm" or argument.kind == "missing":
            continue
        if argument_name in entry.get("only_defaults", []) or (argument_name and argument_name not in expected):
            raise CannotConvert("it calls %s() with '%s', which AIVA does not evaluate" % (name, argument_name))
        if argument_name:
            placed[expected.index(argument_name)] = argument
        else:
            extra.append(argument)
    ordered = []
    for position in range(len(placed) + len(extra)):
        ordered.append(placed[position] if position in placed else extra.pop(0))
    enough = len(expected) - entry.get("optional", 0) <= len(ordered) <= len(expected)
    if not entry.get("variadic") and not enough:
        raise CannotConvert("it calls %s() with %d argument(s) where AIVA knows it with %d"
                            % (name, len(ordered), len(expected)))
    return shared.Expr("call", name=entry["neutral"], args=tuple(to_expr(arg, function_map, known) for arg in ordered))

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
    assignments are substituted in order. Branches that assign, loops and anything AIVA
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
            raise CannotConvert("it has steps that AIVA cannot follow in a straight line")
    if result is None:
        raise CannotConvert("it returns nothing that AIVA can follow")
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
                detail[form] = shared.to_plain(shared.Expr("eq", args=(shared.Expr("sym", name=shared.normalise_symbol(target)), tree)))
            except CannotConvert as problem:
                detail["not_composed_reason"] = str(problem)
        lines = (statement.line, statement.end_line)
        units.append(draft(shared.KIND_FORMULA, path, lines, target, "\n".join(source_lines[lines[0] - 1:lines[1]]),
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
        detail["composed"] = shared.to_plain(shared.Expr("eq", args=(shared.Expr("sym", name=shared.normalise_symbol(name)), tree)))
    except CannotConvert as problem:
        detail["not_composed_reason"] = str(problem)
    computes = any(has_arithmetic(part, function_map, context["trivial"]) for part in function_node.args if part.kind != "missing")
    if not computes:                                     # the body AND the defaults: a non-trivial default is never "supporting"
        detail.update(plumbing=True, plumbing_reason="no arithmetic and no number other than the trivial ones: it only "
                                                     "checks, converts or passes values on")
    unit = draft(shared.KIND_FUNCTION, path, lines, name, "\n".join(source_lines[lines[0] - 1:lines[1]]),
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
        return [draft(shared.KIND_TEST, path, lines, label, text, code=code_detail(node, function_map, context["settings"]), node=node)]
    detail = code_detail(node, function_map, context["settings"])
    if parts and parts[0].kind == "name" and has_arithmetic(parts[1], function_map, context["trivial"]):
        try:
            tree = to_expr(parts[1], function_map, {})
            detail["expression"] = shared.to_plain(shared.Expr("eq", args=(shared.Expr("sym", name=shared.normalise_symbol(parts[0].value)), tree)))
        except CannotConvert as problem:
            detail["not_composed_reason"] = str(problem)
        return [draft(shared.KIND_FORMULA, path, lines, parts[0].value, text, code=detail, node=node)]
    kind = shared.KIND_TEST if in_tests and node.kind == "call" and callee_name(node).startswith("expect_") else shared.KIND_TOPLEVEL
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
            units.append(draft(shared.KIND_NOT_READ, path, (first, last), "", "\n".join(source_lines[first - 1:last]),
                               read_problem="AIVA's R reader could not read this expression: %s" % reason))
        else:
            units.extend(statement_units(result, path, source_lines, context, in_tests))
    units.extend(roxygen_units(path, source_lines, parsed, context))
    units.sort(key=lambda unit: (unit["lines"][0], 0 if unit["kind"] == shared.KIND_ROXYGEN else 1, unit["lines"][1] * -1))
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
        units.append(draft(shared.KIND_TOPLEVEL, path, (1, len(source_lines)), "", source, code=None))
    for unit in units:
        if unit["parent_key"] is None or unit["kind"] == shared.KIND_FUNCTION:
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
                equation = aiva1_documents.read_equation("latex", aiva1_documents.latex_to_linear(latex), context["notation"])
            except aiva1_documents.NotReadable as problem:
                equation = shared.EquationData("latex", latex, False, str(problem), None, "")
            formulas.append(dict(shared.to_plain(equation), line=first + 1 + text[:found.start()].count("\n")))
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
        units.append(draft(shared.KIND_ROXYGEN, path, (first + 1, number), documents, "\n".join(source_lines[first:number]),
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
    first = lambda macro: next((shared.normalise_text(content) for name, content in sections if name == macro), "")
    arguments = []
    for name, content in sections:
        if name == "arguments":
            for item in re.finditer(r"\\item\s*(?=\{)", content):
                argument, after = braces_content(content, item.end())
                description, _ = braces_content(content, after) if content[after:after + 1] == "{" else ("", after)
                arguments.append((shared.normalise_text(argument), shared.normalise_text(description)))
    detail = {"rd_name": first("name"), "aliases": tuple(shared.normalise_text(c) for n, c in sections if n == "alias"),
              "title": first("title"), "usage": first("usage"), "arguments": tuple(arguments),
              "generated_from_ref": None, "in_step_with_source": None,
              "generated_from_file": generated_from.group(1) if generated_from else ""}
    return draft(shared.KIND_HELP, path, (1, text.count("\n") + 1), detail["rd_name"] or os.path.basename(path), text, helppage=detail)

def vignette_units(path, text, context):
    """A vignette: prose becomes "Vignette text" units, one per stretch between code chunks;
    code chunks are read as R code (and never run)."""
    units, lines, prose_start, number = [], text.split("\n"), 0, 0
    def close_prose(end):
        prose = "\n".join(lines[prose_start:end]).strip()
        if prose:
            units.append(draft(shared.KIND_VIGNETTE, path, (prose_start + 1, end), "", prose))
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
        return shared.plain_decimal(shared.Decimal(repr(number)))
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
        return draft(shared.KIND_OBJECT, path, None, name, described, data=detail), None
    header, rows, shape = found
    kinds = [column_kind([row[i] for row in rows]) for i in range(len(header))]
    n_cells = len(rows) * len(header)
    value_hash = shared.sha256_text("\x1f".join(header + [cell for row in rows for cell in row]))
    too_large = n_cells > settings["max_parameter_cells"] or len(header) > settings["max_parameter_columns"]
    reason = "too large to be a parameter table (%d cells); it looks like a dataset" % n_cells if too_large else None
    keys = row_key_columns(header, rows, kinds)
    detail = {"object_name": name, "container_file": path, "r_class": (shape,), "r_type": shape,
              "dims": (len(rows), len(header)), "attributes": {}, "columns": tuple(zip(header, kinds)), "row_keys": keys,
              "n_cells": n_cells, "canonical_value_hash": value_hash, "decoded_by": decoded_by,
              "assessable": not too_large, "not_assessable_reason": reason}
    kind = shared.KIND_OBJECT if shape == "list" else shared.KIND_TABLE
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
        table = [row for row in csv.reader(io.StringIO(aiva1_documents.decode_text(data)), delimiter=delimiter) if row]
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
        unit = draft(shared.KIND_NOT_READ, path, None, stem, "", read_problem="This data file was not read: %s." % reason)
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
    """Does this path name a stored-data file that AIVA decodes?"""
    lowered = path.lower()
    if lowered.endswith(DATA_EXTENSIONS):
        return True
    return lowered.endswith((".csv", ".tsv")) and lowered.split("/")[0] in ("data", "inst")

def is_parsed_r_file(path):
    """Is this an R source file in a folder whose code AIVA parses?"""
    return path.lower().endswith(".r") and path.lower().split("/")[0] in ("r", "tests", "data", "inst", "data-raw", "demo")

def file_units(path, data, context, facts):
    """The units of one file of the package, by where it lies and what it is."""
    lowered = path.lower()
    if is_data_file(path):
        units, tables, fact = decode_data_file(path, data, context["settings"])
        context["tables"].extend(tables)
        facts["data"].append(fact)
        return units
    if lowered.startswith("src/"):
        return [draft(shared.KIND_COMPILED, path, None, os.path.basename(path), "",
                      read_problem="Compiled code is not read by AIVA; it needs a manual review.")]
    text = aiva1_documents.decode_text(data) if b"\x00" not in data[:4096] else None
    if text is None:
        return [draft(shared.KIND_NOT_READ, path, None, os.path.basename(path), "",
                      read_problem="A binary file of a kind AIVA does not know; it needs a manual review.")]
    if is_parsed_r_file(path):
        return units_from_r_source(path, text, context)
    if lowered.endswith(".rd") and lowered.startswith("man/"):
        return [help_page_unit(path, text)]
    if lowered.endswith((".rmd", ".rnw", ".qmd")):
        return vignette_units(path, text, context)
    return [draft(shared.KIND_OTHER, path, (1, text.count("\n") + 1), os.path.basename(path), text[:2000])]

def link_documentation_units(units):
    """Tie each roxygen block to the object it documents and each help page to the block that
    generated it (by name and aliases), and say whether the page is still in step with it."""
    by_name = {}
    for unit in units:
        if unit["kind"] in (shared.KIND_FUNCTION, shared.KIND_TABLE, shared.KIND_OBJECT) and not unit["inside"]:
            by_name.setdefault(unit["name"], unit)
    blocks = {}
    for unit in units:
        if unit["kind"] == shared.KIND_ROXYGEN:
            target = by_name.get(unit["roxygen"]["documents_name"])
            unit["roxygen"]["documents_ref"] = target["key"] if target else None
            blocks.setdefault(unit["roxygen"]["documents_name"], unit)
    for unit in units:
        if unit["kind"] == shared.KIND_HELP:
            page = unit["helppage"]
            block = next((blocks[name] for name in (page["rd_name"],) + tuple(page["aliases"]) if name in blocks), None)
            if block is not None:
                page["generated_from_ref"] = block["key"]
                parameters = [tag["name"] for tag in block["roxygen"]["tags"] if tag["tag"] == "param"]
                documented = [name for names in parameters for name in names.split(",")]
                page["in_step_with_source"] = sorted(documented) == sorted(name for a, _ in page["arguments"] for name in a.split(", "))

def finalise_units(drafts, file_hashes):
    """Give every draft its reference, in reading order, and turn keys into references."""
    refs = {unit["key"]: shared.make_ref("M", number) for number, unit in enumerate(drafts, start=1)}
    units = []
    for unit in drafts:
        for part, field_name in (("roxygen", "documents_ref"), ("helppage", "generated_from_ref")):
            if unit[part] and unit[part][field_name]:
                unit[part][field_name] = refs.get(unit[part][field_name])
        helppage = dict(unit["helppage"]) if unit["helppage"] else None
        if helppage:
            helppage.pop("generated_from_file", None)
        units.append(shared.ModelUnit(
            ref=refs[unit["key"]], kind=unit["kind"], file=unit["file"], lines=unit["lines"], name=unit["name"],
            inside=unit["inside"], text=unit["text"], parent_ref=refs.get(unit["parent_key"]),
            file_sha256=file_hashes[unit["file"]], content_hash=shared.content_hash(unit["text"]),
            code=shared.CodeDetail(**unit["code"]) if unit["code"] else None,
            data=shared.ParameterDataDetail(**unit["data"]) if unit["data"] else None,
            roxygen=shared.RoxygenDetail(**unit["roxygen"]) if unit["roxygen"] else None,
            helppage=shared.HelpPageDetail(**helppage) if helppage else None, read_problem=unit["read_problem"]))
    return units, refs

def package_rows(description, namespace, units, facts, refused):
    """The package lines of Model_Package_Info."""
    rows = [("Package", "Name", description.get("Package", "not stated")),
            ("Package", "Version", description.get("Version", "not stated")),
            ("Package", "Title", description.get("Title", "")), ("Package", "Parser", PARSER_NAME)]
    counts = {}
    for unit in units:
        counts[unit.kind] = counts.get(unit.kind, 0) + 1
    rows.extend(("Package", "Units of kind %s" % kind, counts[kind]) for kind in shared.UNIT_KINDS if kind in counts)
    exported = sorted(u.name for u in units if u.kind == shared.KIND_FUNCTION and u.code and u.code.exported)
    rows.append(("Package", "Exported functions", ", ".join(exported) or "none found"))
    rows.extend(("Package data", "Data file", fact) for fact in facts["data"])
    rows.extend(("Package data", "Not assessed", "%s (%s): %s" % (u.ref, u.name, u.data.not_assessable_reason))
                for u in units if u.data and not u.data.assessable)
    rows.extend(("Package", "Could not be read", "%s %s lines %s" % (u.ref, u.file, "-".join(str(n) for n in u.lines or ())))
                for u in units if u.kind == shared.KIND_NOT_READ)
    rows.extend(("Package", "Member of the tarball refused", "%s: %s" % entry) for entry in refused)
    return [{"group": group, "item": item, "value": value} for group, item, value in rows if value != ""]

def read_package(ctx):
    """Step 04, skill read-package. Files are taken in a fixed order (DESCRIPTION, NAMESPACE, R/,
    data, man/, tests/, vignettes/, the rest; by name inside each), so references are stable
    for an unchanged tarball. Enforces: R2, R5"""
    tarballs = ctx.options["inputs"]["package"]
    if not tarballs:
        return shared.StepResult({}, {"units": 0}, ["No package tarball was found in Inputs/2_Model_Package."])
    files, refused = unpack_package(tarballs[0], int(ctx.settings["max_file_mb"] * 1024 * 1024))
    files = strip_top_folder(files)
    with open(os.path.join(ctx.options["references_dir"], "r_function_map.yaml"), encoding="utf-8") as handle:
        function_map = yaml.safe_load(handle)
    description = read_description(aiva1_documents.decode_text(files["DESCRIPTION"])) if "DESCRIPTION" in files else {}
    namespace = read_namespace(aiva1_documents.decode_text(files["NAMESPACE"])) if "NAMESPACE" in files else None
    context = {"function_map": function_map, "notation": function_map["notation"], "namespace": namespace,
               "trivial": set(ctx.settings["trivial_numbers"]), "settings": ctx.settings, "tables": []}
    order = ("description", "namespace", "r", "data", "inst", "man", "tests", "vignettes")
    def rank(path):
        top = path.split("/")[0].lower()
        return (order.index(top) if top in order else len(order), path)
    drafts, facts = [], {"data": []}
    for path in sorted(files, key=rank):
        drafts.extend(file_units(path, files[path], context, facts))
    data_names = {unit["name"] for unit in drafts if unit["data"]}
    data_files = {}
    for unit in drafts:
        if unit["data"]:
            data_files.setdefault(os.path.splitext(os.path.basename(unit["file"]))[0], []).append(unit["name"])
    for unit in drafts:
        if unit["kind"] == shared.KIND_FUNCTION:
            formals = [name for name, _ in unit["code"]["formals"]]
            unit["code"]["reads_data"] = data_reads(unit["node"], formals, data_names, data_files)
    link_documentation_units(drafts)
    hashes = {path: shared.sha256_bytes(data) for path, data in files.items()}
    units, refs = finalise_units(drafts, hashes)
    tables = []
    for unit in units:
        if unit.data and unit.data.assessable:
            values = next(t for t in context["tables"] if t["object_name"] == unit.name)
            tables.append(dict(values, unit_ref=unit.ref))
    inventory = [{"file": path, "bytes": len(files[path]), "sha256": hashes[path], "swhid": shared.swhid_content(files[path])}
                 for path in sorted(files)]
    for entry in inventory:                              # for identity part 3: the lines that must lie inside a unit
        if is_parsed_r_file(entry["file"]):
            lines = aiva1_documents.decode_text(files[entry["file"]]).split("\n")
            entry["nonblank_lines"] = [number for number, line in enumerate(lines, start=1) if line.strip()]
    info = {"name": description.get("Package", ""), "version": description.get("Version", ""), "parser": PARSER_NAME,
            "tarball": os.path.basename(tarballs[0]), "files": inventory,
            "rows": package_rows(description, namespace, units, facts, refused)}
    messages = ["%d units read from %d files of the package." % (len(units), len(files))]
    if len(tarballs) > 1:
        messages.append("More than one tarball was found; only %s was read." % os.path.basename(tarballs[0]))
    plain_units = [shared.to_plain(unit) for unit in units]
    account = aiva0r_reading.account_of_package(files, plain_units, refused, lambda path: is_parsed_r_file(path) or os.path.splitext(path)[1].lower() in TEXT_MEMBERS or "/" not in path)
    info["rows"].extend({"group": "The package", "item": "content account", "value": line}
                        for line in aiva0r_reading.account_lines(account))
    if not account["closed"]:
        messages.append("The content account of the package is open; Model_Package_Info says what could not be placed.")
    return shared.StepResult({"model_units": units, "parameter_tables": tables, "package_info": [info],
                              "content_accounts": [account]},
                             {"units": len(units), "files": len(files), "members refused": len(refused)}, messages)
