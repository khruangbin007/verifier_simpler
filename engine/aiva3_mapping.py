"""
AIVA 0.0.1 - aiva3_mapping.py - the graph, the search for related passages, and the AI judge. For Reviewer 3.

WHAT THIS FILE DOES
  1. It records everything the readers found as a graph (nodes and typed edges) in an
     append-only, hash-chained ledger, and offers a small path finder over it.
  2. For every unit it proposes a shortlist of passages in the other corners. This search
     is fully deterministic, its job is recall, and every proposal carries a plain reason.
  3. It builds the questions for the AI judge, validates every answer in code (letters,
     verbatim quotations, planted control passages) and turns accepted answers into
     `corresponds` edges. A rejected answer never becomes a link.

WHAT IT TAKES IN AND PRODUCES
  In: chunks_canon, chunks_doc, model_units, parameter_tables; references/stopwords.txt,
  bridge_patterns.yaml, r_function_map.yaml, prompts/; optional Inputs/glossary.xlsx.
  Out: graph_ledger, bridge_vocabulary, unresolved_references, candidates, search_records,
  judgement_problems, doc_judgements, second_opinions.

WHICH SHEETS SHOW ITS RESULTS
  Both mapping sheets: the reference, relation, "How established" and "What was searched"
  columns; "Why not mapped" for rows without a link.

DESIGN RULES ENFORCED HERE (function names in brackets)
  R2  closed accounting: every searched unit gets a search record, also when nothing was
      proposed                                                               [find_candidates]
  R3  the model's opinion is never the last word: validate_answer decides what is usable,
      and a rejected answer leaves the unit without a link                   [validate_answer]
  R4  every link says how it was established and carries provenance; the ledger is
      append-only and hash-chained, and no function changes or removes a record
                                                                  [judge_links, ledger_records]
  R5  same input, same output: fixed orders, hash-derived letter order, no random choices
                                                                  [fuse, assemble_question]
  R9  no domain concept: word lists live in references/                      [load_word_lists]

HOW TO SANITY-CHECK IT
  Run `python -m unittest engine/tests/test_aiva3_mapping.py`. In the notebook run the
  appendix cell "Reviewer 3 sanity check" (steps 01 to 07 on sample A_minimal with the
  stand-in chat), then open Output.xlsx, sheet Mapping_Model_to_Canon_and_Doc: the row of
  function dim_weight shows a Canon ref, "What was searched (canon)" lists its words,
  symbols and numbers, and "How established (canon)" starts with "AI judgement" and gives
  the proposal reason.
"""
import hashlib
import json
import math
import os
import re

import yaml

import aiva0_shared as shared
import aiva0r_reading as reading
import aiva1_documents

SKILL_VERSIONS = {"build-graph": "0.0.1", "find-candidates": "0.0.1", "judge-links": "0.0.1", "interpret-code": "0.0.1"}
LEDGER_VOLATILE = ("created_at", "run_id")
CORNER_NAMES = {"canon": "the methodology", "doc": "the documentation", "model": "the package"}

# ---------------------------------------------------------------- the ledger and the graph in memory
def node_record(ref, node_kind, corner):
    """The ledger record of one node."""
    return {"record_type": "node", "ref": ref, "node_kind": node_kind, "corner": corner}

def ledger_records(existing, new_records):
    """Chain new records onto the ledger. Nodes come first (by reference), then edges sorted
    by source, target and kind, never in the order threads finished, so the same content
    always gives the same graph version id. There is no function that edits or removes a
    record: a later contradiction is a NEW edge. Enforces: R4, R5"""
    plain = [shared.to_plain(record) for record in new_records]
    nodes = sorted((r for r in plain if r["record_type"] == "node"), key=lambda r: r["ref"])
    edges = sorted((r for r in plain if r["record_type"] == "edge"),
                   key=lambda r: (r["source"], r["target"], r["kind"], r.get("relation", ""), r.get("how", "")))
    return shared.chain_records(shared.chain_head(existing), nodes + edges, LEDGER_VOLATILE)

def verify_ledger(records):
    """True when no record of the ledger was edited, removed or re-ordered."""
    return shared.verify_chain(records, LEDGER_VOLATILE)

def graph_version_id(records):
    """G- and the first twelve characters of the ledger's head hash."""
    return "G-" + shared.chain_head(records)[:12]

def load_graph(records):
    """The ledger as two adjacency dictionaries: outgoing and incoming edges per node."""
    graph = {"nodes": {}, "out": {}, "in": {}}
    for record in records:
        if record["record_type"] == "node":
            graph["nodes"][record["ref"]] = record
        else:
            graph["out"].setdefault(record["source"], []).append(record)
            graph["in"].setdefault(record["target"], []).append(record)
    return graph

def find_path(graph, start, is_goal, allowed_kinds=None, max_hops=4):
    """Breadth-first walk over typed edges in either direction, at most `max_hops` long.
    Returns the list of (edge, node reached) hops of the first shortest path, or None."""
    frontier, seen = [(start, [])], {start}
    for _ in range(max_hops):
        following = []
        for node, path in frontier:
            steps = [(e, e["target"]) for e in graph["out"].get(node, [])] + [(e, e["source"]) for e in graph["in"].get(node, [])]
            for edge, reached in sorted(steps, key=lambda step: (step[1], step[0]["kind"])):
                if reached in seen or (allowed_kinds and edge["kind"] not in allowed_kinds):
                    continue
                seen.add(reached)
                if is_goal(reached):
                    return path + [(edge, reached)]
                following.append((reached, path + [(edge, reached)]))
        frontier = following
    return None

def links_of(graph, ref, corner_prefix):
    """The `corresponds` edges of a unit into one corner ("C", "D" or "M"), in ledger order."""
    edges = [e for e in graph["out"].get(ref, []) if e["kind"] == "corresponds" and e["target"].startswith(corner_prefix)]
    return edges + [dict(e, target=e["source"]) for e in graph["in"].get(ref, [])
                    if e["kind"] == "corresponds" and e["source"].startswith(corner_prefix)]

# ---------------------------------------------------------------- words: splitting, stemming, word lists
def load_word_lists(references_dir):
    """Stop words, bridge patterns and the neutral words of mathematical functions. All word
    lists live in references/, where the lint checks them for domain words. Enforces: R9"""
    with open(os.path.join(references_dir, "stopwords.txt"), encoding="utf-8") as handle:
        stop = {word for line in handle if not line.startswith("#") for word in line.split()}
    with open(os.path.join(references_dir, "bridge_patterns.yaml"), encoding="utf-8") as handle:
        patterns = yaml.safe_load(handle)
    with open(os.path.join(references_dir, "r_function_map.yaml"), encoding="utf-8") as handle:
        function_map = yaml.safe_load(handle)
    return {"stop": stop, "patterns": patterns, "function_map": function_map}

