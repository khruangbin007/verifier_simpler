"""
standin_chat.py - a deterministic stand-in for chat(), for offline building and for
reviewers' sanity checks. Same signature and return shape as the real chat().

It reads the prompt the way the engine wrote it (QUESTION TYPE line, UNIT block, lettered
PASSAGES) and answers by simple, explainable rules. With misbehave=True it also gives
deliberately bad answers for prompts whose hash falls in fixed buckets, so that every
validator of the engine is exercised on every sample run:
    bucket 0  broken JSON             bucket 1  a letter that was not shown
    bucket 2  a paraphrased quotation bucket 3  agrees with everything (decoys included)
"""
import hashlib
import json
import re

STOP = set("the a an and or of to in is are be by for with as at on it this that from each which "
           "value values function return returns given using used use where when then than not any all "
           "its their shall must may can will into per under over between model package".split())
BUCKETS = 40
DEFAULT_RELATION = {"judge-unit-to-canon": "implements", "judge-unit-to-doc": "describes",
                    "judge-doc-to-canon": "consistent with", "judge-doc-to-model": "describes"}


def words_of(text):
    """Lower-case words of at least three letters, identifiers split at _ and ., stop words out."""
    found = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.]*", text or ""):
        for part in re.split(r"[_.]+|(?<=[a-z])(?=[A-Z])", token):
            part = part.lower()
            if len(part) >= 3 and part not in STOP:
                found.add(part[:-1] if part.endswith("s") and len(part) > 4 else part)
    return found


def numbers_of(text):
    return set(re.findall(r"(?<![\w.])\d+\.\d+", text or ""))


def block_after(prompt, label):
    match = re.search(re.escape(label) + r"[^\n]*\n<<<\n(.*?)\n>>>", prompt, re.S)
    return match.group(1) if match else ""


def passages_of(prompt):
    section = prompt.split("\nPASSAGES\n", 1)[1] if "\nPASSAGES\n" in prompt else ""
    return re.findall(r"\[([A-Z]{1,2})\] ([^\n]*)\n<<<\n(.*?)\n>>>", section, re.S)


def snippet(text, shared_words, length=6):
    """A verbatim run of words from `text` that starts at the first shared word."""
    tokens = list(re.finditer(r"\S+", text))
    for position, token in enumerate(tokens):
        if words_of(token.group(0)) & shared_words:
            last = tokens[min(position + length, len(tokens)) - 1]
            return text[token.start():last.end()]
    return text[:60]


def formula_score(unit, text, code=None):
    """How alike a formula-like passage and a unit are: shared short symbols (whatever their
    capital letters) and shared whole numbers of three digits or more."""
    in_words = any(phrase in text.lower() for phrase in ("product of", "sum of", "divided by"))
    if not in_words and ("=" not in text or not re.search(r"[-+*/^(]", text)):
        return 0
    small = {"a", "i", "in", "is", "of", "to", "if", "the", "and", "by", "f"}
    symbols = lambda t: {part.lower() for s in re.findall(r"(?<![\w.])[A-Za-z_]{1,6}(?![\w(])", t) for part in [s] + s.split("_")} - small
    if in_words:                                     # a formula stated in words: two shared symbols are enough
        return 3 if len(symbols(unit) & symbols(text)) >= 2 else 0
    integers = lambda t: set(re.findall(r"(?<![\w.])\d{3,}(?![\w.])", t))
    single = {s for s in symbols(text) if len(s) == 1}
    initials = {s[0] for s in symbols(unit if code is None else code) if len(s) > 1}       # names in the code itself, not in prose about it
    by_initial = len(single) if len(single) >= 2 and single <= initials else 0          # W for weight, R for rate: only when every letter fits
    return len(symbols(unit) & symbols(text)) + by_initial + 2 * len(integers(unit) & integers(text))


