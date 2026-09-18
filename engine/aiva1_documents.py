"""
AIVA 0.0.1 - aiva1_documents.py - reads the methodology and the model documentation into citable chunks (placeholder of Phase 0).

WHAT THIS FILE DOES
  For Reviewer 1. In Phase 0 every step below returns an empty result, so that the runner,
  the audit store and the workbook can be proven before any reading exists.
"""
import aiva0_shared as shared

SKILL_VERSIONS = {'read-methodology': '0.0.1', 'read-documentation': '0.0.1'}

def read_methodology(ctx):
    """Placeholder for the read-methodology step: produces nothing yet."""
    return shared.StepResult()

def read_documentation(ctx):
    """Placeholder for the read-documentation step: produces nothing yet."""
    return shared.StepResult()
