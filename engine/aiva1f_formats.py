"""
AIVA 0.0.2 - aiva1f_formats.py - the front door of reading. What a file is, how its bytes
become text, which files in an Inputs folder are documents at all, and how a format AIVA has no
reader of its own for becomes markup that the walker in aiva1_documents already reads.
For Reviewer 1.

WHAT THIS FILE DOES
  It decides, before any reader runs, what a file is - from its content, never from its name
  alone. A ZIP archive is looked inside: a Word file, a spreadsheet, a slide deck, an
  OpenDocument file and an e-book all begin with the same four bytes, and until 0.0.2 every one
  of them was sent to the Word reader, failed, and closed its content account on a file whose
  whole content had been lost. It refuses, in plain words and with a next step, a format AIVA
  cannot read, rather than decoding its bytes as if they were text. It lists the files of an
  Inputs folder, walking into folders and leaving out what an operating system or an editor
  leaves behind, and says what it left out. And it turns Markdown, delimited rows, a
  spreadsheet, RTF and LaTeX into plain markup (h1..h4, p, ul, li, table, tr, th, td), so that
  headings, lists and tables are read by the same walker, the same rules and the same content
  account as every other document.

WHAT IT TAKES IN AND PRODUCES
  In: the bytes of a file and its name; the path of an Inputs folder.
  Out: the name of a format; text; a reason in plain words for a format AIVA does not read; the
  documents of a folder and the files it left out with why; markup, together with the words of
  the file with its markup syntax removed, which is what the content account counts.

WHICH SHEETS SHOW ITS RESULTS
  Chunks_Canon and Chunks_Doc, through aiva1_documents; Model_Package_Info, where a file that
  was not read, a file that was left out of a folder and the format each file was read as are
  listed.

DESIGN RULES ENFORCED HERE
  R2  a file that cannot be read is never a stopped run and never a silence: it is named, with
      a reason and a next step.
  R6  the format comes from the content; a name is a hint only where content cannot decide.
  R7  nothing in a file is executed; a spreadsheet's formulas are read as their stored values.
  R11 it imports aiva0_shared and aiva0r_reading only, and sits directly below the readers.
  R13 a converted file is counted from its own words, with its markup syntax taken away by a
      rule named here, so the account still sees the walker lose or add a word.

HOW TO SANITY-CHECK IT
  Run tests/test_formats.py: every format in the review of 18 September 2026 is fed in, and each
  is either read with its structure or refused in plain words. Drop a folder, a Word lock file
  and a saved web page's support folder into an Inputs corner and check Model_Package_Info.
"""

import csv
import io
import os
import re
import zipfile
from xml.sax.saxutils import escape

import aiva0_shared as shared                       # noqa: F401  (kept for the import-direction test)
import aiva0r_reading as reading                    # noqa: F401

# ---------------------------------------------------------------- what a file is
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
IMAGE_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*", b"RIFF")
MARKDOWN_NAMES = (".md", ".markdown", ".mdown", ".mkd")
DELIMITED_NAMES = (".csv", ".tsv", ".tab")
LATEX_NAMES = (".tex", ".ltx")

# A format AIVA does not read, what it is in plain words, and what to do about it.
NOT_READ = {
    "pptx": "a slide deck, which AIVA does not read; save it as PDF and put the PDF in its place",
    "odf": "an OpenDocument file, which AIVA does not read; save it as .docx and put that in its place",
    "epub": "an e-book, which AIVA does not read; save it as PDF and put the PDF in its place",
    "zip": "an archive of other files; unpack it into the folder so that each file is read on its own",
    "gzip": "a compressed file; unpack it into the folder so that the file inside it is read",
    "ole": "in an old Microsoft Office format (.doc, .xls or .ppt), which AIVA does not read; "
           "save it as .docx, .xlsx or PDF and put that in its place",
    "image": "a picture, and AIVA does not read words from a picture on its own; if it holds text, "
             "save it as a PDF with a text layer",
    "binary": "binary data rather than a document",
}

# The name a format goes by in what the analyst reads.
FORMAT_NAMES = {"pdf": "PDF", "docx": "Word", "xlsx": "spreadsheet", "mhtml": "web archive", "html": "web page",
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
    lowered = head.lower()
    if lowered.startswith((b"mime-version:", b"from:", b"content-type:")) or b"multipart/related" in lowered[:1024]:
        return "mhtml"
    if lowered.startswith(b"<"):
        return "html" if re.match(rb"<(!doctype\s+html|html)\b", lowered) else "xml"
    name = file_name.lower()
    sample = decode_text(data[:16384])
    if name.endswith(LATEX_NAMES) and re.search(r"\\[a-zA-Z]+", sample) or re.search(r"\\documentclass|\\begin\{document\}", sample):
        return "latex"
    if name.endswith(MARKDOWN_NAMES) or len(re.findall(r"(?m)^#{1,6} \S", sample)) >= 2:
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

# ---------------------------------------------------------------- formats AIVA reads by converting them
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

def markdown_to_markup(text):
    """Markdown as markup: # headings, paragraphs, lists, tables, fenced code and quotations."""
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
    for line in text.split("\n"):
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

def converted(found, data, file_name):
    """A file in a format read by converting it: (markup, words, what was done, in plain words)."""
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

CONVERTED = ("xlsx", "markdown", "delimited", "latex", "rtf")

def reason_for(problem):
    """Why a reader failed on a file, in words an analyst can act on. Enforces: R2"""
    name, said = type(problem).__name__, str(problem).lower()
    if isinstance(problem, IsADirectoryError):
        return "it is a folder, not a file"
    if isinstance(problem, PermissionError):
        return "AIVA is not allowed to open it; check who may read the file"
    if "password" in said or "encrypt" in said or "decrypt" in said or "pdfminer" in name.lower():
        return "it is protected by a password; save an unprotected copy and put that in its place"
    if isinstance(problem, zipfile.BadZipFile) or name in ("ReadError", "CompressionError", "HeaderError", "EOFError"):
        return "it is damaged, or is not the archive its name says; save it again and put the new copy in its place"
    return "a reader failed on it (%s); the rest of the run went on without it" % name
