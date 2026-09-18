"""
AIVA 0.0.1 - aiva4_checks.py - checks mathematics, values, rules and package documentation, and accounts for every unit (placeholder of Phase 0).

WHAT THIS FILE DOES
  For Reviewer 4. In Phase 0 every step below returns an empty result, so that the runner,
  the audit store and the workbook can be proven before any reading exists.
"""
import aiva0_shared as shared

SKILL_VERSIONS = {'check-mathematics': '0.0.1', 'check-values': '0.0.1', 'check-rules': '0.0.1', 'check-package-docs': '0.0.1', 'account-coverage': '0.0.1'}

def check_mathematics(ctx):
    """Placeholder for the check-mathematics step: produces nothing yet."""
    return shared.StepResult()

def check_values(ctx):
    """Placeholder for the check-values step: produces nothing yet."""
    return shared.StepResult()

def check_rules(ctx):
    """Placeholder for the check-rules step: produces nothing yet."""
    return shared.StepResult()

def check_package_docs(ctx):
    """Placeholder for the check-package-docs step: produces nothing yet."""
    return shared.StepResult()

def account_coverage(ctx):
    """Placeholder for the account-coverage step: produces nothing yet."""
    return shared.StepResult()

class AivaDefect(Exception):
    """The coverage identity failed. This is a defect in AIVA, not in the model under review."""
VALUE_RULE_TEXT = "Not run yet"
