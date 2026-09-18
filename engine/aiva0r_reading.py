"""
AIVA 0.0.2 - aiva0r_reading.py - the reading floor. Shared machinery that the reading steps and
the mapping steps both stand on. For Reviewer 1 and Reviewer 3.

WHAT THIS FILE DOES
  It holds the two bodies of code that had to move down the import order before the reading
  steps could be guided at all (plan 0.0.2, R0):
    - the generic asking machinery - a prompt template, a token estimate from characters, the
      budget the cap leaves, a cut that keeps the words that matter, the last balanced JSON
      object in a reply, and strict parsing that repairs nothing. It sat in aiva3_mapping,
      which is ABOVE aiva1_documents and aiva2_package, so steps 02 to 04 could not reach it;
    - the BASELINE slicing decisions - which tag belongs to which family, which shape is
      really a table, what level a heading sits at, and which lines a page carries only
      because it is a page. These are what AIVA does with no model at all: what a rejected or
      absent answer falls back to, and what a guided reading is measured against.
  Nothing here changed when it moved.

WHAT IT TAKES IN AND PRODUCES
  In: a prompt template from references/prompts; the tag rules; a parsed document element or
  a list of page lines; a reply from the model as text.
  Out: a prompt in its three parts; a token count and a budget; a cut text; a parsed answer or
  a refusal; a family for each tag with the reason in plain words; a level on each heading; the
  page lines with their furniture left out and a note saying what was left out and why.

WHICH SHEETS SHOW ITS RESULTS
  None directly. What it decides reaches Chunks_Canon, Chunks_Doc and Chunks_Model through
  aiva1_documents and aiva2_package, and Model_Package_Info through their reading notes.

DESIGN RULES ENFORCED HERE
  R2  nothing is left out of a document unseen: furniture that is dropped is named and counted.
  R3  a reply is parsed strictly and never repaired, so a malformed answer is refused.
  R7  a reply is read as data only: no evaluation of text, and a repeated key is refused.
  R11 it imports aiva0_shared and nothing else in the engine, so it sits directly above the
      contracts and below every step.

HOW TO SANITY-CHECK IT
  Run tests/test_layout_rules.py: it proves the import direction and the line budget.
  Run tests/test_frozen_interface.py: it proves that moving this code here changed no unit of
  any sample project - every field of every record is the one main produced.
  Read discover_families on a document with an unfamiliar schema and check that every decision
  it records carries a reason a person can read on Model_Package_Info.
"""

import json
import os
import re

import aiva0_shared as shared                       # noqa: F401  (kept for the import-direction test)

# ---------------------------------------------------------------- prompt machinery (from aiva3_mapping)

def load_prompt(references_dir, question_type):
    """A prompt template: its version line, its SYSTEM part and its MAIN part with slots."""
    with open(os.path.join(references_dir, "prompts", question_type + ".txt"), encoding="utf-8") as handle:
        text = handle.read()
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

# ---------------------------------------------------------------- answer machinery (from aiva3_mapping)
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

# ---------------------------------------------------------------- element helpers (from aiva1_documents)
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

# ---------------------------------------------------------------- baseline slicing (from aiva1_documents)
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
    (num="36." gives "36."): more faithful than any count AIVA could make, skipped numbers included."""
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
    way the tag behaves here. The rules always win, so a schema AIVA already knows is read
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
    for edge, text in sorted(furniture):
        state.notes.append("%s: left out as a page header or footer, because it repeats in the %s margin of %d of %d pages: '%s'"
                           % (file_name, edge, len(on_pages[(edge, text)]), pages, text))
    return [entry for entry in lines if not (entry["edge"] and "text" in entry and same(entry) in furniture)]
