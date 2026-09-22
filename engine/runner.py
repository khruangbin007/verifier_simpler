"""
Verifier 0.0.2 - runner.py - the run: its folder, its record, the model calls, the workbook and
the report. For Reviewer 5.

WHAT THIS FILE DOES
  Where a run lives (Run_<date>_<time> under the project, the two deliverables in it, the record
  of three files in _audit/ beside them, scratch space on the driver). The store that writes that
  record and syncs it whole. The wrapper around chat(): recording every exchange, retrying,
  pausing for a fresh token or for a person, replaying recorded answers so that a run can be
  reproduced without a model. pipeline.yaml read and refused if it names a function this engine
  does not offer. Each step run in order, a step that cannot finish written down and the run going
  on. After every step: Output.xlsx rebuilt (never over an edited copy that has not been read in)
  and Validation_Report.docx rebuilt. The determinations a person writes into the yellow columns
  read back by item id, appended, never overwritten. And the verification of an evidence pack:
  fingerprints of the inputs, the engine files that produced it, the content hashes, both hash
  chains, and that no token was ever written into the folder.

WHAT IT TAKES IN AND PRODUCES
  In: a Projects folder, a model id, the widgets' values, a chat(), the live token.
  Out: the run folder; every record; Output.xlsx; Validation_Report.docx; the verification.

WHICH SHEETS SHOW ITS RESULTS
  All of them: this file writes the workbook. The run manifest is manifest.json in _audit/.

DESIGN RULES ENFORCED HERE
  R2  a step that fails is written down and the run goes on; a pause is a pause, not a failure
  R4  the determinations are a hash chain; an evidence pack verifies from its own three files
  R5  a run replays from its recorded answers; the release manifest pins the code that ran
  R6  inputs are never touched; an edited workbook is never overwritten before it is read in
  R8  no setting can hold the token, and no token is ever written to the run folder
  R11 only the functions in STEP_FUNCTIONS can be named by pipeline.yaml
  R12 build on local disk, copy whole files, keep the file count small, sync after every step

HOW TO SANITY-CHECK IT
  Run tests/test_runner.py, tests/test_end_to_end.py and tests/test_run_goes_on.py. Run cells 3
  to 5 on a sample project with the stand-in, then read the verification cell 5 prints: every
  line should say Confirmed.
"""

from dataclasses import dataclass, field, replace
import concurrent.futures
import datetime
import getpass
import gzip
import inspect
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback

import yaml

import core
import reading
import review

# ================================================================================================
# ---------------------------------------------------------------- from verifier5_run_report
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))

class RunPaused(Exception):
    """The run stopped on purpose and can be resumed. The message tells the person what to do."""

# ---------------------------------------------------------------- settings (allow-list)
DEFAULT_SETTINGS = {
    "k_candidates": 12, "concurrency_limit": 4, "token_cap": 40000, "answer_reserve": 1500,
    "thinking_reserve": 0, "safety_margin": 0.15, "prompt_target_tokens": 6000,
    "max_attempts": 3, "breaker_after_failures": 8, "retry_wait_seconds": 2.0,
    "token_lifetime_minutes": 14.0, "token_wait": "wait", "foreground_minutes": 0.0,
    "sync_every_calls": 100, "llm_file_roll_mb": 25.0, "require_outline_confirmation": True,
    "second_opinion": "unchecked_only", "judge_supporting_code": False,
    "max_parameter_cells": 5000, "max_parameter_columns": 50, "protect_sheets": True,
    "system_prompt_prefix": "", "strip_patterns": [r"(?s)<think>.*?</think>", r"(?s)<thought>.*?</thought>",
                                                   r"(?s)<\|channel\|>thought.*?<\|channel\|>"],
    "numeric_points": 200, "numeric_seed": 20260917, "min_valid_points": 50,
    "relative_tolerance": 1e-9, "trivial_numbers": ["0", "1", "2", "-1", "10", "100"],
    "bm25_k1": 1.2, "bm25_b": 0.75, "anchor_max_share": 0.10, "walk_restart": 0.25,
    "walk_rounds": 30, "heading_anchor_cap": 0.5, "rrf_constant": 60, "reserved_places": 2,
    "max_unit_chars": 3000, "max_passage_chars": 1100, "max_file_mb": 200.0, "reviewer_id": "", "read_pictures": True, "interpret_code": True, "agentic_reading": "off",
    "signals": ["concepts", "fields", "bridge", "references", "anchors", "signatures", "propagation"],
    "concept_subject": "", "concept_weight": 2.0, "concept_batch": 8, "concept_candidates_max": 40, "concepts_with_ai": True}

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
LONGEST_AUDIT_NAME = "Validation_Report.docx"
PATH_BUDGET = 100

@dataclass
class RunPaths:
    """Where one run lives. Output.xlsx and Validation_Report.docx sit in run_dir itself; _audit/
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
    for _, folder, readme in core.INPUT_FOLDERS:
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
    place = core.sha256_text(os.path.abspath(run_dir))[:8]       # two Projects folders never share scratch space
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
RECORDS_FILE, CALLS_FILE, MANIFEST_FILE = "records.jsonl", "calls.jsonl.gz", "manifest.json"

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
    """The record of a run, in three files. Everything is read and written on local disk and
    sync() copies whatever changed, whole, into _audit/ in the run folder.

        records.jsonl    every record of every kind, one per line, each as {"kind", "record"},
                         in the order written and never rewritten
        calls.jsonl.gz   every exchange with the model, gzip, one record per line
        manifest.json    the run manifest, the coverage account and the package description,
                         each rewritten whole under its own key

    Three files, so that an evidence pack can be checked, copied and archived without anyone
    having to know which of thirty file names mattered. Enforces: R4, R5, R12"""
    local_dir: str; remote_dir: str
    synced: dict = field(default_factory=dict)
    cache: list = field(default_factory=list)      # records.jsonl as read, so a read does not re-parse the file
    cached_size: int = 0                            # bytes of records.jsonl already parsed into the cache

    def path(self, name):
        return os.path.join(self.local_dir, name)

    def records(self):
        """Every complete line of records.jsonl, parsed once: only the bytes written since the
        last read are parsed, and only up to the last line break. A line that is still being
        written by the run's own thread (cell 4 reads while it writes) is left for the next
        read rather than raising. The file only ever grows, so a shorter file means a fresh run
        of the same folder and the cache starts again."""
        target = self.path(RECORDS_FILE)
        size = os.path.getsize(target) if os.path.exists(target) else 0
        if size < self.cached_size:
            self.cache, self.cached_size = [], 0
        if size > self.cached_size:
            with open(target, "rb") as handle:
                handle.seek(self.cached_size)
                new = handle.read(size - self.cached_size)
            complete = new.rfind(b"\n") + 1
            if complete:
                self.cache.extend(json.loads(line) for line in new[:complete].decode("utf-8").split("\n") if line.strip())
                self.cached_size += complete
        return self.cache

    def manifest(self):
        target = self.path(MANIFEST_FILE)
        if not os.path.exists(target):
            return {}
        with open(target, encoding="utf-8") as handle:
            return json.load(handle)

    def read(self, kind):
        """Every record of one kind, in the order written."""
        if kind == "llm_calls":
            return self.read_calls()
        if kind in AUDIT_OBJECTS:
            found = self.manifest().get(kind)
            return [found] if found is not None else []
        return [line["record"] for line in self.records() if line["kind"] == kind]

    def append(self, kind, records):
        """Append records of one kind; the three single-object kinds are rewritten whole."""
        if kind in AUDIT_OBJECTS:
            whole = self.manifest()
            whole[kind] = core.to_plain(records[-1])
            partial = self.path(MANIFEST_FILE + ".writing")   # written beside, then swapped in: a reader in
            with open(partial, "w", encoding="utf-8") as handle:  # the other thread never sees a half-written file
                handle.write(json.dumps(whole, sort_keys=True, indent=1, ensure_ascii=False))
            os.replace(partial, self.path(MANIFEST_FILE))
            return
        with open(self.path(RECORDS_FILE), "a", encoding="utf-8") as handle:
            for record in records:
                handle.write(core.canonical_json({"kind": kind, "record": core.to_plain(record)}) + "\n")

    def append_calls(self, records):
        """Call records go to one gzip file. Its header carries no time stamp, so the same records
        always give the same bytes; gzip members are appended, and read back as one stream."""
        with open(self.path(CALLS_FILE), "ab") as raw:
            with gzip.GzipFile(filename="", mode="ab", fileobj=raw, mtime=0) as handle:
                for record in records:
                    handle.write((core.canonical_json(record) + "\n").encode("utf-8"))

    def read_calls(self):
        """Every call record of the run, in the order written."""
        target = self.path(CALLS_FILE)
        if not os.path.exists(target):
            return []
        with gzip.open(target, "rt", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def sync(self):
        """Copy each of the three files that changed since the last sync, whole. Returns what was copied."""
        copied = []
        for name in (RECORDS_FILE, CALLS_FILE, MANIFEST_FILE):
            source = self.path(name)
            if not os.path.exists(source):
                continue
            stamp = (os.path.getsize(source), os.stat(source).st_mtime_ns)
            if self.synced.get(name) == stamp:
                continue
            copy_whole(source, os.path.join(self.remote_dir, name))
            self.synced[name] = stamp
            copied.append(name)
        return copied

    def restore(self):
        """On resume: copy the run folder's three files back to local disk first."""
        if os.path.isdir(self.remote_dir) and not os.path.exists(self.path(MANIFEST_FILE)):
            for name in (RECORDS_FILE, CALLS_FILE, MANIFEST_FILE):
                if os.path.exists(os.path.join(self.remote_dir, name)):
                    copy_whole(os.path.join(self.remote_dir, name), self.path(name))

