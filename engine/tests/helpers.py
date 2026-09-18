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


def context_for(inputs, settings=None, read=None, ask=None):
    """A step context for calling one step function directly, outside the runner."""
    import aiva0_shared as shared
    import aiva5_run_report as run
    options = {"inputs": dict({"methodology": [], "documentation": [], "package": [], "glossary": None, "tag_rules": None}, **inputs),
               "references_dir": run.REFERENCES_DIR, "run": {"model_id": "TEST", "project_date": "2026-01-01", "run_id": "Run_2026-01-01_0000"}}
    provenance = shared.Provenance("Run_2026-01-01_0000", "00", "test", "0.0.1")
    return shared.StepContext(settings or run.make_settings(), options, read or (lambda kind: []), ask, scratch(), lambda text: None, provenance)


def chunks_of(file_name, data, corner="methodology"):
    """Read one document given as bytes or text; returns (chunks as plain dictionaries, the whole step result)."""
    import aiva0_shared as shared
    import aiva1_documents
    folder = scratch()
    path = os.path.join(folder, file_name)
    with open(path, "wb") as handle:
        handle.write(data.encode("utf-8") if isinstance(data, str) else data)
    step = aiva1_documents.read_methodology if corner == "methodology" else aiva1_documents.read_documentation
    result = step(context_for({corner: [path]}))
    kind = "chunks_canon" if corner == "methodology" else "chunks_doc"
    return [shared.to_plain(chunk) for chunk in result.records[kind]], result


def units_of(files):
    """Read a package given as {path inside the package: text or bytes}; returns (units, the whole step result)."""
    import aiva0_shared as shared
    import aiva2_package
    import build_samples
    folder = scratch()
    path = os.path.join(folder, "pkg_0.1.tar.gz")
    with open(path, "wb") as handle:
        handle.write(build_samples.tarball("pkg", dict({"DESCRIPTION": "Package: pkg\nVersion: 0.1\n"}, **files)))
    result = aiva2_package.read_package(context_for({"package": [path]}))
    return [shared.to_plain(unit) for unit in result.records["model_units"]], result


def run_sample(sample, chat=None, settings=None, stop_after=""):
    """Copy a sample into a fresh project and run the pipeline on it. Returns (paths, settings, result)."""
    import aiva5_run_report as run
    import standin_chat
    projects = scratch()
    copy_sample(sample, projects, "SAMPLE", "2026-09-18")
    settings = run.make_settings(dict({"require_outline_confirmation": False}, **(settings or {})))
    paths = run.open_run(projects, "SAMPLE", "2026-09-18", scratch_root=scratch())
    result = run.run_pipeline(paths, settings, chat=chat or standin_chat.chat_well_behaved, stop_after=stop_after)
    return paths, settings, result
