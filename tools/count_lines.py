"""count_lines.py - line counts and docstring share of the six engine files against their budgets.

Usage: python tools/count_lines.py      (exit code 1 when a file is over budget)
Budget (plan 2.13): 1,500 lines per bundle, 450 for the shared file, counting everything;
at least 30% of each file is docstrings, comments and overview.
"""
import io
import os
import sys
import tokenize

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
BUDGETS = {"aiva0_shared.py": 450, "aiva1_documents.py": 1500, "aiva2_package.py": 1500,
           "aiva3_mapping.py": 1500, "aiva4_checks.py": 1500, "aiva5_run_report.py": 1500}
MINIMUM_EXPLANATION_SHARE = 0.30


def explanation_lines(source):
    """Line numbers that hold a docstring or a comment."""
    lines = set()
    previous = None
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            lines.add(token.start[0])
        if token.type == tokenize.STRING and (previous is None or previous.type in (
                tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.DEDENT, tokenize.ENCODING)):
            lines.update(range(token.start[0], token.end[0] + 1))
        if token.type not in (tokenize.NL, tokenize.COMMENT):
            previous = token
    return lines


def count(path):
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    total = source.count("\n") + (0 if source.endswith("\n") else 1)
    blank = sum(1 for line in source.split("\n") if not line.strip())
    explained = len(explanation_lines(source))
    return {"total": total, "explained": explained, "share": explained / max(1, total - blank), "blank": blank}


def report():
    rows, within = [], True
    for name, budget in BUDGETS.items():
        result = count(os.path.join(ENGINE_DIR, name))
        result.update(name=name, budget=budget, ok=result["total"] <= budget)
        within = within and result["ok"]
        rows.append(result)
    return rows, within


if __name__ == "__main__":
    rows, within = report()
    print("%-22s %6s %7s %10s %s" % ("file", "lines", "budget", "explained", "status"))
    for row in rows:
        print("%-22s %6d %7d %9.0f%% %s" % (row["name"], row["total"], row["budget"], 100 * row["share"],
                                             "within budget" if row["ok"] else "OVER BUDGET"))
    sys.exit(0 if within else 1)