def open_store(paths, settings):
    """The audit store of a run, restored from the run folder when local scratch is empty."""
    store = AuditStore(paths.local_dir, paths.audit_dir)
    store.restore()
    return store

# ---------------------------------------------------------------- the wrapper around chat()
AUTH_WORDS = ("401", "403", "unauthor", "expired", "forbidden", "invalid token", "authentication", "credential")
OVERLOAD_WORDS = ("429", "502", "503", "504", "overload", "rate limit", "too many", "timeout", "timed out", "busy")

def classify_failure(text):
    """Sort a failure into a class by the words it contains (probe P-13 matches these lists to
    what the real gateway returns). call_chat adds one more class of its own, "truncated"."""
    lowered = (text or "").lower()
    if any(word in lowered for word in AUTH_WORDS):
        return "authentication"
    if any(word in lowered for word in OVERLOAD_WORDS):
        return "overload"
    return "other"

class ChatOutcome(tuple):
    """What one call to chat() came to. It unpacks as the three values the rest of the tool has
    always read - (answer text or None, failure class or "", what was seen with tokens
    removed) - and carries the gateway's own record of the call as .meta, so that adding
    metadata did not change a single existing call site."""

    def __new__(cls, answer, failure, seen, meta=None):
        outcome = super().__new__(cls, (answer, failure, seen))
        outcome.meta = dict(meta or {})
        return outcome

    answer = property(lambda self: self[0])
    failure = property(lambda self: self[1])
    seen = property(lambda self: self[2])

# Fields of the gateway's reply that are worth keeping in the audit record. The reply also
# echoes the prompts back (query, defaultprompt, source) and those are dropped: the tool already
# stores the prompts it sent, and an echo would double the size of every call record.
META_FIELDS = ("chat_id", "thread_id", "prompt_id", "datetime", "user_id", "intent")
RESPONSE_META_FIELDS = ("id", "model", "created", "system_fingerprint", "service_tier")
USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")

def first_choice(response):
    """The first choice of an OpenAI-shaped reply, or an empty dictionary."""
    nested = response.get("response") if isinstance(response.get("response"), dict) else {}
    choices = nested.get("choices")
    return choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}

def chat_metadata(response):
    """What the gateway said about the call itself: which conversation it belonged to, which
    model answered, how many tokens it took and why it stopped. Kept for the audit record so
    that a run can be accounted for afterwards; none of it reaches a status or a check."""
    meta = {name: response[name] for name in META_FIELDS if response.get(name) not in (None, "")}
    nested = response.get("response") if isinstance(response.get("response"), dict) else {}
    meta.update({name: nested[name] for name in RESPONSE_META_FIELDS if nested.get(name) not in (None, "")})
    usage = nested.get("usage") if isinstance(nested.get("usage"), dict) else {}
    meta.update({name: usage[name] for name in USAGE_FIELDS if isinstance(usage.get(name), int)})
    choice = first_choice(response)
    if choice.get("finish_reason"):
        meta["finish_reason"] = choice["finish_reason"]
    return meta

def answer_text_of(response):
    """The generated text. The gateway puts it under "answer"; if that key is missing or
    empty, the same text is read from the OpenAI-shaped part of the reply, so that a
    gateway that only fills one of the two is still usable."""
    if isinstance(response.get("answer"), str) and response["answer"].strip():
        return response["answer"]
    content = first_choice(response).get("message", {})
    content = content.get("content") if isinstance(content, dict) else None
    return content if isinstance(content, str) and content.strip() else None

def summarise_response(response, live):
    """A failed reply, shortened for the audit record: the fields that say what went wrong,
    without the echoed prompts. Falls back to the whole reply when it has no known shape."""
    if not isinstance(response, dict):
        return live.redact(json.dumps(response, default=str)[:2000])
    keep = ("status", "code", "message", "detail", "reason", "answer", "finish_reason")
    kept = {name: response[name] for name in keep if name in response}
    kept.update(chat_metadata(response))
    if not kept:
        kept = {name: value for name, value in response.items()
                if name not in ("query", "defaultprompt", "source", "documents", "history")}
    return live.redact(json.dumps(kept, default=str)[:2000])

def accepts_history(chat):
    """Whether the analyst's chat() takes the third `history` argument. The real gateway cell
    has the signature chat(SystemPrompt, MainPrompt, history=[]); the stand-in and the older
    cell take two arguments. The tool works with either and never depends on which."""
    try:
        parameters = inspect.signature(chat).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return "history" in parameters
    positional = [p for p in parameters.values()
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    return "history" in parameters or len(positional) >= 3

def call_chat(chat, system_prompt, main_prompt, live):
    """Call chat() once and bring every way a failure can surface (an exception; a dictionary
    that carries a status or code; a dictionary with no answer in either place; an answer the
    model was cut off in the middle of) into one shape. Returns a ChatOutcome, which unpacks
    as (answer, failure, seen).

    History is always sent empty. Every question the tool asks is self-contained and is asked in
    its own call, so nothing the model said about an earlier unit may colour the next one;
    an empty history is also what makes a question repeatable. Enforces: R5"""
    try:
        response = chat(system_prompt, main_prompt, []) if accepts_history(chat) else chat(system_prompt, main_prompt)
    except Exception as problem:                     # shape 1: chat() raised
        seen = live.redact("%s: %s" % (type(problem).__name__, problem))
        return ChatOutcome(None, classify_failure(seen), seen)
    if isinstance(response, str):                    # a gateway that returns the text alone
        response = {"answer": response}
    if not isinstance(response, dict):
        seen = live.redact(json.dumps(response, default=str)[:2000])
        return ChatOutcome(None, classify_failure(seen), seen)
    meta, text = chat_metadata(response), answer_text_of(response)
    if text is None:                                 # shapes 2 and 3: a reply with no answer
        seen = summarise_response(response, live)
        return ChatOutcome(None, classify_failure(seen), seen, meta)
    if meta.get("finish_reason") == "length":        # shape 4: the answer stops in mid-air
        seen = "the model was cut off at the token limit; the answer is incomplete"
        return ChatOutcome(None, "truncated", seen, meta)
    return ChatOutcome(live.redact(text), "", "", meta)

@dataclass
class AskState:
    """What the workers of one run share: the pause and stop switches, the consecutive-
    failure count of the circuit breaker, and the generation of the token that failed."""
    control: dict = field(default_factory=lambda: {"pause": False, "stop": False})
    consecutive_failures: int = 0; failed_generation: int = -1; waiting_for_token: bool = False
    deadline: float = 0.0; calls_made: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

def wait_until_allowed(state, live, settings, sleep):
    """Called before every call. Blocks while the run is paused or while a fresh token is
    awaited; raises RunPaused when the run must stop by itself (mode C, stop switch)."""
    while True:
        if state.control.get("stop"):
            raise RunPaused("The run was stopped on request. Run the cell again to resume.")
        if state.deadline and time.time() > state.deadline:
            raise RunPaused("The time box of this foreground run is over. Paste a fresh token "
                            "and run the cell again; no call will be repeated.")
        # Only a call the gateway actually refused for authentication makes the run wait for a fresh
        # token. A token's age alone never does: a run once sat waiting, silently, with a token that
        # still worked, because it was older than token_lifetime_minutes. Age is shown in cell 4 as a
        # hint and nothing more.
        needs_token = state.failed_generation == live.generation
        state.waiting_for_token = bool(needs_token)
        if not needs_token and not state.control.get("pause"):
            return
        if needs_token and settings["token_wait"] == "stop":
            raise RunPaused("Paste a fresh token, then run the cell again; no call will be repeated.")
        sleep(0.05)

def ask_one(question, chat, live, settings, validate, state, sleep):
    """Ask one question until it has a final outcome. Every attempt is recorded. An
    authentication-like failure pauses all workers until a fresh token arrives and does
    not count against the attempts. Enforces: R3"""
    records, attempt = [], 0
    system_prompt = settings["system_prompt_prefix"] + question["system_prompt"]
    while True:
        wait_until_allowed(state, live, settings, sleep)
        generation = live.generation
        started, clock = datetime.datetime.now().isoformat(timespec="seconds"), time.time()
        with state.lock:
            state.calls_made += 1
        outcome_of_call = call_chat(chat, system_prompt, question["main_prompt"], live)
        answer_text, failure, seen = outcome_of_call
        attempt += 1
        outcome, answer = ("failed: " + failure, None) if failure else validate(question, answer_text)
        with state.lock:
            state.consecutive_failures = state.consecutive_failures + 1 if failure else 0
            breaker_open = state.consecutive_failures >= settings["breaker_after_failures"]
            if failure == "authentication":
                state.failed_generation = generation
        final = outcome == "accepted" or (attempt >= settings["max_attempts"] and failure != "authentication")
        records.append({
            "question_id": question["question_id"], "question_type": question["question_type"],
            "unit_ref": question.get("unit_ref", ""), "attempt": len(records) + 1,
            "letters": question.get("letters", {}), "planted": question.get("planted", []),
            "prompt_hash": question["question_id"], "response_hash": core.sha256_text(answer_text or seen),
            "system_prompt": live.redact(system_prompt), "main_prompt": live.redact(question["main_prompt"]),
            "response_text": answer_text if answer_text is not None else seen, "outcome": outcome,
            "answer": answer, "final": final, "started_at": started,
            "seconds": round(time.time() - clock, 3), "estimated_tokens": question.get("estimated_tokens", 0),
            "gateway": outcome_of_call.meta})
        if final:
            return records
        if failure == "authentication":
            attempt -= 1
        elif breaker_open:
            raise RunPaused("Many calls in a row failed, so the run paused itself to avoid wasting "
                            "calls. Check the gateway, then run the cell again to resume.")
        elif failure:
            sleep(settings["retry_wait_seconds"] * attempt)

def run_batch(batch, chat, live, settings, validate, state, sleep):
    """Ask one batch of questions with a thread pool. Results are gathered in the order of
    the questions, never in the order threads finished. Enforces: R5"""
    finished, paused = {}, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(settings["concurrency_limit"]))) as pool:
        futures = [(q["question_id"], pool.submit(ask_one, q, chat, live, settings, validate, state, sleep))
                   for q in batch]
        for question_id, future in futures:
            try:
                finished[question_id] = future.result()
            except RunPaused as pause:
                paused = paused or pause
                state.control["stop"] = True           # let the other workers end after their call
    if paused:
        state.control["stop"] = False
    return finished, paused

