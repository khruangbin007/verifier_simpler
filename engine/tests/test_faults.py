import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import sys, time; sys.path.insert(0, TESTS)
from harness import *
import openpyxl, signal
signal.signal(signal.SIGINT, signal.default_int_handler)   # a background job starts with SIGINT ignored
verifier.CHAT_STOP_WAIT = 30
verifier.CHAT_BACKOFF = 0.1

def sheets(paths):
    book = openpyxl.load_workbook(os.path.join(paths.run_dir, verifier.OUTPUT_FILE), read_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True) if not (ws.title == "Model_Package_Info" and r[1] in ("Run", "Run progress", "Engine files fingerprint"))]
            for ws in book.worksheets}

def check(name, paths, settings, gateway, states):
    store = verifier.open_store(paths, settings)
    want, got = expected_columns(store, settings), workbook_columns(paths)
    phrase = " which is a major departure"             # words once refused: now kept as the model wrote them
    kept = sum(1 for value in got.values() for item in value[2] for cell in item if isinstance(cell, str) and phrase in cell)
    got = {ref: (v[0], v[1], [tuple(c.replace(phrase, "") if isinstance(c, str) else c for c in item) for item in v[2]]) for ref, v in got.items()}
    wrong = [ref for ref in want if want[ref] != got.get(ref)]
    if kept:
        print("    answers keeping words once refused, as written: %d cells" % kept)
    calls = store.read("llm_calls")
    answered = collections.Counter(c["question_id"] for c in calls if c["outcome"] == "answered")
    print("%-34s %-44s wrong %d | answered twice %d | records %d (%d not answered) | chat calls %d | most at once %d | over room %d"
          % (name, states, len(wrong), sum(1 for v in answered.values() if v > 1), len(calls),
             sum(1 for c in calls if c["outcome"] != "answered"), gateway.calls, gateway.most, len(gateway.over_room)))
    for ref in wrong[:2]:
        print("    ", ref, "want", want[ref], "\n          got ", got.get(ref))
    return store

sample = sys.argv[1] if len(sys.argv) > 1 else "F_capital"
small = {"methodology_batch_tokens": 150}

WHICH = os.environ.get('TESTS', 'BCDEF')
# B: parallelism changes nothing in the workbook
books = {}
if 'B' not in WHICH: books = None
for most in ((1, 256) if books is not None else ()):
    settings = verifier.make_settings(dict(small, parallel_chats=most))
    paths = open_sample(sample, settings); gateway = Gateway(delay=(0, 0.01)); attach(gateway)
    states = run_until_done(paths, settings)
    check("B parallel_chats=%d" % most, paths, settings, gateway, states)
    books[most] = sheets(paths)
if books: print("B same workbook at 1 and 256 at once:", books[1] == books[256])

# C: failures, malformed answers, invented refs, unwelcome words
if 'C' in WHICH:
    settings = verifier.make_settings(small)
    paths = open_sample(sample, settings)
    gateway = Gateway(fail_rate=0.25, malformed=0.3, invent=0.25, words=0.4, delay=(0, 0.01)); attach(gateway)
    states = run_until_done(paths, settings, rounds=30)
    store = check("C faults everywhere", paths, settings, gateway, states)
    happened = collections.Counter(line.split(": ", 1)[1].split(" (")[0] for c in store.read("llm_calls") for line in c["what happened"])
    print("   what happened:", dict(happened))

# D: the token runs out mid-step; a fresh one is pasted; cell 3 again
if 'D' in WHICH:
    settings = verifier.make_settings(small)
    paths = open_sample(sample, settings)
    gateway = Gateway(expire_after=150, delay=(0.01, 0.03)); attach(gateway)
    def paste(number, result):
        if result["state"] != "finished":
            records = verifier.open_store(paths, settings).read("step_records")
            print("   run %d stopped in step %s: %s" % (number + 1, records[-1]["step_id"] if records else "-", ((records[-1]["messages"] or ["-"])[-1] if records else "-")[:150]))
            verifier.NOTEBOOK["dbutils"].widgets.values["llm_token"] = TOKEN + "-fresh"
    states = run_until_done(paths, settings, between=paste)
    store = check("D token expires, fresh one pasted", paths, settings, gateway, states)
    print("   token in the run folder:", [f for f in os.popen("grep -rl '%s' %s" % (TOKEN, paths.run_dir)).read().split()] or "nowhere (raw bytes)")

# E: the cell is interrupted mid-step, twice
if 'E' in WHICH:
    settings = verifier.make_settings(small)
    paths = open_sample(sample, settings)
    gateway = Gateway(interrupt_after=120, delay=(0.01, 0.03)); attach(gateway)
    def again(number, result): pass
    results = []
    for number in range(6):
        try:
            result = verifier.run_pipeline(paths, settings); results.append(result["state"])
            if result["state"] == "finished": break
        except KeyboardInterrupt:
            held = sum(len(v) for v in verifier.ANSWERS.values())
            results.append("interrupted (%d held)" % held)
            gateway.interrupt_after = gateway.calls + 80 if number == 0 else None
    time.sleep(0.5)
    store = check("E interrupted twice", paths, settings, gateway, results)

# F: the gateway refuses large questions, so batches are split
if 'F' in WHICH:
    settings = verifier.make_settings({"methodology_batch_tokens": 12000})
    paths = open_sample(sample, settings)
    gateway = Gateway(delay=(0, 0.01), refuse=lambda kind, unit, shown: kind == verifier.METHODOLOGY_SEARCH and len(shown) > 8 and h("big", unit) % 2 == 0); attach(gateway)
    states = run_until_done(paths, settings)
    store = check("F large questions refused", paths, settings, gateway, states)
    sizes = collections.Counter(len(c["pieces"]) for c in store.read("llm_calls") if c["question_type"] == verifier.METHODOLOGY_SEARCH and c["outcome"] == "answered")
    print("   chunks per answered search question:", sorted(sizes.items()), "| refused", gateway.refused)
