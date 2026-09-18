"""
AIVA 0.0.1 - aiva2_package.py - reads the R package statically into model units (placeholder of Phase 0).

WHAT THIS FILE DOES
  For Reviewer 2. In Phase 0 every step below returns an empty result, so that the runner,
  the audit store and the workbook can be proven before any reading exists.
"""
import aiva0_shared as shared
import aiva1_documents as documents

SKILL_VERSIONS = {'read-package': '0.0.1'}

def read_package(ctx):
    """Placeholder for the read-package step: produces nothing yet."""
    return shared.StepResult()