def make_asker(chat, live, store, settings, validate, state=None, sleep=time.sleep):
    """Build ask(), the only place chat() is ever called. ask(questions) returns a dictionary
    question id -> final record. A question that already has a final record in this run is
    never asked again, which is what makes resume safe. Enforces: R3, R5"""
    state = state or AskState()
    if settings["foreground_minutes"]:
        state.deadline = time.time() + 60.0 * settings["foreground_minutes"]

    def ask(questions):
        done = {r["question_id"]: r for r in store.read_calls() if r.get("final")}
        unique = {q["question_id"]: q for q in questions}
        todo = [unique[qid] for qid in sorted(unique) if qid not in done]
        size = max(1, int(settings["sync_every_calls"]))
        for start in range(0, len(todo), size):
            finished, paused = run_batch(todo[start:start + size], chat, live, settings, validate, state, sleep)
            records = [r for qid in sorted(finished) for r in finished[qid]]
            store.append_calls(records)
            store.sync()
            done.update({r["question_id"]: r for r in records if r["final"]})
            if paused:
                raise paused
        return {qid: done[qid] for qid in unique if qid in done}
    ask.state = state
    return ask

def replay_chat(call_records):
    """A chat() that answers from the recorded answers of an earlier run. Running the
    pipeline with it must reproduce the same graph version id, statuses and items, which
    is what reproducibility means for a model that samples its answers. Enforces: R5"""
    recorded = {}
    for record in call_records:
        recorded.setdefault((record["system_prompt"], record["main_prompt"]), []).append(record["response_text"])
    position = {}
    lock = threading.Lock()

    def chat(system_prompt, main_prompt):
        key = (system_prompt, main_prompt)
        with lock:
            index = position.get(key, 0)
            position[key] = index + 1
        answers = recorded.get(key)
        if not answers:
            return {"status": "no recorded answer for this prompt"}
        return {"answer": answers[min(index, len(answers) - 1)]}
    return chat

# ---------------------------------------------------------------- the pipeline runner
CHAT_STEPS = ("read-methodology", "read-documentation", "read-package", "interpret-code", "judge-concepts", "judge-links",
              "check-mathematics", "check-values", "check-rules")
REPEATABLE_STEPS = ("record-determinations", "build-report")
HUMAN_MESSAGES = {
    "confirm-outline": "Waiting for a person: check Level and Section (heading chain) on Chunks_Canon "
                       "against the methodology's own outline, then run cell 4 to confirm.",
    "await-determinations": "Waiting for a person: download Output.xlsx from the run folder, fill the four "
                            "yellow columns on Flagged_Items, put it back in the run folder and run cell 5."}

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

def read_scope_column(path, known_refs):
    """The "Use in review" cell of every row of the three Chunks sheets, by unit reference and
    never by row position. Returns {ref: "to use" | "to not use"} for the cells that hold one of
    the two words; anything else written there is ignored and said so."""
    import openpyxl
    found, ignored = {}, []
    book = openpyxl.load_workbook(path, read_only=True)
    for name in ("Chunks_Canon", "Chunks_Doc", "Chunks_Model"):
        if name not in book.sheetnames:
            continue
        rows = list(book[name].iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(cell or "") for cell in rows[0]]
        if "Use in review" not in header or "Ref" not in header:
            continue
        at_ref, at_scope = header.index("Ref"), header.index("Use in review")
        for row in rows[1:]:
            ref, word = str(row[at_ref] or "").strip(), str(row[at_scope] or "").strip().lower()
            if not word or ref not in known_refs:
                continue
            if word in core.SCOPE_WORDS:
                found[ref] = word
            else:
                ignored.append("%s: '%s' is not one of %s and was ignored" % (ref, word, " / ".join(core.SCOPE_WORDS)))
    return found, ignored

def confirm_outline(paths, settings, reviewer):
    """Record that a person has checked the outline of the methodology (notebook cell 4), and
    read back what they wrote in the "Use in review" column of the three Chunks sheets: a unit
    marked "to not use" is left out of the search, the links and the checks, and ends with the
    status Not in scope. The decisions are a hash chain, like the determinations."""
    store = open_store(paths, settings)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    known = {r["ref"] for kind in ("chunks_canon", "chunks_doc", "model_units") for r in store.read(kind)}
    decisions, ignored, workbook = {}, [], os.path.join(paths.outputs_dir, "Output.xlsx")
    if os.path.exists(workbook):
        try:
            decisions, ignored = read_scope_column(workbook, known)
        except Exception as problem:                 # a workbook that cannot be opened is said, never a stopped cell (R2)
            ignored.append("Output.xlsx could not be opened (%s); no scope decisions were read" % type(problem).__name__)
    records = [{"unit_ref": ref, "decision": word, "recorded_at": now, "reviewer_id": reviewer or "not named"}
               for ref, word in sorted(decisions.items())]
    chained = core.chain_records(core.chain_head(store.read("scope_decisions")), records)
    if chained:
        store.append("scope_decisions", chained)
    update_manifest(store, {"outline_confirmed_by": reviewer or "not named", "outline_confirmed_at": now})
    store.sync()
    out = sum(1 for word in decisions.values() if word == core.SCOPE_WORDS[1])
    said = ["Recorded: the outline was confirmed by %s." % (reviewer or "a person who gave no name"),
            "Scope: %d unit(s) marked to not use%s." % (out, "; they will not be searched, linked or checked" if out else "")]
    return "\n".join(said + ignored)

def human_step_open(step, store, settings, determinations):
    """Is this human step still waiting for its person?"""
    if step["name"] == "confirm-outline":
        manifest = (store.read("run_manifest") or [{}])[0]
        return settings["require_outline_confirmation"] and not manifest.get("outline_confirmed_by")
    return not determinations and not store.read("determinations")

def run_pipeline(paths, settings, chat=None, live=None, determinations=False, stop_after="",
                 state=None, keep_alive=None, sleep=time.sleep):
    """Run, or resume, the pipeline. Each finished step leaves a step record; called again,
    the run continues at the first step without one. A human step stops the run and says
    what the person should do. Returns {"state", "message", "steps_run"}."""
    store = open_store(paths, settings)
    pipeline = load_pipeline()
    live = live or LiveValues()
    done = {record["step_id"] for record in store.read("step_records")}
    steps_run = []
    if determinations and "15" not in done:
        return {"state": "not ready", "steps_run": [], "message":
                "Determinations can be recorded once the run has reached its flagged items."}
    for step in pipeline["steps"]:
        if stop_after and step["id"] > stop_after:
            break
        if step["name"] in REPEATABLE_STEPS:
            if not determinations:
                continue                     # these two run each time the determinations cell is run
        elif step["id"] in done:
            continue
        if step.get("human"):
            if human_step_open(step, store, settings, determinations):
                rebuild_outputs(store, paths, settings, HUMAN_MESSAGES[step["name"]])
                return {"state": "waiting for a person", "message": HUMAN_MESSAGES[step["name"]], "steps_run": steps_run}
            record_step(store, step, core.StepResult(), 0.0)
            continue
        try:
            run_step(step, store, paths, settings, chat, live, state, sleep)
        except RunPaused as pause:
            store.sync()
            return {"state": "paused", "message": str(pause), "steps_run": steps_run}
        steps_run.append(step["name"])
        if keep_alive:
            keep_alive()
        if stop_after and step["id"] == stop_after:
            break
    message = "Every step has run." if not stop_after else "Stopped after step %s as asked." % stop_after
    rebuild_outputs(store, paths, settings, message)
    return {"state": "finished", "message": message, "steps_run": steps_run}

def run_step(step, store, paths, settings, chat, live, state, sleep):
    """Build the context, call the step function, write what it returns, record the step,
    rebuild the outputs and sync. Steps never touch the store themselves."""
    notes = []
    ask = None
    if step["name"] in CHAT_STEPS and chat is not None:
        ask = make_asker(chat, live, store, settings, review.validate_answer, state, sleep)
    provenance = core.Provenance(paths.run_id, step["id"], step["name"], step["version"],
                                   created_at=datetime.datetime.now().isoformat(timespec="seconds"))
    options = dict(step.get("with") or {})
    options.update({"inputs": core.list_input_files(paths.inputs_dir), "paths": paths,
                    "run": {"model_id": paths.model_id, "project_date": paths.project_date, "run_id": paths.run_id}})
    work_dir = os.path.join(paths.local_dir, "work")
    os.makedirs(work_dir, exist_ok=True)
    context = core.StepContext(settings, options, store.read, ask, work_dir, notes.append, provenance)
    function = STEP_FUNCTIONS[step["carried_out_by"]]
    started = time.time()
    try:
        result = function(context)
    except RunPaused:
        raise                                        # a pause is how a run waits for a person; it is not a failure
    except Exception as problem:                     # a step that fails is written down, never a stopped run (R2)
        result = core.StepResult({}, {"step did not finish": 1}, [step_failure(step, problem, work_dir)])
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
            "bytes": len(data), "sha256": core.sha256_bytes(data), "swhid": core.swhid_content(data)}