def judge(question_type, prompt, agree_with_all=False):
    unit = block_after(prompt, "UNIT") + "\n" + block_after(prompt, "WHAT THE PACKAGE SAYS ABOUT IT")
    unit_words, unit_numbers = words_of(unit), numbers_of(unit)
    scored, formulas = [], []
    for letter, _label, text in passages_of(prompt):
        shared_words = unit_words & words_of(text)
        score = len(shared_words) + 2 * len(unit_numbers & numbers_of(text))
        if agree_with_all or score >= 4:
            scored.append((score, letter, text, shared_words))
        elif formula_score(unit, text, block_after(prompt, "UNIT")) >= 3:
            formulas.append((formula_score(unit, text, block_after(prompt, "UNIT")), letter, text, shared_words))
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    formulas.sort(key=lambda entry: (-entry[0], entry[1]))
    matches = []
    for score, letter, text, shared_words in (scored if agree_with_all else scored[:2] + formulas[:1]):
        matches.append({"letter": letter, "relation": DEFAULT_RELATION[question_type],
                        "confidence": min(95, 50 + 5 * score),
                        "quote_from_passage": snippet(text, shared_words or words_of(text)),
                        "quote_from_unit": snippet(block_after(prompt, "UNIT"), shared_words or unit_words)})
    if matches:
        return {"matches": matches, "none_reason": ""}
    answer = {"matches": [], "none_reason": "No passage shares enough of the unit's wording or numbers."}
    if question_type == "judge-doc-to-canon" and not numbers_of(unit) and "=" not in unit:
        answer["states_nothing_checkable"] = len(unit_words) < 6
    return answer


def map_table_columns(prompt):
    package_header = [h.strip() for h in block_after(prompt, "PACKAGE TABLE").split("\n")[0].split(";")]
    best = None
    for letter, _label, text in passages_of(prompt):
        other_header = [h.strip() for h in text.split("\n")[0].split(";")]
        pairs = []
        for column in package_header:
            for other in other_header:
                if words_of(column) & words_of(other) and other not in [p["other"] for p in pairs]:
                    pairs.append({"package": column, "other": other})
                    break
        if len(pairs) >= 2 and (best is None or len(pairs) > len(best[1])):
            best = (letter, pairs)
    if best is None:
        return {"table": "NONE", "reason": "No table has matching headers."}
    return {"table": best[0], "columns": best[1], "key": best[1][0]}


def align_symbols(prompt):
    code = [s.strip() for s in block_after(prompt, "CODE SYMBOLS").split(",") if s.strip()]
    equation = [s.strip() for s in block_after(prompt, "EQUATION SYMBOLS").split(",") if s.strip()]
    pairs, used = [], set()
    for symbol in code:
        for other in equation:
            if other not in used and (symbol.lower() == other.lower() or symbol.lower().startswith(other.lower()[:2])):
                pairs.append({"code": symbol, "equation": other})
                used.add(other)
                break
    if len(pairs) < len(code):
        return {"alignment": [], "cannot_align": True}
    return {"alignment": pairs, "cannot_align": False}


def read_formula_from_prose(prompt):
    text = block_after(prompt, "PARAGRAPH")
    patterns = ((r"(\w+) (?:is|equals) the product of (\w+) and (\w+)", "%s = %s * %s"),
                (r"(\w+) (?:is|equals) the sum of (\w+) and (\w+)", "%s = %s + %s"),
                (r"(\w+) (?:is|equals) (\w+) divided by (\w+)", "%s = %s / %s"))
    for pattern, shape in patterns:
        match = re.search(pattern, text)
        if match:
            formula = shape % match.groups()
            floor = re.search(r"floored at (\d+(?:\.\d+)?)", text)
            if floor:
                left, right = formula.split(" = ")
                formula = "%s = max(%s, %s)" % (left, right, floor.group(1))
            return {"formula": formula, "no_formula_stated": False}
    return {"formula": "", "no_formula_stated": True}


def check_rule(prompt):
    rule, code = block_after(prompt, "RULE AS STATED"), block_after(prompt, "UNIT")
    for number in re.findall(r"\d+(?:\.\d+)?", rule):
        line = next((l for l in code.split("\n") if number in l and re.search(r"pmax|pmin|max|min|if", l)), "")
        if line:
            return {"outcome": "applied", "quote_from_passage": rule.strip()[:80], "quote_from_unit": line.strip()}
    return {"outcome": "not applied", "quote_from_passage": rule.strip()[:80], "quote_from_unit": ""}


