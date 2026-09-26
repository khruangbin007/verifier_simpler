import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import sys, time; sys.path.insert(0, TESTS)
import harness
from harness import *
SAMPLES = sys.argv[1:] or ["A_minimal", "D_dosing", "F_capital", "F_capital_known", "G_schema", "H_twocolumn", "I_wordtraps", "J_pipeline"]
batch = 150
for sample in SAMPLES:
    settings = verifier.make_settings({"methodology_batch_tokens": batch})
    paths = open_sample(sample, settings)
    gateway = Gateway(); attach(gateway)
    t = time.time(); states = run_until_done(paths, settings); took = time.time() - t
    store = verifier.open_store(paths, settings)
    harness.assert_no_fault(store)
    want, got = expected_columns(store, settings), workbook_columns(paths)
    wrong = [ref for ref in want if want[ref] != got.get(ref)]
    calls = store.read("llm_calls")
    kinds = collections.Counter((c["question_type"], c["outcome"]) for c in calls)
    ids = collections.Counter(c["question_id"] for c in calls if c["outcome"] == "answered")
    chunks = store.read("chunks_canon"); pieces = verifier.methodology_pieces(chunks, verifier.piece_cap(settings)); plan = (pieces, verifier.methodology_batches(pieces, verifier.search_shares(settings)[0]))
    print("%-16s %s %.1fs | batches %d | calls %s | asked twice %d | most at once %d | over room %d | wrong %d"
          % (sample, states, took, len(plan[1]), dict(kinds), sum(1 for v in ids.values() if v > 1), gateway.most, len(gateway.over_room), len(wrong)))
    for ref in wrong[:3]:
        print("   ", ref, "\n      want", want[ref], "\n      got ", got.get(ref))
    import openpyxl
    rows = list(openpyxl.load_workbook(os.path.join(paths.run_dir, verifier.OUTPUT_FILE), read_only=True)["Chunks_Model"].iter_rows(values_only=True))
    at = rows[0].index("Code Interpretation (by LLM)")
    interpreted = sum(1 for r in rows[1:] if (r[at] or "").startswith("This "))
    askable = sum(1 for u in store.read("model_units") if verifier.askable(u))
    print("   step 04: %d interpretation records answered, %d of %d askable rows interpreted" % (
        kinds[(verifier.CODE_QUESTION, "answered")], interpreted, askable))
    steps = store.read("step_records")
    print("   step 05:", [(r["counts"], r["messages"]) for r in steps if r["step_id"] == "05"][-1])