def engine_file_hashes():
    """SHA-256 of every file that makes up the engine (its code, which now holds its prompts and
    reference data, the pipeline and the requirements), so that an evidence pack names exactly the
    code that produced it - the same list as engine/release.json."""
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
    for corner, _, _ in core.INPUT_FOLDERS:
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
    manifest = dict(ctx.options["run"], engine_version=core.ENGINE_VERSION, versions=versions, engine_files=engine_file_hashes(),
                    settings=ctx.settings, inputs=fingerprints, changes_since_previous_run=changes,
                    previous_run=previous["run_id"] if previous else "",
                    started_at=datetime.datetime.now().isoformat(timespec="seconds"))
    return core.StepResult({"run_manifest": [manifest]}, {"input files": len(fingerprints)},
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
COVERAGE_ROWS = (("model", "Model units (one row each on Mapping_Model_to_Canon_and_Doc)"),
                 ("doc", "Documentation units (one row each on Mapping_Doc_to_Canon_and_Model)"),
                 ("canon", "Methodology passages (for information only)"))
NEEDS_ATTENTION_MEANS = ("Needs attention = units whose status is not clean; each has an entry on Flagged_Items.")

def quoted(text, citation=""):
    """Text taken from an input or from the AI is always shown visibly quoted, with its
    citation. The wording rules apply to the tool's own words, not to quotations. Enforces: R1"""
    inner = (text or "").replace("\u201c", '"').replace("\u201d", '"')
    return "\u201c%s\u201d%s" % (inner, " (%s)" % citation if citation else "")

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
        return int(value) if value == int(value) else core.plain_number(value)
    text = str(value)
    if not input_text:
        own_words = re.sub(r"\u201c.*?\u201d", "", text, flags=re.S)
        if PYTHON_TRACES.search(own_words) or core.has_banned_wording(own_words):
            log_line(store, "cell text withheld: " + text)
            text = CELL_WITHHELD
    return text if len(text) <= 32000 else text[:31900] + CUT_NOTE

def lines_by_ref(pairs):
    """Several values in one cell: each on its own line, prefixed with its reference."""
    return "\n".join("%s: %s" % (ref, value) for ref, value in pairs if value not in (None, ""))

def texts_by_ref(pairs):
    """Several quoted texts in one cell, separated by a line of dashes."""
    return "\n----------\n".join("%s: %s" % (ref, text) for ref, text in pairs)

def run_identity(store, paths):
    """What ties a workbook to its run: also written into the workbook's properties."""
    items = store.read("flagged_items")
    ledger, decisions = store.read("graph_ledger"), store.read("determinations")
    return {"model_id": paths.model_id, "date_initiated": paths.project_date, "run_id": paths.run_id,
            "engine_version": core.ENGINE_VERSION,
            "item_list_hash": core.sha256_text("\n".join(i["item_id"] for i in items)) if items else "",
            "graph_version_id": "G-" + core.chain_head(ledger)[:12] if ledger else "",
            "determinations_fingerprint": "DR-" + core.chain_head(decisions)[:12] if decisions else ""}

def rows_package_info(store, paths, settings, progress):
    """The rows of Model_Package_Info: identity, inputs, what was read, repairs, how values and formulas are compared, AI calls."""
    identity, rows = run_identity(store, paths), []
    def add(group, item, value):
        rows.append({"group": group, "item": item, "value": value})
    add("Identity", "Model ID", identity["model_id"])
    add("Identity", "Date initiated", identity["date_initiated"])
    add("Identity", "Run", identity["run_id"])
    add("Identity", "Run progress", progress)
    add("Identity", "Engine version", identity["engine_version"])
    add("Identity", "Graph version id", identity["graph_version_id"] or core.NOT_RUN_YET)
    add("Identity", "Determinations record fingerprint", identity["determinations_fingerprint"] or "No determination recorded yet")
    add("Identity", "Item list fingerprint", identity["item_list_hash"] or core.NOT_RUN_YET)
    manifest = (store.read("run_manifest") or [{}])[0]
    if manifest.get("engine_files"):
        add("Identity", "Engine files fingerprint", core.sha256_text(core.canonical_json(manifest["engine_files"]))[:16] +
            " (%d files; the full list is in the run manifest)" % len(manifest["engine_files"]))
    for entry in manifest.get("inputs", []):
        add("Inputs", entry["file"], "SHA-256 %s (%d bytes)" % (entry["sha256"], entry["bytes"]))
    for change in manifest.get("changes_since_previous_run", []):
        add("Inputs", "Changed since run %s" % manifest.get("previous_run", ""), change)
    if manifest.get("outline_confirmed_by"):
        add("Review", "Methodology outline confirmed by", manifest["outline_confirmed_by"])
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
    add("How values are compared", "The value-comparison rule", review.VALUE_RULE_TEXT)
    add("How values are compared", "Numbers treated as trivial", ", ".join(settings["trivial_numbers"]))
    add("How formulas are compared", "Sample points and seed",
        "%d points, seed %d, relative tolerance %s" % (settings["numeric_points"], settings["numeric_seed"],
                                                       core.plain_number(settings["relative_tolerance"], 3)))
    for label, value in call_statistics(store):
        add("AI calls", label, value)
    return rows

def chunk_note(chunk):
    """What a reader should know about one chunk: unreadable, how an equation was read, reconstructed numbering."""
    notes = ["Could not be read: %s" % chunk["not_read_reason"]] if chunk.get("not_read_reason") else []
    equation = chunk.get("equation") or {}
    if chunk["kind"] == "Equation" and not equation.get("readable"):
        notes.append("Could not be read: %s" % (equation.get("not_readable_reason") or "unknown form"))
    if chunk["kind"] == "Equation" and equation.get("readable"):
        notes.append("Read as: %s" % equation.get("linear", ""))
    if chunk["kind"] == "Figure":
        notes.append("The content of a figure is never read; it is raised for manual review")
    if chunk.get("numbering_reconstructed"):
        notes.append("Heading numbering was reconstructed by counting")
    return "; ".join(notes)

def concept_names_by_ref(store):
    """Each unit's concepts as the Chunks sheets show them: the words that unit writes, exactly, for
    each model concept it names, joined by '; '. Never the model's name for it: that mapping, and
    every guess in it, is on the Concepts sheet only."""
    _, unit_concepts = review.latest_concepts(store.read)
    return {u["unit_ref"]: "; ".join(u.get("as_written") or []) for u in unit_concepts}

def rows_concepts(store):
    """The rows of Concepts: one per model concept, model first - the names its code gives it and how
    its roxygen and help pages describe it - then the same words found in the methodology, the
    documentation and the rest of the model, and apart from those, the model's guesses of synonyms,
    acronyms and abbreviations. Every form is shown as written, with the units that write it."""
    concepts, _ = review.latest_concepts(store.read)
    def listed(forms):
        return "\n".join("%s (%s)" % (form, ", ".join(refs)) for form, refs in forms.items())
    rows = []
    for concept in concepts:
        found, guessed = concept["found"], concept["guessed"]
        rows.append({"concept_id": concept["concept_id"], "in_model": listed(concept["identifiers"]),
                     "described": listed(concept["described"]),
                     "canon": listed(found.get("canon", {})), "doc": listed(found.get("doc", {})),
                     "model": listed({form: refs for form, refs in found.get("model", {}).items()}),
                     "guessed": "\n".join("%s: %s" % (corner, listed(forms).replace("\n", "; ")) for corner, forms in
                                          (("Methodology", guessed.get("canon", {})), ("Documentation", guessed.get("doc", {}))) if forms),
                     "established": "\n".join(concept["how"][:12])})
    return rows

def scope_of(store):
    """The latest scope decision per unit, as the yellow column shows it back."""
    latest = {}
    for record in store.read("scope_decisions"):
        latest[record["unit_ref"]] = record["decision"]
    return latest

def rows_chunks(chunks, scope=None, named=None):
    """The rows of Chunks_Canon and Chunks_Doc."""
    rows, scope, named = [], scope or {}, named or {}
    for chunk in chunks:
        rows.append({"ref": chunk["ref"], "scope": scope.get(chunk["ref"], ""), "concepts": named.get(chunk["ref"], ""), "level": chunk["level"], "section": " > ".join(chunk["heading_chain"]),
                     "para_no": chunk.get("para_label") or chunk["para_no"],
                     "kind": chunk["kind"], "text": chunk["text"],
                     "source_file": chunk["source_file"], "refs_out": "; ".join(chunk["refs_out"]),
                     "checkable": chunk.get("checkable"), "reading_note": chunk_note(chunk)})
    return rows

def unit_expression(unit):
    """A unit's formula or arguments as shown on Chunks_Model."""
    code, data = unit.get("code") or {}, unit.get("data") or {}
    if unit["kind"] == core.KIND_FUNCTION:
        formals = ["%s = %s" % (n, d) if d not in (None, "") else n for n, d in code.get("formals", [])]
        return "arguments: " + (", ".join(formals) or "none")
    if code.get("expression"):
        return core.expr_to_text(core.expr_from_dict(code["expression"]))
    if data:
        return "rows identified by: %s; %s" % (", ".join(data.get("row_keys", [])) or "row number",
                                               " x ".join(str(d) for d in data.get("dims", [])))
    return ""

def rows_model_units(units, interpretations=(), scope=None, named=None):
    """The rows of Chunks_Model. What the AI said a piece of code does is shown as a quotation
    (in \u201c \u201d), because the words are the model's and not the tool's own. Enforces: R10"""
    rows, said, scope, named = [], {record["unit_ref"]: record for record in interpretations}, scope or {}, named or {}
    for unit in units:
        code, told = unit.get("code") or {}, said.get(unit["ref"], {})
        lines = "%d-%d" % tuple(unit["lines"]) if unit.get("lines") else ""
        rows.append({"ref": unit["ref"], "scope": scope.get(unit["ref"], ""), "concepts": named.get(unit["ref"], ""), "kind": unit["kind"], "file": unit["file"], "lines": lines,
                     "name": unit["name"], "inside": unit["inside"], "text": unit["text"],
                     "expression": unit_expression(unit), "exported": code.get("exported"),
                     "numbers": "; ".join(n["as_written"] for n in code.get("numbers", [])),
                     "reading_note": unit.get("read_problem") or "", "llm_interpretation": told.get("note") or (
                         "\u201c%s\u201d" % re.sub("[\u201c\u201d]", '"', told["interpretation"]) if told.get("interpretation") else ""),
                     "where": "%s%s" % (unit["file"], " lines " + lines if lines else "")})
    return rows

def link_columns(unit_ref, prefix, corner_letter, links, searches, texts):
    """The block of columns that shows what one unit was linked to in one corner."""
    mine = [e for e in links.get(unit_ref, []) if e["target"].startswith(corner_letter)]
    latest = {}
    for edge in mine:                                 # a later edge on the same pair has the last word
        latest[edge["target"]] = edge
    shown = [latest[ref] for ref in sorted(latest)]
    search = searches.get((unit_ref, prefix), {})
    return {prefix + "_refs": "\n".join(e["target"] for e in shown),
            prefix + "_relation": lines_by_ref((e["target"], e["relation"]) for e in shown),
            prefix + "_how": lines_by_ref((e["target"], e["evidence"].get("how_text", "")) for e in shown),
            prefix + "_searched": search.get("searched_text", "") or (core.NOT_RUN_YET if not searches else ""),
            prefix + "_why_not": "" if shown else search.get("note", ""),
            prefix + "_text": texts_by_ref((e["target"], texts.get(e["target"], "")) for e in shown)}

def rows_mapping(store, corner):
    """One row per model unit (corner "model") or per documentation unit (corner "doc").
    The words in the assessment cells were written by verifier3 and verifier4; this only lays out."""
    units = store.read("model_units") if corner == "model" else store.read("chunks_doc")
    texts = {r["ref"]: r["text"] for kind in ("chunks_canon", "chunks_doc", "model_units") for r in store.read(kind)}
    links, searches = {}, {}
    for record in store.read("graph_ledger"):
        if record.get("record_type") == "edge" and record["kind"] == "corresponds":
            links.setdefault(record["source"], []).append(record)
            links.setdefault(record["target"], []).append(dict(record, target=record["source"]))   # the same link, seen from the other side
    corner_names = {"canon": "canon", "doc": "doc", "model": "model"}
    for record in store.read("search_records"):
        key = (record["unit_ref"], corner_names[record["target_corner"]])
        merged = dict(searches.get(key, {}))
        merged.update({k: v for k, v in record.items() if v})
        searches[key] = merged
    statuses = {r["unit_ref"]: r for r in store.read("unit_status")}
    base_rows = rows_model_units(units) if corner == "model" else rows_chunks(units)
    rows = []
    for row in base_rows:
        row.update(link_columns(row["ref"], "canon", "C-", links, searches, texts))
        other = ("doc", "D-") if corner == "model" else ("model", "M-")
        row.update(link_columns(row["ref"], other[0], other[1], links, searches, texts))
        status = statuses.get(row["ref"])
        row["status"] = status["status"] if status else core.NOT_RUN_YET
        row["item_ids"] = ("\n".join(status["item_ids"]) or "No item") if status else ""
        row["cells"] = status["cells"] if status else {}
        rows.append(row)
    return rows

def rows_coverage(model_rows, doc_rows, store):
    """Counted from the rows actually written: the second, independent route of the
    coverage identity (part 4). Enforces: R2"""
    rows, counted = [], bool(store.read("coverage"))
    for corner, label in COVERAGE_ROWS[:2]:
        written = model_rows if corner == "model" else doc_rows
        if not counted:                              # empty, never zero: nothing has been counted yet
            rows.append({"corner": label, "total": len(written), "how_to_read":
                         "Not counted yet: statuses are given by the step account-coverage, after the model has "
                         "judged the links. Until then these columns stay empty; cell 4 shows how far the run is."})
            continue
        row = {"corner": label, "total": len(written), "how_to_read": NEEDS_ATTENTION_MEANS}
        for status in core.CLEAN_STATUSES + core.NOT_CLEAN_STATUSES:
            row[status] = sum(1 for r in written if r["status"] == status)
        row["needs_attention"] = sum(row[status] for status in core.NOT_CLEAN_STATUSES)
        rows.append(row)
    canon = store.read("chunks_canon")
    pointed = {e["target"] for e in store.read("graph_ledger")
               if e.get("record_type") == "edge" and e["kind"] == "corresponds" and e["relation"] in core.LINKING_RELATIONS}
    count = sum(1 for c in canon if c["ref"] in pointed)
    rows.append({"corner": COVERAGE_ROWS[2][1], "total": len(canon), "how_to_read":
                 "%d of %d passages are pointed to by at least one link. The others are listed in the "
                 "report, for information only." % (count, len(canon))})
    return rows

def latest_determinations(store):
    """The last recorded determination of every item."""
    latest = {}
    for record in store.read("determinations"):
        latest[record["item_id"]] = record
    return latest

def rows_flagged(store):
    """The rows of Flagged_Items with the latest determination of each item."""
    latest, rows = latest_determinations(store), []
    for item in store.read("flagged_items"):
        decided = latest.get(item["item_id"])
        active = decided is not None and decided["decision"] != core.DECISION_WITHDRAWN
        row = dict(item, unit_refs="\n".join(item["unit_refs"]),
                   status=decided["decision"] if active else core.ITEM_OPEN,
                   last_decision_recorded=decided["recorded_at"] if decided else "")
        for name in ("decision", "reviewer", "role", "rationale"):
            row[name] = decided[name] if active else ""
        rows.append(row)
    return rows

def sheet_rows(store, paths, settings, progress):
    """The rows of all eight sheets, by sheet name."""
    model_rows, doc_rows = rows_mapping(store, "model"), rows_mapping(store, "doc")
    for row in model_rows + doc_rows:
        for name, text in row.pop("cells").items():
            row[name] = text
    return {"Model_Package_Info": rows_package_info(store, paths, settings, progress),
            "Chunks_Canon": rows_chunks(store.read("chunks_canon"), scope_of(store), concept_names_by_ref(store)),
            "Chunks_Doc": rows_chunks(store.read("chunks_doc"), scope_of(store), concept_names_by_ref(store)),
            "Chunks_Model": rows_model_units(store.read("model_units"), store.read("interpretations"), scope_of(store), concept_names_by_ref(store)),
            "Concepts": rows_concepts(store),
            "Mapping_Model_to_Canon_and_Doc": model_rows, "Mapping_Doc_to_Canon_and_Model": doc_rows,
            "Mapping_Coverage": rows_coverage(model_rows, doc_rows, store), "Flagged_Items": rows_flagged(store)}

def check_written_totals(rows, store):
    """Identity part 4: what account-coverage counted must equal what the workbook holds."""
    coverage = store.read("coverage")
    if not coverage:
        return
    for position, corner in enumerate(("model", "doc")):
        counted, written = coverage[0][corner], rows["Mapping_Coverage"][position]
        same = counted["total"] == written["total"] and all(
            counted["by_status"].get(s, 0) == written[s] for s in core.CLEAN_STATUSES + core.NOT_CLEAN_STATUSES)
        if not same:
            raise review.EngineFault(
                "Part 4 of the coverage identity does not hold: the totals counted for the %s corner differ "
                "from the rows written to the workbook. This is a defect in the tool, not in the model under review." % corner)

# ---------------------------------------------------------------- the workbook layout
# Every sheet of Output.xlsx in order, and every column of each: its header, its colour group, the
# field of the row it shows, its width, and whether it is typed by a person (input_text). One line
# per column. Parsed on every call, so a caller's change stays its own. Enforces: R10
WORKBOOK_LAYOUT_YAML = r'''colours: {identity: D9E1F2, code_text: E2EFDA, methodology: FCE4D6, documentation: E4DFEC, assessments: DDEBF7, reviewer_input: FFFF00}
sheets:
- name: Model_Package_Info
  columns:
  - {header: Group, group: identity, field: group, width: 26}
  - {header: Item, group: identity, field: item, width: 40}
  - {header: Value, group: assessments, field: value, width: 90}
- name: Chunks_Canon
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Use in review, group: reviewer_input, field: scope, width: 14, input_text: true}
  - {header: Level, group: identity, field: level, width: 7}
  - {header: Section (heading chain), group: identity, field: section, width: 44}
  - {header: Para no., group: identity, field: para_no, width: 9}
  - {header: Type, group: identity, field: kind, width: 11}
  - {header: Text, group: methodology, field: text, width: 90, input_text: true}
  - {header: Extracted concepts with candidate equivalent in model, group: methodology, field: concepts, width: 42}
  - {header: Source file, group: identity, field: source_file, width: 28}
  - {header: Cross-references, group: methodology, field: refs_out, width: 24}
  - {header: Reading note, group: assessments, field: reading_note, width: 40}
- name: Chunks_Doc
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Use in review, group: reviewer_input, field: scope, width: 14, input_text: true}
  - {header: Level, group: identity, field: level, width: 7}
  - {header: Section (heading chain), group: identity, field: section, width: 44}
  - {header: Para no., group: identity, field: para_no, width: 9}
  - {header: Type, group: identity, field: kind, width: 11}
  - {header: Text, group: documentation, field: text, width: 90, input_text: true}
  - {header: Extracted concepts with candidate equivalent in model, group: documentation, field: concepts, width: 42}
  - {header: Source file, group: identity, field: source_file, width: 28}
  - {header: Cross-references, group: documentation, field: refs_out, width: 24}
  - {header: States something checkable, group: assessments, field: checkable, width: 16}
  - {header: Reading note, group: assessments, field: reading_note, width: 40}
- name: Chunks_Model
  columns:
  - {header: Ref, group: identity, field: ref, width: 10}
  - {header: Use in review, group: reviewer_input, field: scope, width: 14, input_text: true}
  - {header: Kind, group: identity, field: kind, width: 20}
  - {header: File, group: identity, field: file, width: 30}
  - {header: Lines, group: identity, field: lines, width: 10}
  - {header: Name, group: identity, field: name, width: 24, input_text: true}
  - {header: Inside, group: identity, field: inside, width: 20}
  - {header: Text, group: code_text, field: text, width: 80, input_text: true}
  - {header: Extracted concepts with candidate equivalent in model, group: code_text, field: concepts, width: 42}
  - {header: LLM Interpretation, group: assessments, field: llm_interpretation, width: 60}
  - {header: Expression / arguments, group: code_text, field: expression, width: 50, input_text: true}
  - {header: Numbers used, group: code_text, field: numbers, width: 20}
  - {header: Exported, group: identity, field: exported, width: 10}
  - {header: Reading note, group: assessments, field: reading_note, width: 40}
- name: Concepts
  columns:
  - {header: Concept id, group: identity, field: concept_id, width: 11}
  - {header: 'In the model, as the code names it', group: identity, field: in_model, width: 30}
  - {header: Described in the model as, group: identity, field: described, width: 34}
  - {header: Same words in the methodology, group: assessments, field: canon, width: 34}
  - {header: Same words in the documentation, group: assessments, field: doc, width: 34}
  - {header: Same words in the rest of the model, group: assessments, field: model, width: 30}
  - {header: Candidate synonyms and acronyms (AI guess), group: assessments, field: guessed, width: 40}
  - {header: How established, group: assessments, field: established, width: 60}
- name: Mapping_Model_to_Canon_and_Doc
  columns:
  - {header: Model ref, group: identity, field: ref, width: 10}
  - {header: Kind, group: identity, field: kind, width: 18}
  - {header: Name, group: identity, field: name, width: 22, input_text: true}
  - {header: File and lines, group: identity, field: where, width: 26}
  - {header: Code text, group: code_text, field: text, width: 60, input_text: true}
  - {header: Canon ref(s), group: methodology, field: canon_refs, width: 14}
  - {header: Relation (canon), group: methodology, field: canon_relation, width: 22}
  - {header: How established (canon), group: methodology, field: canon_how, width: 50}
  - {header: What was searched (canon), group: methodology, field: canon_searched, width: 50}
  - {header: Why not mapped (canon), group: methodology, field: canon_why_not, width: 40}
  - {header: Canon text, group: methodology, field: canon_text, width: 60, input_text: true}
  - {header: Doc ref(s), group: documentation, field: doc_refs, width: 14}
  - {header: Relation (doc), group: documentation, field: doc_relation, width: 22}
  - {header: How established (doc), group: documentation, field: doc_how, width: 50}
  - {header: What was searched (doc), group: documentation, field: doc_searched, width: 50}
  - {header: Why not mapped (doc), group: documentation, field: doc_why_not, width: 40}
  - {header: Doc text, group: documentation, field: doc_text, width: 60, input_text: true}
  - {header: Math check, group: assessments, field: math_check, width: 50}
  - {header: Parameter completeness, group: assessments, field: parameter_completeness, width: 50}
  - {header: Logic consistency, group: assessments, field: logic_consistency, width: 50}
  - {header: Documentation consistency, group: assessments, field: documentation_consistency, width: 50}
  - {header: Hard-coded numbers, group: assessments, field: hard_coded_numbers, width: 44}
  - {header: Unit test, group: assessments, field: unit_test, width: 34}
  - {header: Quality notes (AI), group: assessments, field: quality_notes_ai, width: 44}
  - {header: Overall status, group: assessments, field: status, width: 30}
  - {header: Flagged item(s), group: assessments, field: item_ids, width: 30}
- name: Mapping_Doc_to_Canon_and_Model
  columns:
  - {header: Doc ref, group: identity, field: ref, width: 10}
  - {header: Type, group: identity, field: kind, width: 11}
  - {header: Section (heading chain), group: identity, field: section, width: 40}
  - {header: Doc text, group: documentation, field: text, width: 60, input_text: true}
  - {header: Canon ref(s), group: methodology, field: canon_refs, width: 14}
  - {header: Relation (canon), group: methodology, field: canon_relation, width: 22}
  - {header: How established (canon), group: methodology, field: canon_how, width: 50}
  - {header: What was searched (canon), group: methodology, field: canon_searched, width: 50}
  - {header: Why not mapped (canon), group: methodology, field: canon_why_not, width: 40}
  - {header: Canon text, group: methodology, field: canon_text, width: 60, input_text: true}
  - {header: Model ref(s), group: code_text, field: model_refs, width: 14}
  - {header: Relation (model), group: code_text, field: model_relation, width: 22}
  - {header: How established (model), group: code_text, field: model_how, width: 50}
  - {header: Model text, group: code_text, field: model_text, width: 60, input_text: true}
  - {header: Value check, group: assessments, field: value_check, width: 50}
  - {header: Math check, group: assessments, field: math_check, width: 50}
  - {header: Logic consistency, group: assessments, field: logic_consistency, width: 50}
  - {header: Parameter note (AI), group: assessments, field: parameter_note_ai, width: 44}
  - {header: Documentation quality notes, group: assessments, field: quality_notes, width: 44}
  - {header: Overall status, group: assessments, field: status, width: 30}
  - {header: Flagged item(s), group: assessments, field: item_ids, width: 30}
- name: Mapping_Coverage
  columns:
  - {header: Corner, group: identity, field: corner, width: 30}
  - {header: Units in total, group: identity, field: total, width: 12}
  - {header: Traced to methodology, group: assessments, field: Traced to methodology, width: 14}
  - {header: Supporting code (justified), group: assessments, field: Supporting code (justified), width: 14}
  - {header: Unit test, group: assessments, field: Unit test, width: 12}
  - {header: Narrative - nothing to check, group: assessments, field: Narrative - nothing to check, width: 14}
  - {header: Not in scope (a person's decision), group: assessments, field: Not in scope (a person's decision), width: 14}
  - {header: Traced - differences flagged, group: assessments, field: Traced - differences flagged, width: 14}
  - {header: Traced - check undecided, group: assessments, field: Traced - check undecided, width: 14}
  - {header: Not traced - for review, group: assessments, field: Not traced - for review, width: 14}
  - {header: Not assessed - for manual review, group: assessments, field: Not assessed - for manual review, width: 14}
  - {header: Needs attention, group: assessments, field: needs_attention, width: 12}
  - {header: How to read this row, group: identity, field: how_to_read, width: 70}
- name: Flagged_Items
  columns:
  - {header: Item id, group: identity, field: item_id, width: 30}
  - {header: Concerns, group: identity, field: concerns, width: 22}
  - {header: Category, group: identity, field: category, width: 34}
  - {header: Unit ref(s), group: identity, field: unit_refs, width: 14}
  - {header: Item, group: assessments, field: item, width: 44}
  - {header: What was observed, group: assessments, field: observed, width: 70}
  - {header: Methodology says, group: methodology, field: methodology_says, width: 50}
  - {header: Code does, group: code_text, field: code_does, width: 50}
  - {header: Documentation says, group: documentation, field: documentation_says, width: 50}
  - {header: Suggested next step, group: assessments, field: suggested_next_step, width: 44}
  - {header: Status, group: assessments, field: status, width: 18}
  - {header: Last decision recorded, group: assessments, field: last_decision_recorded, width: 22}
  - {header: Decision, group: reviewer_input, field: decision, width: 20, input_text: true}
  - {header: Reviewer, group: reviewer_input, field: reviewer, width: 20, input_text: true}
  - {header: Role, group: reviewer_input, field: role, width: 20, input_text: true}
  - {header: Rationale, group: reviewer_input, field: rationale, width: 60, input_text: true}
'''

def load_layout():
    """The workbook layout: every sheet and every column of Output.xlsx."""
    return yaml.safe_load(WORKBOOK_LAYOUT_YAML)

def write_sheet(sheet, sheet_layout, rows, colours, settings, store):
    """One generic writer for every sheet: header row and first column frozen, filter on
    the header, wrapped text, no merged cells, reviewer columns yellow and unlocked."""
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    columns = sheet_layout["columns"]
    wrap = Alignment(wrap_text=True, vertical="top")
    for number, column in enumerate(columns, start=1):
        header = column["header"]
        if column["field"] == "concepts" and settings.get("concept_subject"):   # "Extracted financial concepts with ..."
            header = header.replace("Extracted concepts", "Extracted %s concepts" % settings["concept_subject"].strip().lower(), 1)
        cell = sheet.cell(row=1, column=number, value=header)
        cell.font, cell.alignment = Font(bold=True), wrap
        cell.fill = PatternFill("solid", start_color=colours[column["group"]])
        sheet.column_dimensions[get_column_letter(number)].width = column.get("width", 20)
    for row_number, row in enumerate(rows, start=2):
        for number, column in enumerate(columns, start=1):
            value = row.get(column["field"])
            if value in (None, "") and column["group"] == "assessments" and sheet_layout["name"].startswith(("Mapping_Model", "Mapping_Doc")):
                value = core.NOT_RUN_YET
            cell = sheet.cell(row=row_number, column=number, value=plain_cell(value, column.get("input_text"), store))
            cell.alignment = wrap
            if column["group"] == "reviewer_input":
                cell.fill = PatternFill("solid", start_color=colours["reviewer_input"])
                cell.protection = Protection(locked=False)
    last = get_column_letter(len(columns))
    sheet.freeze_panes = "B2"
    sheet.auto_filter.ref = "A1:%s%d" % (last, max(1, len(rows) + 1))
    fields = [c["field"] for c in columns]
    for field_name, words in (("decision", core.DECISION_WORDS), ("scope", core.SCOPE_WORDS)):
        if field_name in fields and rows:            # the drop-downs: Decision on Flagged_Items, Use in review on the Chunks sheets
            letter = get_column_letter(fields.index(field_name) + 1)
            choice = DataValidation(type="list", formula1='"%s"' % ",".join(words), allow_blank=True)
            sheet.add_data_validation(choice)
            choice.add("%s2:%s%d" % (letter, letter, len(rows) + 1))
    if settings["protect_sheets"]:
        sheet.protection.sheet = True
        sheet.protection.autoFilter = False          # False = not locked: filtering stays possible
        sheet.protection.formatColumns = False

def build_workbook(store, paths, settings, progress, target):
    """Build Output.xlsx on local disk from the audit records. All eight sheets always
    exist; a sheet whose step has not run shows its header only."""
    import openpyxl
    layout = load_layout()
    rows = sheet_rows(store, paths, settings, progress)
    check_written_totals(rows, store)
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for sheet_layout in layout["sheets"]:
        sheet = workbook.create_sheet(sheet_layout["name"])
        write_sheet(sheet, sheet_layout, rows[sheet_layout["name"]], layout["colours"], settings, store)
    workbook.properties.title = "the tool Output"
    workbook.properties.description = core.canonical_json(run_identity(store, paths))
    workbook.save(target)
    return rows

# ---------------------------------------------------------------- rebuilding the outputs
def file_sha256(path):
    """SHA-256 of a file's bytes."""
    with open(path, "rb") as handle:
        return core.sha256_bytes(handle.read())

REPORT_SCOPE = (
    "This review compares three things: the methodology, the model's code and data, and the model "
    "documentation. The tool reads all three, links what corresponds, checks formulas, values and stated rules "
    "by code, and raises what it could not line up for a person to decide. It does not run the model, does not "
    "judge whether the methodology is sound, and rates nothing: every flagged item is a question for a person.")

def docx_table(document, header, rows):
    """A plain table in a Word document, header row in bold."""
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, header):
        cell.text = text
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for row in rows:
        for cell, text in zip(table.add_row().cells, row):
            cell.text = str(text)
    return table