def second_opinion(prompt, name_a_difference):
    passages = passages_of(prompt)
    if not name_a_difference or not passages:
        return {"differences": []}
    letter, _label, text = passages[0]
    unit = block_after(prompt, "UNIT")
    return {"differences": [{"letter": letter, "quote_from_passage": snippet(text, words_of(text)),
                             "quote_from_unit": snippet(unit, words_of(unit)),
                             "what_differs": "The two texts do not state the same thing."}]}




def slice_rules(main_prompt, misbehave=False):
    """Read the shape back out of the digest and answer it the way the prompt describes: a tag
    that occurs about as often as what it sits inside, holds short text of its own and is the
    first child of it, is the heading of it. Everything else that holds text is a paragraph,
    and everything else that holds other tags is a container. A misbehaving answer names a tag
    nobody showed it, which the validator has to refuse."""
    rows = {}
    for line in main_prompt.split("\n"):
        found = re.match(r"<([\w.:-]+)> x(\d+) depth ([\d-]+) \|(.*)$", line.strip())
        if not found:
            continue
        tag, count, rest = found.group(1), int(found.group(2)), found.group(4)
        holds = re.search(r"holds: ([^|]*)", rest)
        text_times = re.search(r"has own text (\d+) of \d+ times, averaging (\d+) characters", rest)
        first = re.search(r"is the first child (\d+) times", rest)
        rows[tag] = {"count": count, "holds": [p.strip() for p in holds.group(1).split(",") if p.strip()] if holds else [],
                     "with_text": int(text_times.group(1)) if text_times else 0,
                     "mean": int(text_times.group(2)) if text_times else 0,
                     "first_child": int(first.group(1)) if first else 0,
                     "known": "ALREADY READ AS" in rest}
    families, levels, why = {}, {}, {}
    for tag, row in rows.items():
        if row["known"]:
            continue                                 # a tag the reader already knows is left alone
        if row["holds"]:                             # a tag holding other tags is never a paragraph
            families[tag] = "container" if not (row["first_child"] and row["with_text"]) else "heading"
            if families[tag] == "heading":
                levels[tag] = 1
            continue
        if row["first_child"] and row["first_child"] >= row["count"] * 0.8 and row["with_text"] >= row["count"] * 0.8 and row["mean"] <= 60:
            families[tag] = "heading"
            levels[tag] = 1
            why[tag] = "it opens the block around it and holds a short name for it"
        elif row["holds"] and row["with_text"] * 2 < row["count"]:
            families[tag] = "container"
        elif row["with_text"]:
            families[tag] = "paragraph"
        else:
            families[tag] = "container"
    if misbehave:
        families["a-tag-nobody-showed"] = "heading"
    return {"families": families, "levels": levels, "why": why}


def trace_gap(main_prompt, misbehave=False):
    """The Tracer as a careful model plays it: where the place sets a value, declare what it is computed
    from - the names the tool knows, and the stored tables, that the code at the place uses - copying that
    code; once declared, done. Where it sets no value, look at the callers first, then give up with a
    reason. Misbehaving, it invents an action, which the validator has to refuse."""
    if misbehave:
        return {"action": "guess_the_answer", "args": {}}
    code = re.search(r"^code at this place: (.*)$", main_prompt, re.M).group(1)
    function = re.search(r"^function (\S+) \(", main_prompt, re.M).group(1)
    history = re.search(r"WHAT HAPPENED SO FAR\n<<<\n(.*?)\n>>>", main_prompt, re.S).group(1)   # the history alone, not the answer format after it
    if "declare_edge" in history or "declare_input" in history:
        return {"action": "done", "args": {"because": "what the value is computed from is declared"}}
    known = re.findall(r"^  (\S+) \((?:value|argument)\)", main_prompt, re.M)
    tables = [t.strip() for t in re.search(r"^stored tables: (.*)$", main_prompt, re.M).group(1).split(",")]
    assigned = re.match(r"\s*([A-Za-z_.][\w.]*)\s*<-", code)
    if assigned:
        inner = set(re.findall(r"function\(([^)]*)\)", code)[0].replace(" ", "").split(",")) if "function(" in code else set()
        sources = [n for n in known + tables if n != assigned.group(1) and n not in inner and re.search(r"(?<![\w.$])%s(?![\w.])" % re.escape(n), code)]
        if sources:
            return {"action": "declare_edge", "args": {"value": assigned.group(1), "from": sorted(set(sources)), "quote": code}}
    if "callers_of" not in history:
        return {"action": "callers_of", "args": {"function": function}}
    return {"action": "give_up", "args": {"because": "what it works on is built at run time"}}