def stem(word):
    """A light, rule-based stemmer: plural endings, -ing, -ed, and a doubled last letter.
    Deliberately weak: a wrong merge costs more than a missed one."""
    for ending, replacement in (("ies", "y"), ("ied", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", "e"), ("s", "")):
        if word.endswith(ending) and len(word) - len(ending) >= 3 and not word.endswith(("ss", "us", "is")):
            word = word[:len(word) - len(ending)] + replacement
            break
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "lsz":
        word = word[:-1]
    return word[:-1] if len(word) > 4 and word.endswith("e") else word

AS_WRITTEN = {}      # stem -> the first word seen with that stem; used only to show words to analysts

def split_words(text, stop):
    """Text or identifiers to index words: split at anything that is not a letter or digit,
    at underscores, dots and capital letters inside a name; lower-case; drop stop words,
    single characters and pure numbers; stem."""
    words = []
    for piece in re.findall(r"[^\W_]+", text or ""):
        for part in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[^\W\d_]+|\d+", piece):
            lowered = part.lower()
            if len(lowered) > 1 and not lowered.isdigit() and lowered not in stop:
                words.append(stem(lowered))
                AS_WRITTEN.setdefault(words[-1], lowered)
    return words

def shown(words):
    """Index words as an analyst should see them: as first written, not as stems."""
    return [AS_WRITTEN.get(word, word) for word in words]

def symbols_in(text):
    """Short symbols a passage uses: single letters and Greek names standing alone, short
    capital abbreviations, and names with a subscript."""
    found = re.findall(r"(?<![\w.])([A-Za-z\u0370-\u03ff]{1,4}(?:_\{?\w+\}?|\[\w+\])?)(?![\w(])", text or "")
    keep = []
    for symbol in found:
        plain = shared.normalise_symbol(symbol)
        if symbol.isupper() or len(symbol) == 1 or "_" in symbol or plain in shared.GREEK or symbol in shared.GREEK.values():
            if symbol.lower() not in ("a", "i"):
                keep.append(plain)
    return list(dict.fromkeys(keep))

def numbers_in(text, trivial):
    """The non-trivial numbers of a text, as normalised values ("12.5%" gives 0.125)."""
    return list(dict.fromkeys(n["value"] for n in shared.find_numbers(text or "") if n["value"] not in trivial))

# ---------------------------------------------------------------- what is indexed for each unit
FIELD_WEIGHTS = {"name": 3, "heading": 3, "about": 2, "caption": 2, "symbols": 2, "body": 1, "calls": 1}

def chunk_fields(chunk, lists, trivial):
    """The named fields of a methodology or documentation chunk (plan 2.6)."""
    table = chunk.get("table") or {}
    table_words = " ".join(table.get("header", [])) + " " + " ".join(row[0] for row in table.get("rows", []) if row)
    return {"fields": {"heading": split_words(" ".join(chunk["heading_chain"][-2:]), lists["stop"]),
                       "caption": split_words(chunk.get("caption", "") + " " + table_words, lists["stop"]),
                       "body": split_words(chunk["text"], lists["stop"])},
            "symbols": symbols_in(chunk["text"]) + list((chunk.get("equation") or {}).get("expression") and
                       sorted(shared.expr_symbols(shared.expr_from_dict(chunk["equation"]["expression"]))) or []),
            "numbers": numbers_in(chunk["text"], trivial), "identifiers": re.findall(r"\b[a-z]+(?:[_.][a-z0-9]+)+\b", chunk["text"])}

def unit_fields(unit, units_by_ref, documented_by, lists, trivial):
    """The named fields of a model unit: name words, what the package says about it (roxygen
    of the object or of the function it sits in), comments, symbols, numbers, the neutral
    words of the mathematical functions it calls, and string literals."""
    code = unit.get("code") or {}
    about_unit = documented_by.get(unit["ref"])
    about = about_unit["text"] if about_unit else ""
    parent_block = documented_by.get(unit.get("parent_ref") or "")
    if parent_block and not about_unit:                  # a statement takes only the @param lines of the symbols it uses
        used = set(code.get("symbols_read", ())) | set(code.get("symbols_written", ()))
        about = " ".join(tag["text"] for tag in parent_block["roxygen"]["tags"] if tag["tag"] == "param" and tag["name"] in used)
    if unit.get("roxygen") or unit.get("helppage") or unit["kind"] == shared.KIND_VIGNETTE:
        about = unit["text"]
    comments = " ".join(re.findall(r"#(?!')\s*(.*)", unit["text"])) if code else ""
    neutral = [word for call in code.get("calls", ()) for word in
               lists["patterns"]["function_words"].get((lists["function_map"]["r_functions"].get(call) or {}).get("neutral", ""), [])]
    data = unit.get("data") or {}
    columns = " ".join(name for name, _ in data.get("columns", ()))
    body = comments + " " + " ".join(code.get("strings", ())) + " " + (unit["text"] if data else "")
    symbols = [shared.normalise_symbol(s) for s in tuple(code.get("symbols_read", ())) + tuple(code.get("symbols_written", ()))]
    return {"fields": {"name": split_words(unit["name"] + " " + unit.get("inside", "") + " " + columns, lists["stop"]),
                       "about": split_words(re.sub(r"#'|@\w+|\\\w+", " ", about), lists["stop"]),
                       "body": split_words(body, lists["stop"]), "calls": [stem(word) for word in neutral]},
            "symbols": list(dict.fromkeys(symbols)),
            "numbers": list(dict.fromkeys([n["value"] for n in code.get("numbers", ()) if n["value"] not in trivial] +
                                          numbers_in(about + " " + (unit["text"] if data else ""), trivial))),
            "identifiers": [unit["name"]] if code and unit["name"] else []}

# ---------------------------------------------------------------- S1: field-aware BM25 (the only text-ranking formula)
def build_index(documents):
    """documents: {ref: {"fields": {field: [words]}}}. Term frequencies are weighted by field;
    the length of a document is its weighted number of words."""
    index = {"tf": {}, "length": {}, "df": {}, "n": len(documents)}
    for ref in sorted(documents):
        weighted = {}
        for field_name, words in documents[ref]["fields"].items():
            for word in words:
                weighted[word] = weighted.get(word, 0) + FIELD_WEIGHTS.get(field_name, 1)
        index["tf"][ref], index["length"][ref] = weighted, sum(weighted.values())
        for word in weighted:
            index["df"][word] = index["df"].get(word, 0) + 1
    index["average_length"] = (sum(index["length"].values()) / len(documents)) if documents else 0.0
    return index

def bm25_scores(index, query_weights, k1, b):
    """BM25 with the usual constants k1 and b. query_weights: {word: weight}; a bridged word
    seen only once in the inputs counts half. Returns {ref: (score, matched words)}."""
    scores = {}
    for word in sorted(query_weights):
        df = index["df"].get(word)
        if not df:
            continue
        idf = math.log(1 + (index["n"] - df + 0.5) / (df + 0.5))
        for ref, weighted in index["tf"].items():
            tf = weighted.get(word)
            if tf:
                norm = tf + k1 * (1 - b + b * index["length"][ref] / (index["average_length"] or 1.0))
                score, words = scores.get(ref, (0.0, []))
                scores[ref] = (score + query_weights[word] * idf * tf * (k1 + 1) / norm, words + [word])
    return scores

def ranked(scores):
    """References by falling score; ties break by reference. Enforces: R5"""
    return [ref for ref, _ in sorted(scores.items(), key=lambda item: (-item[1][0] if isinstance(item[1], tuple) else -item[1], item[0]))]

# ---------------------------------------------------------------- S2: the bridge vocabulary
def initials_match(short, words):
    """Do the letters of an abbreviation appear, in order, as initials of the long form?
    Guards against reading "(see Table 3)" as an abbreviation."""
    letters = [c for c in short.lower() if c.isalpha()]
    initials = [w[0].lower() for w in words if w]
    position = 0
    for letter in letters:
        while position < len(initials) and initials[position] != letter:
            position += 1
        if position == len(initials):
            return False
        position += 1
    return bool(letters)

def harvest_text(text, source, patterns):
    """Bridge entries from one text: "long form (ABBR)", "ABBR (long form)", "where X denotes
    ...", "let X be ...". Returns (term, phrase, source, pattern name) tuples."""
    entries = []
    for found in re.finditer(r"((?:[A-Za-z][\w-]*\s+){1,6}[A-Za-z][\w-]*)\s+\(([A-Za-z\u0370-\u03ff][\w]{0,9})\)", text):
        words = found.group(1).split()
        for start in range(len(words) - 1, -1, -1):
            if initials_match(found.group(2), words[start:]) and len(words[start:]) <= len(found.group(2)) + 2:
                entries.append((found.group(2), " ".join(words[start:]), source, "long form (short form)"))
                break
    for found in re.finditer(r"\b([A-Z][A-Za-z0-9_]{1,9})\s+\(([a-z][^()]{3,60})\)", text):
        if initials_match(found.group(1), found.group(2).split()):
            entries.append((found.group(1), found.group(2), source, "short form (long form)"))
    verbs = "|".join(re.escape(verb) for verb in patterns["definition_verbs"])
    for found in re.finditer(r"(?:\bwhere|,|\band)\s+(\S{1,12})\s+(?:%s|is)\s+(?:the\s+|an?\s+)?([^,.;()]{3,60})" % verbs, text):
        if len(found.group(1)) <= 4 or "_" in found.group(1):
            entries.append((found.group(1), found.group(2).strip(), source, "where ... denotes"))
    for found in re.finditer(r"\b[Ll]et\s+(\S{1,12})\s+be\s+(?:the\s+|an?\s+)?([^,.;()]{3,60})", text):
        entries.append((found.group(1), found.group(2).strip(), source, "let ... be"))
    return entries

def harvest_bridge(canon, doc, units, lists, glossary_path):
    """The bridge vocabulary of this project, harvested from its own inputs: documents,
    symbol tables, roxygen @param and @return lines, column descriptions of data blocks,
    comments of the form "# x: phrase", and the optional Inputs/glossary.xlsx. Every entry
    records where it was seen and how often; entries seen once count half."""
    patterns, raw = lists["patterns"], []
    for chunk in canon + doc:
        raw.extend(harvest_text(chunk["text"], chunk["ref"], patterns))
        table = chunk.get("table") or {}
        header = [cell.lower() for cell in table.get("header", [])]
        if len(header) >= 2 and header[0] in patterns["symbol_headers"] and any(h in patterns["description_headers"] for h in header[1:]):
            described = next(i for i, h in enumerate(header) if h in patterns["description_headers"])
            raw.extend((row[0], row[described], chunk["ref"], "table of symbols") for row in table["rows"] if row[0] and row[described])
    for unit in units:
        roxygen = unit.get("roxygen")
        if roxygen:
            for tag in roxygen["tags"]:
                if tag["tag"] == "param" and tag["name"] and tag["text"]:
                    raw.extend((name, tag["text"], "%s@param:%s" % (unit["ref"], name), "roxygen @param") for name in tag["name"].split(","))
                elif tag["tag"] == "return" and tag["text"] and roxygen["documents_name"]:
                    raw.append((roxygen["documents_name"], tag["text"], unit["ref"] + "@return", "roxygen @return"))
            for found in re.finditer(r"\\item\{([^{}]+)\}\{([^{}]+)\}", unit["text"]):
                raw.append((found.group(1), found.group(2), unit["ref"], "column description"))
        if unit.get("code"):
            for found in re.finditer(r"#(?!')\s*([A-Za-z][\w.]{0,20})\s*:\s+([^\n]{3,60})", unit["text"]):
                raw.append((found.group(1), found.group(2).strip(), unit["ref"], "code comment"))
    if glossary_path:
        import openpyxl
        sheet = openpyxl.load_workbook(glossary_path, read_only=True).worksheets[0]
        for row in list(sheet.iter_rows(values_only=True))[1:]:
            if row and row[0] and len(row) > 1 and row[1]:
                raw.extend([(str(row[0]), str(row[1]), "glossary.xlsx", "glossary"), (str(row[1]), str(row[0]), "glossary.xlsx", "glossary")])
    merged = {}
    for term, phrase, source, pattern in raw:
        key = (shared.normalise_symbol(term.strip()), " ".join(split_words(phrase, lists["stop"])))
        if not key[1]:
            continue
        entry = merged.setdefault(key, {"term": key[0], "term_as_written": term.strip(), "phrase": shared.normalise_text(phrase)[:80],
                                        "words": key[1].split(), "sources": [], "patterns": [], "count": 0})
        entry["count"] += 1
        entry["sources"].append(source)
        entry["patterns"].append(pattern)
    return [merged[key] for key in sorted(merged)]

def expansions_for(representation, bridge_by_term):
    """The bridge entries that apply to a unit: by its symbols and by its name words."""
    found = []
    for term in list(representation["symbols"]) + representation["fields"].get("name", []) + representation.get("identifiers", []):
        for entry in bridge_by_term.get(shared.normalise_symbol(term), []):
            if entry not in found:
                found.append(entry)
    return found

# ---------------------------------------------------------------- S3: explicit references as written
def resolve_reference(reference, chunks):
    """"Table 3", "section 4.2", "Annex B" as written, resolved among `chunks` (one corner):
    tables, figures and equations by the label at the start of their caption, sections by
    their numbering as written. Several matches are all returned; none gives an empty list."""
    label, _, number = reference.partition(" ")
    label, number = label.lower().rstrip("s"), number.strip("().").lower()
    matches = []
    for chunk in chunks:
        caption = (chunk.get("caption") or "").lower()
        if label in ("table", "figure", "equation") and chunk["kind"].lower() == label:
            if re.match(r"%s\s+\(?%s\)?(?!\w)(?!\.\d)" % (label, re.escape(number)), caption):
                matches.append(chunk["ref"])
        elif label in ("section", "paragraph", "chapter", "annex", "appendix"):
            written = (chunk.get("numbering") or "").lower().rstrip(".")
            if written == number or written in ("%s %s" % (label, number), "annex %s" % number, "appendix %s" % number):
                matches.append(chunk["ref"])
    return matches

# ---------------------------------------------------------------- S4: rare shared anchors and the restart random walk
def anchors_of(representation, heading_words, scope):
    """The anchors one unit or chunk mentions, as (kind, key) pairs. A symbol is scoped by
    `scope` (symbol -> key of the section that defines it) where a definition is known."""
    anchors = [("number", value) for value in representation["numbers"]]
    anchors += [("symbol", scope.get(symbol, symbol)) for symbol in representation["symbols"]]
    anchors += [("identifier", name) for name in representation.get("identifiers", [])]
    anchors += [("term", word) for word in representation.get("terms", [])]
    if heading_words:
        anchors.append(("heading", " ".join(heading_words)))
    return list(dict.fromkeys(anchors))

def anchor_weights(mentions, settings):
    """Weight of an anchor = 1 / log(1 + number of units that mention it). An anchor that
    more than `anchor_max_share` of all units mention is dropped; an anchor only one unit
    mentions joins nothing and is dropped too; heading anchors are capped so that a section
    title shared by many passages cannot dominate."""
    total = len({ref for refs in mentions.values() for ref in refs})
    weights = {}
    for anchor, refs in mentions.items():
        if len(refs) < 2 or len(refs) > max(2, settings["anchor_max_share"] * total):
            continue
        weight = 1.0 / math.log(1 + len(refs))
        weights[anchor] = min(weight, settings["heading_anchor_cap"]) if anchor[0] == "heading" else weight
    return weights

def restart_walk(mentions, weights, starts, settings):
    """A random walk over the two-sided graph of units and anchors that keeps restarting at the
    unit (personalised PageRank): fixed restart probability and a fixed number of rounds, so
    it is deterministic. Returns {start: {ref: closeness}}."""
    import numpy
    from scipy import sparse
    refs = sorted({ref for anchor in weights for ref in mentions[anchor]})
    anchors = sorted(weights)
    position = {ref: i for i, ref in enumerate(refs)}
    rows, columns, values = [], [], []
    for column, anchor in enumerate(anchors):
        for ref in mentions[anchor]:
            rows.append(position[ref])
            columns.append(len(refs) + column)
            values.append(weights[anchor])
    size = len(refs) + len(anchors)
    if not values:
        return {start: {} for start in starts}
    matrix = sparse.coo_matrix((values + values, (rows + columns, columns + rows)), shape=(size, size)).tocsr()
    degree = numpy.asarray(matrix.sum(axis=0)).ravel()
    degree[degree == 0] = 1.0
    transition = matrix.multiply(1.0 / degree).tocsr()               # each column sums to one: hubs pass on little
    results, restart = {}, settings["walk_restart"]
    for start in starts:
        if start not in position:
            results[start] = {}
            continue
        home = numpy.zeros(size)
        home[position[start]] = 1.0
        state = home.copy()
        for _ in range(int(settings["walk_rounds"])):
            state = (1 - restart) * transition.dot(state) + restart * home
        results[start] = {ref: float(state[position[ref]]) for ref in refs if ref != start and state[position[ref]] > 1e-9}
    return results

# ---------------------------------------------------------------- S6: signatures (re-order only) and table shape
def formula_signature(expression):
    """What a formula is made of, whatever its symbols are called: operators, neutral
    function names with their number of arguments, and non-trivial constants."""
    parts = {}
    for node in shared.expr_walk(shared.expr_from_dict(expression)):
        if node.op in ("sym", "eq"):
            continue
        key = "%s/%d" % (node.name, len(node.args)) if node.op == "call" else node.value if node.op == "num" else node.op
        if key not in ("0", "1", "2"):
            parts[key] = parts.get(key, 0) + 1
    return parts

def overlap(left, right):
    """Weighted overlap of two multisets, between 0 and 1."""
    shared_count = sum(min(count, right.get(key, 0)) for key, count in left.items())
    return shared_count / max(1, max(sum(left.values()), sum(right.values())))

def table_shape_score(table, chunk_table, stop):
    """How alike two tables are: shared header words, shared row keys and shared values at
    printed precision. The package table comes from parameter_tables; the other from a chunk."""
    header_a = set(split_words(" ".join(table["header"]), stop))
    header_b = set(split_words(" ".join(chunk_table.get("header", [])), stop))
    keys_a = {row[0].strip().lower() for row in table["rows"] if row}
    keys_b = {row[0].strip().lower() for row in chunk_table.get("rows", []) if row}
    values_a = {n["value"] for row in table["rows"] for cell in row for n in shared.find_numbers(cell)}
    values_b = {n["value"] for row in chunk_table.get("rows", []) for cell in row for n in shared.find_numbers(cell)}
    share = lambda a, b: len(a & b) / max(1, min(len(a), len(b)))
    return share(header_a, header_b) + share(keys_a, keys_b) + share(values_a, values_b)

# ---------------------------------------------------------------- fusion and reasons
REASON_TEMPLATES = {      # every phrase the search stage can put into "How established"
    "fields": "shares the words {detail}",
    "bridge": "{detail}",
    "references": "it is cited as written ({detail})",
    "anchors": "shares the rare {detail}",
    "signatures": "its formula has a similar structure",
    "table shape": "its table has similar headers, row keys or values",
    "propagation": "inherited from {detail}"}
SIGNAL_ORDER = ("references", "fields", "bridge", "anchors", "table shape", "signatures", "propagation")

def fuse(rankings, settings, cited=(), reserve_from=("anchors", "propagation")):
    """Reciprocal rank fusion: score = sum over signals of 1 / (60 + rank). Only ranks are
    combined, so no signal's raw scale matters. Explicitly cited chunks are always included
    (up to three); two places are reserved for the best anchor or propagated candidates
    that the word search did not rank; ties break by reference. Enforces: R5"""
    constant, k = settings["rrf_constant"], int(settings["k_candidates"])
    scores, ranks = {}, {}
    for signal in SIGNAL_ORDER:
        refs = rankings.get(signal, [])
        if signal == "signatures":                       # used to re-order, never alone
            refs = [ref for ref in refs if ref in scores]
        for rank, ref in enumerate(refs, start=1):
            scores[ref] = scores.get(ref, 0.0) + 1.0 / (constant + rank)
            ranks.setdefault(ref, {})[signal] = rank
    ordered = sorted(scores, key=lambda ref: (-scores[ref], ref))
    must = list(dict.fromkeys(list(cited)[:3]))
    reserved = [ref for signal in reserve_from for ref in rankings.get(signal, []) if "fields" not in ranks.get(ref, {})]
    must += [ref for ref in dict.fromkeys(reserved) if ref not in must][:int(settings["reserved_places"])]
    shortlist = [ref for ref in ordered if ref not in must][:max(0, k - len(must))] + must
    shortlist.sort(key=lambda ref: (-scores.get(ref, 0.0), ref))
    return [(ref, scores.get(ref, 0.0), ranks.get(ref, {})) for ref in shortlist]

def reason_text(signals, details):
    """The plain reason of one candidate, assembled from the signals that proposed it."""
    phrases = [REASON_TEMPLATES[signal].format(detail=details.get(signal, "")) for signal in SIGNAL_ORDER
               if signal in signals and (details.get(signal) or "{detail}" not in REASON_TEMPLATES[signal])]
    return "Proposed because: " + "; ".join(phrases) if phrases else "Proposed by rank only"

# ---------------------------------------------------------------- step 05: build-graph
def structural_edges(units, provenance):
    """Edges the readers established: contains, calls, tested_by, documents, generated_from,
    reads_data. All are parsed from the files, none comes from the AI."""
    functions = {u["name"]: u["ref"] for u in units if u["kind"] == shared.KIND_FUNCTION and not u["inside"]}
    data_units = {u["name"]: u["ref"] for u in units if u.get("data")}
    edges = []
    def add(source, target, kind, evidence=None):
        edges.append(shared.Edge(source, target, kind, shared.HOW_PARSED, provenance, evidence=evidence or {}))
    for unit in units:
        code = unit.get("code") or {}
        if unit.get("parent_ref"):
            add(unit["parent_ref"], unit["ref"], "contains")
        for name in code.get("calls", ()):
            if name in functions and functions[name] != unit["ref"] and unit["kind"] in (shared.KIND_FUNCTION, shared.KIND_TEST):
                add(functions[name] if unit["kind"] == shared.KIND_TEST else unit["ref"],
                    unit["ref"] if unit["kind"] == shared.KIND_TEST else functions[name],
                    "tested_by" if unit["kind"] == shared.KIND_TEST else "calls")
        for read in code.get("reads_data", ()):
            if read["object"] in data_units:
                add(unit["ref"], data_units[read["object"]], "reads_data", dict(read))
        if unit.get("roxygen") and unit["roxygen"]["documents_ref"]:
            add(unit["ref"], unit["roxygen"]["documents_ref"], "documents")
        page = unit.get("helppage")
        if page:
            if page["generated_from_ref"]:
                add(unit["ref"], page["generated_from_ref"], "generated_from")
            target = functions.get(page["rd_name"]) or data_units.get(page["rd_name"])
            if target:
                add(unit["ref"], target, "documents")
    return edges

def build_graph(ctx):
    """Step 05, skill build-graph: nodes for every chunk and unit, structural edges,
    cross-references resolved within their own corner, and the bridge vocabulary."""
    canon, doc, units = ctx.read("chunks_canon"), ctx.read("chunks_doc"), ctx.read("model_units")
    lists = load_word_lists(ctx.options["references_dir"])
    records = [node_record(c["ref"], c["kind"], c["corner"]) for c in canon + doc]
    records += [node_record(u["ref"], u["kind"], "model") for u in units]
    edges, unresolved = structural_edges(units, ctx.provenance), []
    for corner_chunks in (canon, doc):
        for chunk in corner_chunks:
            same_file = [c for c in corner_chunks if c["source_file"] == chunk["source_file"]]
            for reference in chunk.get("refs_out", ()):
                targets = [ref for ref in resolve_reference(reference, same_file) if ref != chunk["ref"]]
                for target in targets:
                    edges.append(shared.Edge(chunk["ref"], target, "cross_reference", shared.HOW_PARSED, ctx.provenance,
                                             evidence={"as_written": reference}))
                own_caption = (chunk.get("caption") or "").lower().startswith(reference.lower())
                if not targets and not own_caption:
                    unresolved.append({"unit_ref": chunk["ref"], "reference": reference,
                                       "note": "'%s' is cited here but could not be found in %s" % (reference, chunk["source_file"])})
    bridge = harvest_bridge(canon, doc, units, lists, ctx.options["inputs"].get("glossary"))
    ledger = ledger_records(ctx.read("graph_ledger"), records + edges)
    return shared.StepResult({"graph_ledger": ledger, "bridge_vocabulary": bridge, "unresolved_references": unresolved},
                             {"nodes": len(records), "edges": len(edges), "bridge entries": len(bridge)},
                             ["Graph version %s." % graph_version_id(ctx.read("graph_ledger") + ledger)])

# ---------------------------------------------------------------- step 06: find-candidates
SEARCHED_KINDS = (shared.KIND_FUNCTION, shared.KIND_FORMULA, shared.KIND_TABLE, shared.KIND_OBJECT, shared.KIND_VIGNETTE)

def is_searched(unit, settings):
    """Which model units look for passages. Test blocks, files that were not read, package
    files without code, and (unless the setting says otherwise) supporting code by syntax
    are not sent to the search or to the judge; roxygen blocks and help pages take the
    tracing of the object they document."""
    if unit["kind"] not in SEARCHED_KINDS:
        return False
    if unit.get("data") and not unit["data"]["assessable"]:
        return False
    code = unit.get("code") or {}
    return not code.get("plumbing") or bool(settings["judge_supporting_code"])

def searched_text(representation, expansions, corner, proposed):
    """The "What was searched" sentence of one unit and corner."""
    words = list(dict.fromkeys(representation["fields"].get("name", []) + representation["fields"].get("heading", [])))[:8]
    if not words:
        words = list(dict.fromkeys(representation["fields"].get("body", [])))[:8]
    listed = []
    for word in words:
        entry = next((e for e in expansions if stem(e["term"].lower()) == word or e["term"] == word), None)
        listed.append("%s (%s)" % (AS_WRITTEN.get(word, word), entry["phrase"]) if entry else AS_WRITTEN.get(word, word))
    parts = ["Searched %s for: %s" % (CORNER_NAMES[corner], ", ".join(listed) or "no usable words")]
    if representation["symbols"]:
        parts.append("symbols " + ", ".join(representation["symbols"][:8]))
    if representation["numbers"]:
        parts.append("numbers " + ", ".join(representation["numbers"][:8]))
    return "; ".join(parts) + ". %d passage(s) proposed." % proposed

def search_one(source_ref, representation, corner, world, settings):
    """All signals for one unit and one target corner, fused into a shortlist of candidates."""
    targets, index, enabled = world["targets"][corner], world["index"][corner], settings["signals"]
    rankings, details = {}, {}
    query = {word: 1.0 for words in representation["fields"].values() for word in words}
    expansions = expansions_for(representation, world["bridge_by_term"]) if "bridge" in enabled else []
    if "fields" in enabled:
        scores = bm25_scores(index, query, settings["bm25_k1"], settings["bm25_b"])
        rankings["fields"] = ranked(scores)
        details["fields"] = {ref: ", ".join(dict.fromkeys(shown(words[:4]))) for ref, (score, words) in scores.items()}
    if expansions:
        bridged = {word: (1.0 if e["count"] > 1 else 0.5) for e in expansions for word in e["words"] if word not in query}
        scores = bm25_scores(index, bridged, settings["bm25_k1"], settings["bm25_b"])
        rankings["bridge"] = ranked(scores)
        for ref, (score, words) in scores.items():
            entry = next(e for e in expansions if set(e["words"]) & set(words))
            details.setdefault("bridge", {})[ref] = "'%s' is described as '%s' (%s), which this passage mentions" % (
                entry["term_as_written"], entry["phrase"], entry["sources"][0])
    cited = []
    if "references" in enabled:
        for reference in representation.get("references", ()):
            for ref in resolve_reference(reference, targets.values()):
                cited.append(ref)
                details.setdefault("references", {})[ref] = reference
        rankings["references"] = list(dict.fromkeys(cited))
    if "anchors" in enabled:
        closeness = world["walk"].get(source_ref, {})
        rankings["anchors"] = ranked({ref: score for ref, score in closeness.items() if ref in targets})[:2 * int(settings["k_candidates"])]
        own = set(world["anchors"].get(source_ref, ()))
        for ref in rankings["anchors"]:
            common = sorted(own & set(world["anchors"].get(ref, ())), key=lambda a: (-world["weights"].get(a, 0), a))
            common = [a for a in common if a in world["weights"]]
            if common:
                details.setdefault("anchors", {})[ref] = " and ".join("%s %s" % (kind, key.split("@")[0]) for kind, key in common[:2])
    if "signatures" in enabled and representation.get("signature"):
        alike = {ref: overlap(representation["signature"], world["signatures"][ref]) for ref in targets if ref in world["signatures"]}
        rankings["signatures"] = ranked({ref: score for ref, score in alike.items() if score >= 0.5})
    if representation.get("table"):
        shapes = {ref: table_shape_score(representation["table"], targets[ref]["table"], world["lists"]["stop"])
                  for ref in targets if targets[ref].get("table")}
        rankings["table shape"] = ranked({ref: score for ref, score in shapes.items() if score >= 1.0})
    if "propagation" in enabled:
        inherited = world["propagated"].get((source_ref, corner), [])
        rankings["propagation"] = [ref for ref, _ in inherited]
        details["propagation"] = dict(inherited)
    fused = fuse(rankings, settings, cited)
    candidates = []
    for rank, (ref, score, signals) in enumerate(fused, start=1):
        reason = reason_text(signals, {signal: details.get(signal, {}).get(ref, "") for signal in signals})
        candidates.append(shared.Candidate(source_ref, ref, corner, rank, round(score, 6), signals, reason,
                                           suggestion_only="propagation" in signals and len(signals) == 1,
                                           search_pass=world["search_pass"]))
    ranked_anywhere = sorted({ref for refs in rankings.values() for ref in refs})
    record = {"unit_ref": source_ref, "target_corner": corner, "search_pass": world["search_pass"],
              "query_fields": representation["fields"], "expansions": [(e["term"], e["words"], e["sources"][0]) for e in expansions],
              "anchors_used": [list(a) for a in world["anchors"].get(source_ref, ()) if a in world["weights"]][:20],
              "per_signal": {signal: len(refs) for signal, refs in rankings.items()}, "shortlist": [c.target_ref for c in candidates],
              "ranked_anywhere": ranked_anywhere, "searched_text": searched_text(representation, expansions, corner, len(candidates)),
              "note": "" if candidates else "Nothing in %s shares a word, a symbol, a number or a citation with this unit." % CORNER_NAMES[corner]}
    return candidates, record

def build_world(ctx, search_pass):
    """Everything the search needs, built once per step: representations of all units and
    chunks, one BM25 index per corner, the bridge vocabulary, anchors and the walk."""
    settings, lists = ctx.settings, load_word_lists(ctx.options["references_dir"])
    trivial = set(settings["trivial_numbers"])
    canon, doc, units = ctx.read("chunks_canon"), ctx.read("chunks_doc"), ctx.read("model_units")
    tables = {t["unit_ref"]: t for t in ctx.read("parameter_tables")}
    by_ref = {u["ref"]: u for u in units}
    documented_by = {u["roxygen"]["documents_ref"]: u for u in units if u.get("roxygen") and u["roxygen"]["documents_ref"]}
    representations = {}
    for chunk in canon + doc:
        representations[chunk["ref"]] = dict(chunk_fields(chunk, lists, trivial), references=chunk.get("refs_out", ()),
                                             heading=split_words(" ".join(chunk["heading_chain"][-1:]), lists["stop"]))
        equation = chunk.get("equation") or {}
        if equation.get("expression"):
            representations[chunk["ref"]]["signature"] = formula_signature(equation["expression"])
    for unit in units:
        representation = unit_fields(unit, by_ref, documented_by, lists, trivial)
        about = documented_by.get(unit["ref"])
        representation["references"] = aiva1_documents.cross_references(unit["text"] + " " + (about["text"] if about else ""),
                                                                        {"cross_reference_labels": ["Table", "Figure", "Section", "Equation", "Annex", "Appendix"]})
        expression = (unit.get("code") or {}).get("expression") or (unit.get("code") or {}).get("composed")
        if expression:
            representation["signature"] = formula_signature(expression)
        if unit["ref"] in tables:
            representation["table"] = tables[unit["ref"]]
        representations[unit["ref"]] = representation
    bridge_by_term = {}
    for entry in ctx.read("bridge_vocabulary"):
        bridge_by_term.setdefault(entry["term"], []).append(entry)
    definitions = {}
    for entries in bridge_by_term.values():
        for entry in entries:
            for source in entry["sources"]:
                if source[:2] in ("C-", "D-"):
                    definitions.setdefault(entry["term"], set()).add(source)
    scope = {term: "%s@%s" % (term, sorted(sources)[0]) for term, sources in definitions.items() if len(sources) == 1}
    anchors, mentions = {}, {}
    for ref, representation in representations.items():
        anchors[ref] = anchors_of(representation, representation.get("heading"), scope)
        for anchor in anchors[ref]:
            mentions.setdefault(anchor, []).append(ref)
    weights = anchor_weights(mentions, settings)
    searched = [u["ref"] for u in units if is_searched(u, settings)] + [c["ref"] for c in doc if c.get("checkable")]
    walk = restart_walk(mentions, weights, searched, settings) if "anchors" in settings["signals"] else {}
    targets = {"canon": {c["ref"]: c for c in canon}, "doc": {c["ref"]: c for c in doc},
               "model": {u["ref"]: u for u in units if is_searched(u, settings)}}
    index = {corner: build_index({ref: representations[ref] for ref in targets[corner]}) for corner in targets}
    signatures = {ref: r["signature"] for ref, r in representations.items() if r.get("signature")}
    return {"representations": representations, "targets": targets, "index": index, "bridge_by_term": bridge_by_term,
            "anchors": anchors, "weights": weights, "walk": walk, "signatures": signatures, "lists": lists,
            "units": units, "doc": doc, "canon": canon, "propagated": {}, "search_pass": search_pass}

def propagated_candidates(world, graph):
    """S5, pass 2 only. Once the judge accepted that a function corresponds to a passage, the
    statements inside it, the functions it calls, the data it reads and its tests inherit
    that passage, and the tables the passage cites, as SUGGESTIONS. Never as links."""
    inherited = {}
    names = {u["ref"]: "%s %s" % (u["kind"].lower(), u["name"]) for u in world["units"]}
    for unit in world["units"]:
        accepted = [e for e in links_of(graph, unit["ref"], "C") + links_of(graph, unit["ref"], "D") if e["relation"] in shared.LINKING_RELATIONS]
        if unit["kind"] != shared.KIND_FUNCTION or not accepted:
            continue
        heirs = [e["target"] for e in graph["out"].get(unit["ref"], []) if e["kind"] in ("contains", "calls", "reads_data", "tested_by")]
        for edge in accepted:
            corner = "canon" if edge["target"].startswith("C") else "doc"
            cited = [e["target"] for e in graph["out"].get(edge["target"], []) if e["kind"] == "cross_reference"]
            for heir in heirs:
                for target in [edge["target"]] + cited:
                    detail = "%s (%s), which the AI judged to correspond to %s" % (unit["ref"], names[unit["ref"]], edge["target"])
                    inherited.setdefault((heir, corner), []).append((target, detail))
    return inherited

def find_candidates(ctx):
    """Step 06 (pass 1) and step 08 (pass 2), skill find-candidates. Pass 1 searches for every
    searched model unit in the methodology and the documentation, and for every checkable
    documentation passage in the methodology. Pass 2 searches again, with propagation, only
    for units still without a methodology link, and looks in the package for documentation
    passages still without any link. Every search leaves a search record. Enforces: R2"""
    search_pass = int(ctx.options.get("pass", 1))
    world = build_world(ctx, search_pass)
    graph = load_graph(ctx.read("graph_ledger"))
    jobs = []
    if search_pass == 1:
        jobs += [(u["ref"], corner) for u in world["units"] if is_searched(u, ctx.settings) for corner in ("canon", "doc")]
        jobs += [(c["ref"], "canon") for c in world["doc"] if c.get("checkable")]
    else:
        world["propagated"] = propagated_candidates(world, graph)
        linked = lambda ref, prefix: any(e["relation"] in shared.LINKING_RELATIONS for e in links_of(graph, ref, prefix))
        jobs += [(ref, corner) for (ref, corner) in sorted(world["propagated"]) if not linked(ref, "C" if corner == "canon" else "D")
                 and ref in world["targets"]["model"]]
        jobs += [(c["ref"], "model") for c in world["doc"] if c.get("checkable") and not linked(c["ref"], "C") and not linked(c["ref"], "M")]
    candidates, records = [], []
    for source_ref, corner in jobs:
        found, record = search_one(source_ref, world["representations"][source_ref], corner, world, ctx.settings)
        candidates.extend(found)
        records.append(record)
    return shared.StepResult({"candidates": candidates, "search_records": records},
                             {"searches": len(jobs), "candidates": len(candidates),
                              "searches without any proposal": sum(1 for r in records if not r["shortlist"])}, [])

# ---------------------------------------------------------------- questions for the AI
def cut_code(text, limit):
    """Cut a long function around its formula lines: the header, then every line that
    computes something with two lines of context, until the limit is reached."""
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    wanted = {0, 1, len(lines) - 1}
    for number, line in enumerate(lines):
        if re.search(r"(<-|=).*[-+*/^]|\b(pnorm|qnorm|exp|log|sqrt|pmax|pmin|max|min)\(", line):
            wanted.update(range(max(0, number - 2), min(len(lines), number + 3)))
    kept, size, previous = [], 0, -1
    for number in sorted(wanted):
        if size + len(lines[number]) > limit:
            break
        if number != previous + 1:
            kept.append("# [... lines cut ...]")
        kept.append(lines[number])
        size, previous = size + len(lines[number]) + 1, number
    return "\n".join(kept)

def passage_text(node, settings, keep_words=()):
    """How a chunk or a unit is shown as a lettered passage. A table is never pasted whole:
    its header, three rows and its dimensions."""
    table = node.get("table")
    if table and table.get("header") is not None and node.get("kind") == "Table":
        rows = table.get("rows", [])
        shown = ["; ".join(table["header"])] + ["; ".join(row) for row in rows[:3]]
        return "\n".join(shown) + "\n(table of %d rows and %d columns%s)" % (
            len(rows), len(table["header"]), "; caption: " + node["caption"] if node.get("caption") else "")
    if node.get("code") is not None or node.get("file"):
        return cut_code(node["text"], int(settings["max_passage_chars"]))
    return reading.cut_text(node["text"], int(settings["max_passage_chars"]), keep_words)

def passage_label(node):
    """The heading line of a lettered passage: where it stands, never its reference."""
    if node.get("heading_chain") is not None:
        place = " > ".join(node["heading_chain"][-3:]) or node["source_file"]
        return "%s, %s%s" % (place, node["kind"].lower(), " %d" % node["para_no"] if node.get("para_no") else "")
    lines = "lines %d-%d" % tuple(node["lines"]) if node.get("lines") else ""
    return "%s `%s`, %s %s" % (node["kind"].lower(), node["name"], node["file"], lines)

def letters_for(count):
    """A, B, ... Z, AA, AB, ... for the passages of one question."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return [alphabet[i] if i < 26 else alphabet[i // 26 - 1] + alphabet[i % 26] for i in range(count)]

def choose_decoys(unit_ref, shortlist, never, pool, anchors, count):
    """Planted control passages: chosen by a hash of the unit reference (never at random) from
    passages that share no anchor with the unit and appear nowhere in its rankings."""
    own = set(anchors.get(unit_ref, ()))
    eligible = [ref for ref in sorted(pool) if ref not in never and ref not in shortlist
                and not own & set(anchors.get(ref, ())) and len(pool[ref].get("text", "")) > 40]
    eligible.sort(key=lambda ref: hashlib.sha256((unit_ref + ref).encode("utf-8")).hexdigest())
    return eligible[:count]

def assemble_question(question_type, unit_ref, blocks, passages, prompt, settings, planted=(), more=None):
    """Put one question together. blocks: [(label line, text)]; passages: [(ref, label, text)].
    Passages are lettered in an order derived from a hash, never by score, so position
    carries no hint. The question id is the hash of the full prompt. Enforces: R5"""
    ordered = sorted(passages, key=lambda p: hashlib.sha256((unit_ref + "|" + p[0]).encode("utf-8")).hexdigest())
    letters = dict(zip(letters_for(len(ordered)), ordered))
    shown = "\n".join("[%s] %s\n<<<\n%s\n>>>" % (letter, label, text) for letter, (ref, label, text) in letters.items())
    main = prompt["main"].replace("[[PASSAGES]]", shown)
    for slot, (label, text) in zip(("[[UNIT]]", "[[ABOUT]]"), list(blocks) + [("", "")]):
        main = main.replace(slot, "%s\n<<<\n%s\n>>>" % (label, text) if label else "")
    main = re.sub(r"\n{2,}", "\n", main)
    question = {"question_type": question_type, "unit_ref": unit_ref, "system_prompt": prompt["system"], "main_prompt": main,
                "letters": {letter: ref for letter, (ref, _, _) in letters.items()},
                "planted": [letter for letter, (ref, _, _) in letters.items() if ref in planted],
                "passage_texts": {letter: text for letter, (_, _, text) in letters.items()},
                "unit_text": "\n".join(text for _, text in blocks), "strip_patterns": list(settings["strip_patterns"]),
                "estimated_tokens": reading.estimate_tokens(main, blocks[0][1] if blocks else ""),
                "question_id": shared.sha256_text(prompt["version"] + "\n" + prompt["system"] + "\n" + main)}
    question.update(more or {})
    question["too_large"] = question["estimated_tokens"] > reading.prompt_budget(settings, prompt["system"])
    return question

def narrow_question(question_type, unit_ref, blocks, references_dir, settings, passages=(), more=None):
    """The narrow questions of the checks (map-table-columns, align-symbols, read-formula-
    from-prose, check-rule): same assembly, same budget, same validators."""
    return assemble_question(question_type, unit_ref, blocks, list(passages), reading.load_prompt(references_dir, question_type), settings, more=more)

def judge_question(source, corner, candidates, world, references_dir, settings):
    """The judge question of one unit (or documentation passage) and one target corner."""
    is_chunk = source.get("heading_chain") is not None
    question_type = {("canon", False): "judge-unit-to-canon", ("doc", False): "judge-unit-to-doc",
                     ("canon", True): "judge-doc-to-canon", ("model", True): "judge-doc-to-model"}[(corner, is_chunk)]
    pool = world["targets"][corner]
    shortlist = [c["target_ref"] for c in candidates]
    record = next((r for r in world["search_records"] if r["unit_ref"] == source["ref"] and r["target_corner"] == corner), {})
    decoys = choose_decoys(source["ref"], shortlist, set(record.get("ranked_anywhere", ())), pool, world["anchors"],
                           1 if len(shortlist) < 6 else 2)
    words = [word for words in world["representations"][source["ref"]]["fields"].values() for word in words]
    passages = [(ref, passage_label(pool[ref]), passage_text(pool[ref], settings, words)) for ref in shortlist + decoys]
    unit_text = reading.cut_text(source["text"], int(settings["max_unit_chars"])) if is_chunk else cut_code(source["text"], int(settings["max_unit_chars"]))
    blocks = [("UNIT (%s)" % passage_label(source), unit_text)]
    about = world["documented_by"].get(source["ref"]) or world["documented_by"].get(source.get("parent_ref") or "")
    if about and not is_chunk:
        blocks.append(("WHAT THE PACKAGE SAYS ABOUT IT", reading.cut_text(re.sub(r"(?m)^\s*#' ?", "", about["text"]), 1200)))
    return assemble_question(question_type, source["ref"], blocks, passages, reading.load_prompt(references_dir, question_type),
                             settings, planted=decoys, more={"target_corner": corner})

# ---------------------------------------------------------------- validators: code decides what is usable
class Rejected(Exception):
    """An answer that cannot be used. The message is one reason from the fixed plain list."""


def check_quote(quote, text, required=True):
    """A quotation must be verbatim after white-space normalisation, contiguous, without an
    ellipsis, and of a sensible length."""
    quote = shared.normalise_text(quote if isinstance(quote, str) else "")
    if not quote and not required:
        return
    flat = shared.normalise_text(text)
    if len(quote) < 4 or len(quote) > 400 or "..." in quote or "\u2026" in quote or quote not in flat:
        raise Rejected(shared.REJECTION_REASONS[2])

JUDGE_RELATIONS = {"judge-unit-to-canon": ("implements", "partly implements", "deviates from", "merely related"),
                   "judge-unit-to-doc": ("describes", "consistent with", "inconsistent with"),
                   "judge-doc-to-canon": ("consistent with", "inconsistent with", "merely related"),
                   "judge-doc-to-model": ("describes", "inconsistent with")}

def validate_judge(question, answer):
    """The answer to a judge question: its shape, the letters it names, its quotations, planted passages, self-contradiction."""
    allowed = {"matches", "none_reason", "states_nothing_checkable"}
    if not isinstance(answer.get("matches"), list) or set(answer) - allowed:
        raise Rejected(shared.REJECTION_REASONS[0])
    for match in answer["matches"]:
        confidence = match.get("confidence") if isinstance(match, dict) else None
        if not isinstance(match, dict) or set(match) - {"letter", "relation", "confidence", "quote_from_passage", "quote_from_unit"} \
                or match.get("relation") not in JUDGE_RELATIONS[question["question_type"]] \
                or isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
            raise Rejected(shared.REJECTION_REASONS[0])
        if match.get("letter") not in question["letters"]:
            raise Rejected(shared.REJECTION_REASONS[1])
    for match in answer["matches"]:
        check_quote(match.get("quote_from_passage"), question["passage_texts"][match["letter"]])
        check_quote(match.get("quote_from_unit"), question["unit_text"])
    if any(match["letter"] in question["planted"] and match["relation"] != "merely related" for match in answer["matches"]):
        raise Rejected(shared.REJECTION_REASONS[3])
    if answer["matches"] and str(answer.get("none_reason") or "").strip():
        raise Rejected(shared.REJECTION_REASONS[4])

def validate_narrow(question, answer):
    """The narrow question types. Each check mirrors what the prompt allows."""
    kind = question["question_type"]
    if kind == "second-opinion":
        if not isinstance(answer.get("differences"), list):
            raise Rejected(shared.REJECTION_REASONS[0])
        for difference in answer["differences"]:
            if not isinstance(difference, dict) or difference.get("letter") not in question["letters"]:
                raise Rejected(shared.REJECTION_REASONS[1])
            check_quote(difference.get("quote_from_passage"), question["passage_texts"][difference["letter"]])
            check_quote(difference.get("quote_from_unit"), question["unit_text"])
    elif kind == "interpret-code":
        words = answer.get("interpretation")
        if not isinstance(words, str) or not 3 <= len(words.split()) <= 150:
            raise Rejected(shared.REJECTION_REASONS[0])
        check_quote(answer.get("quote_from_unit"), question["code_text"])     # it has to rest on code that is there
    elif kind == "check-rule":
        if answer.get("outcome") not in ("applied", "applied differently", "not applied"):
            raise Rejected(shared.REJECTION_REASONS[0])
        check_quote(answer.get("quote_from_passage"), question["rule_text"])
        check_quote(answer.get("quote_from_unit"), question["code_text"], required=answer["outcome"] != "not applied")
    elif kind == "align-symbols":
        pairs = answer.get("alignment")
        if not isinstance(pairs, list) or not isinstance(answer.get("cannot_align", False), bool):
            raise Rejected(shared.REJECTION_REASONS[0])
        codes, equations = [p.get("code") for p in pairs if isinstance(p, dict)], [p.get("equation") for p in pairs if isinstance(p, dict)]
        if len(codes) != len(pairs) or set(codes) - set(question["code_symbols"]) or set(equations) - set(question["equation_symbols"]):
            raise Rejected(shared.REJECTION_REASONS[1])
        if len(set(codes)) != len(codes) or len(set(equations)) != len(equations) or (pairs and answer.get("cannot_align")):
            raise Rejected(shared.REJECTION_REASONS[4])
    elif kind == "read-formula-from-prose":
        formula = answer.get("formula")
        if not isinstance(formula, str) or (not formula.strip()) != bool(answer.get("no_formula_stated")):
            raise Rejected(shared.REJECTION_REASONS[4] if isinstance(formula, str) else shared.REJECTION_REASONS[0])
        if formula.strip():
            try:
                tree = aiva1_documents.parse_formula(formula, question["notation"])
            except aiva1_documents.NotReadable:
                raise Rejected(shared.REJECTION_REASONS[0])
            text = question["unit_text"].lower()
            if any(symbol.lower().replace("_", " ") not in text and symbol.lower() not in text for symbol in shared.expr_symbols(tree)):
                raise Rejected(shared.REJECTION_REASONS[2])
    elif kind == "map-table-columns":
        if answer.get("table") == "NONE":
            return
        if answer.get("table") not in question["letters"]:
            raise Rejected(shared.REJECTION_REASONS[1])
        columns, key = answer.get("columns"), answer.get("key")
        if not isinstance(columns, list) or not isinstance(key, dict) or not columns:
            raise Rejected(shared.REJECTION_REASONS[0])
        ours, theirs = question["package_header"], question["other_headers"][answer["table"]]
        pairs = [(c.get("package"), c.get("other")) for c in columns if isinstance(c, dict)]
        if len(pairs) != len(columns) or any(a not in ours or b not in theirs for a, b in pairs + [(key.get("package"), key.get("other"))]):
            raise Rejected(shared.REJECTION_REASONS[1])
        if len({a for a, _ in pairs}) != len(pairs) or len({b for _, b in pairs}) != len(pairs):
            raise Rejected(shared.REJECTION_REASONS[4])

def validate_answer(question, text):
    """The validators, in a fixed order: remove any thought block and code fence; take the last
    balanced JSON object; parse it strictly; check its shape, its letters, its quotations,
    the planted passages and self-contradiction. Returns ("accepted", answer) or
    ("rejected: <one reason from the fixed list>", None). Enforces: R3"""
    try:
        if not isinstance(text, str) or not text.strip():
            raise Rejected(shared.REJECTION_REASONS[0])
        for pattern in question.get("strip_patterns", ()):
            text = re.sub(pattern, "", text)
        text = re.sub(r"```[a-zA-Z]*", "", text)
        found = reading.last_json_object(text)
        try:
            answer = reading.strict_json(found) if found else None
        except ValueError:
            answer = None
        if not isinstance(answer, dict):
            raise Rejected(shared.REJECTION_REASONS[0])
        if question["question_type"] == "slice-rules":
            reading.validate_slice_rules(question, answer, Rejected)
        elif question["question_type"] == "package-plan":
            reading.validate_package_plan(question, answer, Rejected)
        elif question["question_type"] in JUDGE_RELATIONS:
            validate_judge(question, answer)
        else:
            validate_narrow(question, answer)
    except Rejected as problem:
        return "rejected: %s" % problem, None
    return "accepted", answer

_NOT_SHOWN = re.compile(r"\b(%s)\b" % "|".join(("sev" "er(e|ity)", "crit" "ical", "maj" "or", "min" "or", "err" "ors?", "find" "ings?",
                        "mater" "ial(ity)?", "(high|medium|low)[- ](risk|priority|impact|rating)", "non-?compl" "ian(t|ce)", "breach")), re.I)

def shown_ai_text(text):
    """Text written by the model passes the same plain-language filter as AIVA's own wording:
    if it rates seriousness or uses a policy term, a fixed sentence is shown instead and the
    full text stays in the audit records."""
    text = shared.normalise_text(str(text or ""))[:300]
    return shared.AI_WORDING_NOT_SHOWN if _NOT_SHOWN.search(text) else text

# ---------------------------------------------------------------- steps 07 and 09: judge-links
def needs_second_opinion(settings, target):
    """`unchecked_only`: a second, oppositely framed question is asked for accepted links that
    no deterministic check will back, that is, passages without a formula or a table."""
    mode = settings["second_opinion"]
    backed = bool(target.get("table")) or bool((target.get("equation") or {}).get("readable"))
    return mode == "all" or (mode == "unchecked_only" and not backed and target.get("heading_chain") is not None)

# ---------------------------------------------------------------- what each piece of code does, in plain words
INTERPRETED_KINDS = (shared.KIND_FUNCTION, shared.KIND_FORMULA, shared.KIND_TOPLEVEL, shared.KIND_TEST)

def package_outline(units, package):
    """The whole package in a few lines, as every interpretation question sees it: its name and
    title, then for each file the functions defined there with their arguments and the first
    line of their documentation, and the stored data. Also returns the documentation block of
    each unit, by the reference of the unit it documents."""
    described = {u["roxygen"]["documents_ref"]: u for u in units if u.get("roxygen") and u["roxygen"].get("documents_ref")}
    title = next((row["value"] for row in package.get("rows", []) if row.get("item") == "Title"), "")
    lines, by_file = ["Package %s %s: %s" % (package.get("name", ""), package.get("version", ""), title)], {}
    for unit in units:
        if unit["kind"] == shared.KIND_FUNCTION and not unit["inside"]:
            tags = described[unit["ref"]]["roxygen"]["tags"] if unit["ref"] in described else []
            says = next((tag["text"].split("\n")[0] for tag in tags if tag["tag"] in ("title", "description")), "")
            formals = ", ".join(name for name, _ in (unit.get("code") or {}).get("formals", []))
            by_file.setdefault(unit["file"], []).append("%s(%s)%s" % (unit["name"], formals, " - " + says if says else ""))
        elif unit["kind"] in (shared.KIND_TABLE, shared.KIND_OBJECT):
            by_file.setdefault(unit["file"], []).append("stored data %s" % unit["name"])
    return "\n".join(lines + ["%s: %s" % (file, "; ".join(by_file[file])) for file in sorted(by_file)]), described

def interpret_question(unit, functions, outline, described, references_dir, settings):
    """The question about one piece of code. The piece is shown whole; around it goes what a
    person would look up to understand it: the function a statement sits inside, the
    documentation the package gives, what calls it and what it calls, the stored data it reads,
    and the outline of the whole package cut around the piece's own name."""
    inside = functions.get(unit["inside"]) if unit["inside"] else None
    about, owner = [], inside or unit
    if inside is not None:
        about.append("This piece is one statement inside the function %s. The whole function:\n%s" % (inside["name"], cut_code(inside["text"], settings["max_unit_chars"])))
    if owner["ref"] in described:
        about.append("What the package's own documentation says:\n%s" % reading.cut_text(described[owner["ref"]]["text"], settings["max_passage_chars"]))
    code = owner.get("code") or {}
    callers = sorted(name for name, other in functions.items() if owner["name"] and owner["name"] in (other.get("code") or {}).get("calls", []))
    facts = [("It is called by", callers), ("Within this package it calls", sorted(c for c in code.get("calls", []) if c in functions)),
             ("It reads the stored data", sorted({r["object"] for r in code.get("reads_data", [])}))]
    about.extend("%s: %s." % (says, ", ".join(names)) for says, names in facts if names)
    about.append("The whole package:\n%s" % reading.cut_text(outline, 4000, keep_words=(owner["name"],)))
    where = "%s%s, %s%s" % (unit["kind"], " " + unit["name"] if unit["name"] else "", unit["file"],
                           " lines %d-%d" % tuple(unit["lines"]) if unit.get("lines") else "")
    blocks = [("THE PIECE OF CODE (%s)" % where, cut_code(unit["text"], settings["max_unit_chars"])),
              ("WHERE IT SITS IN THE PACKAGE", "\n\n".join(about))]
    return narrow_question("interpret-code", unit["ref"], blocks, references_dir, settings, more={"code_text": unit["text"]})

def interpret_code(ctx):
    """Step 07a, skill interpret-code. One question per function, formula statement, top-level
    statement and test block: what does this piece do, given where it sits in the package?
    Accepted answers fill the column "LLM Interpretation" of Chunks_Model. An interpretation
    is an aid to reading and nothing more: it gives no status, raises no flagged item and takes
    no part in the coverage identity, and a question that fails leaves a plain note. Enforces: R3"""
    units = ctx.read("model_units")
    if not ctx.settings.get("interpret_code", True):
        return shared.StepResult(messages=["Interpreting the code is switched off (setting interpret_code)."])
    outline, described = package_outline(units, (ctx.read("package_info") or [{}])[0])
    functions = {u["name"]: u for u in units if u["kind"] == shared.KIND_FUNCTION and not u["inside"]}
    questions, records = {}, []
    for unit in units:
        if unit["kind"] in INTERPRETED_KINDS and unit["text"].strip():
            question = interpret_question(unit, functions, outline, described, ctx.options["references_dir"], ctx.settings)
            if question["too_large"]:
                records.append({"unit_ref": unit["ref"], "interpretation": "", "question_id": "", "note": "Not asked: the question was too large to ask."})
            else:
                questions[question["question_id"]] = question
    answers = ctx.ask(list(questions.values())) if questions and ctx.ask else {}
    for question_id in sorted(questions, key=lambda key: questions[key]["unit_ref"]):
        final = answers.get(question_id)
        if final is not None and final["outcome"] == "accepted":
            records.append({"unit_ref": questions[question_id]["unit_ref"], "interpretation": final["answer"]["interpretation"].strip(),
                            "quote_from_unit": final["answer"]["quote_from_unit"], "question_id": question_id, "note": ""})
        else:
            reason = (final or {}).get("outcome", "failed: no answer was obtained").split(": ", 1)[-1]
            records.append({"unit_ref": questions[question_id]["unit_ref"], "interpretation": "", "question_id": question_id,
                            "note": "The AI's answer could not be used: %s." % reason})
    done = sum(1 for record in records if record["interpretation"])
    return shared.StepResult({"interpretations": sorted(records, key=lambda record: record["unit_ref"])},
                             counts={"pieces_of_code": len(records), "interpreted": done},
                             messages=["%d of %d pieces of code were given an interpretation by the AI." % (done, len(records))])

def judge_links(ctx):
    """Steps 07 and 09, skill judge-links. Builds one question per unit and corner, asks them
    through ask(), and turns ACCEPTED answers into `corresponds` edges with the relation
    word, the confidence, both quotations and the proposal reason. Rejected answers leave
    the unit without a link and are recorded for account-coverage. Enforces: R3, R4"""
    search_pass, settings = int(ctx.options.get("pass", 1)), ctx.settings
    world = build_world(ctx, search_pass)
    world["search_records"] = [r for r in ctx.read("search_records") if r["search_pass"] == search_pass]
    world["documented_by"] = {u["roxygen"]["documents_ref"]: u for u in world["units"] if u.get("roxygen") and u["roxygen"]["documents_ref"]}
    sources = dict(world["targets"]["model"], **{c["ref"]: c for c in world["doc"]})
    grouped = {}
    for candidate in ctx.read("candidates"):
        if candidate["search_pass"] == search_pass:
            grouped.setdefault((candidate["unit_ref"], candidate["target_corner"]), []).append(candidate)
    questions, skipped = {}, []
    for (unit_ref, corner) in sorted(grouped):
        question = judge_question(sources[unit_ref], corner, grouped[(unit_ref, corner)], world, ctx.options["references_dir"], settings)
        if question["too_large"]:
            skipped.append({"unit_ref": unit_ref, "target_corner": corner, "reason": "the question was too large to ask"})
        else:
            questions[question["question_id"]] = question
    answers = ctx.ask(list(questions.values())) if questions else {}
    edges, problems, records, doc_judgements, follow_ups = [], list(skipped), [], [], {}
    for question_id in sorted(questions):
        question, final = questions[question_id], answers.get(question_id)
        unit_ref, corner = question["unit_ref"], question["target_corner"]
        shown = len(question["letters"])
        if final is None or final["outcome"] != "accepted":
            reason = (final or {}).get("outcome", "failed: no answer was obtained").split(": ", 1)[-1]
            problems.append({"unit_ref": unit_ref, "target_corner": corner, "reason": reason, "question_id": question_id})
            records.append({"unit_ref": unit_ref, "target_corner": corner, "search_pass": search_pass,
                            "note": "%d passages were shown to the AI. Its answer could not be used: %s." % (shown, reason)})
            continue
        answer = final["answer"]
        if answer.get("states_nothing_checkable"):
            doc_judgements.append({"unit_ref": unit_ref, "states_nothing_checkable": True, "question_id": question_id})
        accepted = [m for m in answer["matches"] if m["letter"] not in question["planted"]]
        reasons = {c["target_ref"]: c["reason"] for c in grouped[(unit_ref, corner)]}
        for match in accepted:
            target = question["letters"][match["letter"]]
            how = shared.HOW_AI.format(confidence=match["confidence"])
            provenance = shared.to_plain(ctx.provenance)
            provenance.update(prompt_hash=question_id, response_hash=final["response_hash"])
            edges.append(dict(shared.to_plain(shared.Edge(unit_ref, target, "corresponds", how, ctx.provenance,
                         relation=shared.RELATION_WORDING[match["relation"]], confidence=match["confidence"],
                         evidence={"how_text": "%s. %s" % (how, reasons.get(target, "")), "question_id": question_id,
                                   "quote_from_passage": match["quote_from_passage"], "quote_from_unit": match["quote_from_unit"],
                                   "search_pass": search_pass})), provenance=provenance))
            linking = shared.RELATION_WORDING[match["relation"]] in shared.LINKING_RELATIONS
            if linking and match["relation"] not in ("deviates from", "inconsistent with") and needs_second_opinion(settings, world["targets"][corner][target]):
                follow_ups.setdefault((unit_ref, corner), []).append(target)
        linked = [m for m in accepted if shared.RELATION_WORDING[m["relation"]] in shared.LINKING_RELATIONS]
        note = "" if linked else "%d passages were shown to the AI. None accepted: %s" % (
            shown, "the AI's reason was \u201c%s\u201d" % shown_ai_text(answer.get("none_reason")) if answer.get("none_reason")
            else "the AI only saw passages on the same topic")
        records.append({"unit_ref": unit_ref, "target_corner": corner, "search_pass": search_pass, "note": note})
    opinions = second_opinions(ctx, follow_ups, sources, world) if follow_ups else []
    ledger = ledger_records(ctx.read("graph_ledger"), edges)
    return shared.StepResult({"graph_ledger": ledger, "judgement_problems": problems, "search_records": records,
                              "doc_judgements": doc_judgements, "second_opinions": opinions},
                             {"questions": len(questions), "links recorded": len(edges), "answers not usable": len(problems) - len(skipped),
                              "questions too large to ask": len(skipped)}, [])

def second_opinions(ctx, follow_ups, sources, world):
    """The oppositely framed question ("identify any difference ...") for links no check can
    back. A named difference with verbatim quotations is recorded; account-coverage turns
    it into a flagged item of the category "AI answers disagree"."""
    questions = {}
    for (unit_ref, corner), targets in sorted(follow_ups.items()):
        source, pool = sources[unit_ref], world["targets"][corner]
        text = reading.cut_text(source["text"], int(ctx.settings["max_unit_chars"]))
        passages = [(ref, passage_label(pool[ref]), passage_text(pool[ref], ctx.settings)) for ref in sorted(set(targets))]
        question = assemble_question("second-opinion", unit_ref, [("UNIT (%s)" % passage_label(source), text)], passages,
                                     reading.load_prompt(ctx.options["references_dir"], "second-opinion"), ctx.settings, more={"target_corner": corner})
        if not question["too_large"]:
            questions[question["question_id"]] = question
    answers, opinions = ctx.ask(list(questions.values())), []
    for question_id in sorted(questions):
        final, question = answers.get(question_id), questions[question_id]
        if final and final["outcome"] == "accepted":
            for difference in final["answer"]["differences"]:
                opinions.append({"unit_ref": question["unit_ref"], "target_ref": question["letters"][difference["letter"]],
                                 "quote_from_passage": difference["quote_from_passage"], "quote_from_unit": difference["quote_from_unit"],
                                 "what_differs": shown_ai_text(difference.get("what_differs")), "question_id": question_id})
    return opinions