def call_statistics(store):
    """The AI call statistics shown on Model_Package_Info and in the report's annex."""
    calls = store.read_calls()
    if not calls:
        return [("Questions asked", "No question has been asked yet")]
    final = [c for c in calls if c.get("final")]
    rejected = {}
    for call in final:
        if call["outcome"].startswith("rejected"):
            rejected[call["outcome"]] = rejected.get(call["outcome"], 0) + 1
    with_planted = [c for c in final if c.get("planted")]
    seconds = sorted(c["seconds"] for c in calls)
    rows = [("Questions asked", len(final)), ("Attempts made", len(calls)),
            ("Answers accepted", sum(1 for c in final if c["outcome"] == "accepted")),
            ("Questions that stayed without an answer", sum(1 for c in final if c["outcome"].startswith("failed")))]
    rows += [("Answers %s" % reason, count) for reason, count in sorted(rejected.items())]
    planted = sum(1 for c in with_planted if c["outcome"] == "rejected: " + core.REJECTION_REASONS[3])
    rows.append(("Answers that accepted a planted control passage", "%d of %d questions that held one" % (planted, len(with_planted))))
    rows.append(("Median seconds per call", core.plain_number(seconds[len(seconds) // 2], 3)))
    return rows

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
    if store.read("flagged_items"):
        local_report = os.path.join(work, "Validation_Report.docx")
        build_report_file(store, paths, settings, local_report)
        copy_whole(local_report, os.path.join(paths.outputs_dir, "Validation_Report.docx"))
    store.sync()
    return not guarded

# ---------------------------------------------------------------- determinations
def find_uploads(paths, identity):
    """Every .xlsx in the run folder whose embedded identity matches this run, whatever it is called
    (the behaviour of an upload onto an existing name is not documented). Returns the
    matching files, newest last, and plain messages about files that were refused."""
    import openpyxl
    matching, refused = [], []
    for name in sorted(os.listdir(paths.outputs_dir)):
        path = os.path.join(paths.outputs_dir, name)
        if name.lower().endswith(".xls"):
            refused.append("%s is in the old .xls format; save it as .xlsx and upload it again." % name)
        if not name.lower().endswith(".xlsx"):
            continue
        try:
            found = json.loads(openpyxl.load_workbook(path, read_only=True).properties.description or "{}")
        except Exception:
            refused.append("%s could not be opened as a workbook; nothing was read from it." % name)
            continue
        if all(found.get(key) == identity[key] for key in ("model_id", "date_initiated", "run_id", "item_list_hash")):
            matching.append(path)
        else:
            refused.append("%s belongs to another run or another list of items; nothing was read from it." % name)
    return sorted(matching, key=os.path.getmtime), refused

def read_yellow_cells(path, known_ids):
    """The four yellow cells of every row of Flagged_Items, found by item id and never by row
    position, because reviewers sort and filter. Returns ({item id: values}, messages)."""
    import openpyxl
    sheet = openpyxl.load_workbook(path, read_only=True)["Flagged_Items"]
    rows = list(sheet.iter_rows(values_only=True))
    header = [str(cell or "") for cell in rows[0]]
    places = {name: header.index(name) for name in ("Item id", "Decision", "Reviewer", "Role", "Rationale")}
    found, messages = {}, []
    for row in rows[1:]:
        item_id = str(row[places["Item id"]] or "").strip()
        values = {name.lower(): str(row[places[name]] or "").strip() for name in ("Decision", "Reviewer", "Role", "Rationale")}
        if not item_id:
            continue
        if item_id not in known_ids:
            messages.append("The row with item id %s belongs to no flagged item of this run and was not read." % item_id)
        elif item_id in found:
            messages.append("Item %s occurs on two rows; neither was recorded." % item_id)
            found[item_id] = None
        else:
            found[item_id] = values
    return {item_id: values for item_id, values in found.items() if values is not None}, messages

def record_determinations(ctx):
    """Step 17, record-determinations: find the uploaded workbook by its identity, keep a
    copy of its bytes in _audit/uploads/, read and validate the yellow cells, and append one
    record for every item whose four values changed. Earlier records are never changed; a
    cleared decision is recorded as Withdrawn. The record is a hash chain. Enforces: R4, R12"""
    paths, settings = ctx.options["paths"], ctx.settings
    manifest = (ctx.read("run_manifest") or [{}])[0]
    items = {item["item_id"] for item in ctx.read("flagged_items")}
    identity = {"model_id": paths.model_id, "date_initiated": paths.project_date, "run_id": paths.run_id,
                "item_list_hash": core.sha256_text("\n".join(i["item_id"] for i in ctx.read("flagged_items"))) if items else ""}
    uploads, messages = find_uploads(paths, identity)
    edited = [p for p in uploads if file_sha256(p) != manifest.get("last_workbook_sha256")]
    if not edited:
        return core.StepResult({}, {"determinations recorded": 0}, messages + ["No edited workbook of this run was found in the run folder."])
    chosen = edited[-1]
    digest = file_sha256(chosen)
    cells, notes = read_yellow_cells(chosen, items)
    messages += notes
    latest, records = {}, []
    for record in ctx.read("determinations"):
        latest[record["item_id"]] = record
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for item_id in sorted(cells):
        values = cells[item_id]
        previous = latest.get(item_id)
        decision = next((word for word in core.DECISION_WORDS if word.lower() == values["decision"].lower()), "")
        if values["decision"] and not decision:
            messages.append("Item %s: the decision must be one of: %s. Nothing was recorded for it." % (item_id, ", ".join(core.DECISION_WORDS)))
            continue
        if decision and not (values["reviewer"] and values["role"] and values["rationale"]):
            messages.append("Item %s: a decision needs a reviewer, a role and a rationale. Nothing was recorded for it." % item_id)
            continue
        if not decision:
            if previous and previous["decision"] != core.DECISION_WITHDRAWN:
                records.append(core.Determination(item_id, core.DECISION_WITHDRAWN, previous["reviewer"], previous["role"],
                                                    "The recorded decision was cleared in the workbook.", now, settings["reviewer_id"], digest))
            continue
        same = previous and all(previous[key] == value for key, value in dict(values, decision=decision).items())
        if not same:
            records.append(core.Determination(item_id, decision, values["reviewer"], values["role"], values["rationale"], now,
                                                settings["reviewer_id"], digest))
    for path in uploads:                                 # tidy the run folder back to exactly the two files the tool writes
        if os.path.basename(path) != "Output.xlsx":
            os.remove(path)
    chained = core.chain_records(core.chain_head(ctx.read("determinations")), [core.to_plain(r) for r in records])
    manifest.update(last_upload_sha256=digest)
    return core.StepResult({"determinations": chained, "run_manifest": [manifest]}, {"determinations recorded": len(chained)},
                             messages + ["Text typed outside the four yellow columns is ignored."])

# ---------------------------------------------------------------- Validation_Report.docx
def build_report_file(store, paths, settings, target):
    """The report, in the eight parts of plan 2.11, built from the same records as the
    workbook. Items are ordered by item id and never ranked. Enforces: R1, R10"""
    import docx
    from docx.enum.section import WD_ORIENT
    identity, document = run_identity(store, paths), docx.Document()
    items, latest = store.read("flagged_items"), latest_determinations(store)
    decided = {k: v for k, v in latest.items() if v["decision"] != core.DECISION_WITHDRAWN}
    info = (store.read("package_info") or [{}])[0]
    document.add_heading("the tool validation report", level=1)
    open_count = sum(1 for item in items if item["item_id"] not in decided)
    document.add_paragraph("Every flagged item has a recorded determination." if items and not open_count
                           else "%d of %d flagged items are still open." % (open_count, len(items)))
    docx_table(document, ("Field", "Value"), [
        ("Model ID", identity["model_id"]), ("Date initiated", identity["date_initiated"]), ("Run", identity["run_id"]),
        ("Package", "%s %s" % (info.get("name", ""), info.get("version", ""))), ("Engine version", identity["engine_version"]),
        ("Graph version id", identity["graph_version_id"]), ("Item list fingerprint", identity["item_list_hash"][:16]),
        ("Determinations record fingerprint", identity["determinations_fingerprint"] or "No determination recorded yet")])
    manifest = (store.read("run_manifest") or [{}])[0]
    document.add_heading("1. What was reviewed", level=2)
    docx_table(document, ("Input file", "SHA-256", "Bytes"), [(e["file"], e["sha256"], e["bytes"]) for e in manifest.get("inputs", [])])
    for change in manifest.get("changes_since_previous_run", []):
        document.add_paragraph("Changed since run %s: %s" % (manifest.get("previous_run", ""), change))
    document.add_heading("2. What the tool did and did not assess", level=2)
    document.add_paragraph(REPORT_SCOPE)
    limits = [(s["unit_ref"], s["reason_shown"]) for s in store.read("unit_status") if s["status"] == core.ST_NOT_ASSESSED]
    limits += [("Repair", "%s: %s" % (r["file"], r["kind"])) for r in store.read("read_repairs")][:40]
    docx_table(document, ("Unit or file", "Limit of this run"), limits or [("None", "Nothing was left unread or unassessed")])
    document.add_heading("3. Coverage", level=2)
    coverage = (store.read("coverage") or [{}])[0]
    rows = [(label, coverage.get(corner, {}).get("total", ""), coverage.get(corner, {}).get("needs_attention", "for information only"))
            for corner, label in COVERAGE_ROWS]
    docx_table(document, ("Corner", "Units", "Needs attention"), rows)
    document.add_paragraph(NEEDS_ATTENTION_MEANS)
    document.add_heading("4. Flagged items by concern and category", level=2)
    counts = {}
    for item in items:
        counts[(item["concerns"], item["category"])] = counts.get((item["concerns"], item["category"]), 0) + 1
    docx_table(document, ("Concerns", "Category", "Items"), [(c, k, n) for (c, k), n in sorted(counts.items())])
    section = document.add_section()
    section.orientation, section.page_width, section.page_height = WD_ORIENT.LANDSCAPE, section.page_height, section.page_width
    document.add_heading("5. Every flagged item", level=2)
    for item in items:
        document.add_heading("%s - %s" % (item["item_id"], item["category"]), level=3)
        document.add_paragraph("Concerns: %s. Units: %s." % (item["concerns"], ", ".join(item["unit_refs"])))
        document.add_paragraph(item["observed"][:3000])
        docx_table(document, ("Methodology says", "Code does", "Documentation says"),
                   [(item["methodology_says"][:1500], item["code_does"][:1500], item["documentation_says"][:1500])])
        document.add_paragraph("Suggested next step: %s" % item["suggested_next_step"])
        record = latest.get(item["item_id"])
        if record:
            by = "" if record["recorded_by"] in ("", record["reviewer"]) else ", recorded by %s for reviewer %s" % (record["recorded_by"], record["reviewer"])
            document.add_paragraph("Determination: %s, by %s (%s) at %s%s. Rationale: %s" % (
                record["decision"], record["reviewer"], record["role"], record["recorded_at"], by, quoted(record["rationale"])))
        else:
            document.add_paragraph("Determination: none recorded yet (the item is open).")
    document.add_heading("6. Methodology passages that nothing points to (for information)", level=2)
    pointed = {e["target"] for e in store.read("graph_ledger") if e.get("record_type") == "edge" and e["kind"] == "corresponds"
               and e["relation"] in core.LINKING_RELATIONS}
    unpointed = [(c["ref"], " > ".join(c["heading_chain"][-2:]), c["kind"]) for c in store.read("chunks_canon") if c["ref"] not in pointed]
    docx_table(document, ("Passage", "Section", "Kind"), unpointed or [("None", "", "")])
    document.add_heading("7. How to re-verify this pack", level=2)
    document.add_paragraph("Open the notebook, enter the model ID, the date initiated and this run, and run the cell \"Verify this evidence "
                           "pack\". It re-hashes the inputs, re-reads them, verifies both hash chains and re-checks the coverage identity.")
    document.add_heading("Annex. AI call statistics", level=2)
    docx_table(document, ("Measure", "Value"), call_statistics(store))
    document.save(target)

def build_report(ctx):
    """Step 18, build-report: a summary of the graph as it stands - nodes and edges by kind - as
    one record, so that a reader of the pack can see the graph's shape without loading every
    ledger record. The graph itself is the graph_ledger records; the two deliverables are rebuilt
    by the runner after every step."""
    ledger = ctx.read("graph_ledger")
    nodes = [r for r in ledger if r["record_type"] == "node"]
    edges = [r for r in ledger if r["record_type"] == "edge"]
    by_node, by_edge = {}, {}
    for node in nodes:
        by_node[node["node_kind"]] = by_node.get(node["node_kind"], 0) + 1
    for edge in edges:
        by_edge[edge["kind"]] = by_edge.get(edge["kind"], 0) + 1
    summary = {"nodes": len(nodes), "edges": len(edges), "nodes_by_kind": by_node, "edges_by_kind": by_edge}
    return core.StepResult({"graph_summary": [summary]}, {"nodes": len(nodes), "edges": len(edges)}, [])

# ---------------------------------------------------------------- verify this evidence pack
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
    options = {"inputs": core.list_input_files(paths.inputs_dir)}
    context = core.StepContext(settings, options, lambda kind: [], None, paths.local_dir, lambda text: None)
    for kind, function in (("chunks_canon", reading.read_methodology), ("chunks_doc", reading.read_documentation),
                           ("model_units", reading.read_package)):
        fresh = {core.to_plain(r)["ref"]: core.to_plain(r)["content_hash"] for r in function(context).records.get(kind, [])}
        recorded = {r["ref"]: r["content_hash"] for r in store.read(kind)}
        differing = sorted(ref for ref in set(fresh) | set(recorded) if fresh.get(ref) != recorded.get(ref))
        line("Re-reading the inputs gives the recorded content hashes (%s)" % kind, not differing, ", ".join(differing[:5]))
    ledger_ok, position, _ = core.verify_chain(store.read("graph_ledger"), review.LEDGER_VOLATILE)
    line("The graph ledger chain verifies", ledger_ok, "" if ledger_ok else "record %d no longer verifies" % (position + 1))
    decisions_ok, position, _ = core.verify_chain(store.read("determinations"))
    line("The determinations chain verifies", decisions_ok, "" if decisions_ok else "record %d no longer verifies" % (position + 1))
    statuses, items = store.read("unit_status"), store.read("flagged_items")
    named = {ref for item in items for ref in item["unit_refs"]}
    not_clean = {s["unit_ref"] for s in statuses if not s["clean"]}
    expected = {r["ref"] for kind in ("model_units", "chunks_doc") for r in store.read(kind)}
    reached = any(r["step_id"] == "15" for r in store.read("step_records"))
    line("Every unit has one status; units that are not clean and flagged items match",
         None if not reached else ({s["unit_ref"] for s in statuses} == expected and len(statuses) == len(expected) and not_clean == named & expected),
         "" if reached else "the run has not reached step 15, where each unit gets its status")
    known = expected | {r["ref"] for r in store.read("chunks_canon")}
    line("Every citation on Flagged_Items resolves to a unit", all(ref in known for ref in named))
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

STEP_FUNCTIONS = {        # every function that pipeline.yaml is allowed to name. Enforces: R11
    "reading.read_methodology": reading.read_methodology,
    "reading.read_documentation": reading.read_documentation,
    "reading.read_package": reading.read_package,
    "review.build_graph": review.build_graph,
    "review.extract_concepts": review.extract_concepts,
    "review.judge_concepts": review.judge_concepts,
    "review.find_candidates": review.find_candidates,
    "review.judge_links": review.judge_links, "review.interpret_code": review.interpret_code,
    "review.check_mathematics": review.check_mathematics,
    "review.check_values": review.check_values,
    "review.check_rules": review.check_rules,
    "review.check_package_docs": review.check_package_docs,
    "review.account_coverage": review.account_coverage,
    "runner.prepare_run": prepare_run,
    "runner.record_determinations": record_determinations,
    "runner.build_report": build_report}
