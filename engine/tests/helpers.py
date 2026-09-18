"""helpers.py - shared by the test files: import path, scratch folders, timestamp-free comparison."""
import json
import os
import shutil
import sys
import tempfile

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(TESTS_DIR)
ROOT_DIR = os.path.dirname(ENGINE_DIR)
SAMPLES_DIR = os.path.join(TESTS_DIR, "sample_projects")
for folder in (ENGINE_DIR, TESTS_DIR, os.path.join(ROOT_DIR, "tools")):
    if folder not in sys.path:
        sys.path.insert(0, folder)

TIME_FIELDS = ("created_at", "started_at", "finished_at", "seconds", "recorded_at", "run_id", "previous_run",
               "outline_confirmed_at", "last_workbook_sha256", "last_upload_sha256", "workbook_sha256",
               "date_initiated", "project_date", "versions", "prev_hash", "record_hash")


def scratch():
    return tempfile.mkdtemp(prefix="aiva_test_")


def copy_sample(sample, projects_dir, model_id="SAMPLE", project_date="2026-09-18"):
    """Copy a sample project's Inputs into a fresh project folder, as an analyst would."""
    target = os.path.join(projects_dir, model_id, project_date, "Inputs")
    shutil.copytree(os.path.join(SAMPLES_DIR, sample, "Inputs"), target)
    return target


def without_times(value):
    if isinstance(value, dict):
        return {k: without_times(v) for k, v in value.items() if k not in TIME_FIELDS}
    if isinstance(value, list):
        return [without_times(v) for v in value]
    return value


def audit_snapshot(store, kinds):
    """The content of audit files with time stamps and run ids set aside, for comparing runs."""
    return {kind: [json.dumps(without_times(r), sort_keys=True) for r in store.read(kind)] for kind in kinds}