def name_steps(main_prompt):
    """A plain name for every step, from its name and where it is set."""
    names = {}
    for step, name, where in re.findall(r"^\[(S\d+)\] (.+?), in ([^:]+):", main_prompt, re.M):
        names[step] = " ".join(("%s, set in %s" % (name.replace("_", " "), where)).split()[:12])
    return {"names": names}




def package_plan(main_prompt, misbehave=False):
    """Read the manifest back out of the prompt and give each unplaced member a reader, the way
    the prompt describes: by what its first lines look like. Only a line of the manifest itself
    counts - "path (N bytes) | ..." - so that the prompt's own wording about NOT PLACED is not
    mistaken for a file. A misbehaving answer leaves one member out, which the validator has to
    refuse."""
    readers, path, lines = {}, None, []
    row = re.compile(r"^(\S.*?) \((\d+) bytes\) \| (.*)$")
    for line in main_prompt.split("\n"):
        stripped = line.strip()
        found = row.match(stripped)
        if found:
            if path:
                readers[path] = reader_for(path, lines)
            path, lines = (found.group(1), []) if found.group(3).startswith("NOT PLACED") else (None, [])
        elif stripped.startswith("line: ") and path:
            lines.append(stripped[6:])
    if path:
        readers[path] = reader_for(path, lines)
    if misbehave and len(readers) > 1:
        readers.pop(sorted(readers)[0])              # one member left out
    return {"readers": readers, "why": {path: "by what its first lines look like" for path in readers}}


def reader_for(path, lines):
    body = "\n".join(lines)
    if re.search(r"<-|function\s*\(", body):
        return "r-source"
    if "\\name{" in body or "\\alias{" in body:
        return "help-page"
    if body.startswith("---") or "```" in body:
        return "vignette"
    if lines and all(line.count(",") >= 1 for line in lines[:3]):
        return "table-file"
    return "prose"


def answer_for(system_prompt, main_prompt, misbehave):
    match = re.search(r"QUESTION TYPE: ([a-z-]+)", main_prompt)
    question_type = match.group(1) if match else "self-test"
    bucket = int(hashlib.sha256(main_prompt.encode("utf-8")).hexdigest()[:8], 16) % BUCKETS
    if question_type in DEFAULT_RELATION:
        if misbehave and bucket == 0:
            return '{"matches": [{"letter": "A", "relation": "implements", '          # cut off: broken JSON
        answer = judge(question_type, main_prompt, agree_with_all=misbehave and bucket == 3)
        if misbehave and bucket == 1:
            answer = {"matches": [{"letter": "ZZ", "relation": DEFAULT_RELATION[question_type], "confidence": 80,
                                   "quote_from_passage": "x", "quote_from_unit": "y"}], "none_reason": ""}
        if misbehave and bucket == 2 and answer["matches"]:
            answer["matches"][0]["quote_from_passage"] = "in other words, roughly the same idea"
        return json.dumps(answer)
    if question_type == "map-table-columns":
        answer = map_table_columns(main_prompt)
        if misbehave and bucket in (0, 1) and answer.get("columns"):
            answer["columns"][0]["other"] = "a column that does not exist"
        return json.dumps(answer)
    if question_type == "align-symbols":
        return json.dumps(align_symbols(main_prompt))
    if question_type == "read-formula-from-prose":
        return json.dumps(read_formula_from_prose(main_prompt))
    if question_type == "trace-gap":
        return json.dumps(trace_gap(main_prompt, misbehave and bucket == 3))
    if question_type == "name-steps":
        return json.dumps(name_steps(main_prompt))
    if question_type == "check-rule":
        return json.dumps(check_rule(main_prompt))
    return json.dumps({"ok": True})


def make_chat(misbehave=True):
    def chat(SystemPrompt, MainPrompt):
        return {"answer": answer_for(SystemPrompt, MainPrompt, misbehave)}
    return chat


chat = make_chat(misbehave=True)                 # the stand-in the notebook switch selects
chat_well_behaved = make_chat(misbehave=False)   # for tests that need one stable outcome
