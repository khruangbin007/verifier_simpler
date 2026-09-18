"""
AIVA 0.0.1 - aiva3_mapping.py - builds the graph, proposes candidates and asks the judge (placeholder of Phase 0).

WHAT THIS FILE DOES
  For Reviewer 3. In Phase 0 every step below returns an empty result, so that the runner,
  the audit store and the workbook can be proven before any reading exists.
"""
import aiva0_shared as shared

SKILL_VERSIONS = {'build-graph': '0.0.1', 'find-candidates': '0.0.1', 'judge-links': '0.0.1'}

def build_graph(ctx):
    """Placeholder for the build-graph step: produces nothing yet."""
    return shared.StepResult()

def find_candidates(ctx):
    """Placeholder for the find-candidates step: produces nothing yet."""
    return shared.StepResult()

def judge_links(ctx):
    """Placeholder for the judge-links step: produces nothing yet."""
    return shared.StepResult()

def validate_answer(question, response_text):
    """Placeholder validator: accepts any answer that is a JSON object."""
    import json
    try:
        answer = json.loads(response_text)
    except ValueError:
        return "rejected: " + shared.REJECTION_REASONS[0], None
    return "accepted", answer
