"""Where the tests and tools find the engine, the notebook and the sample projects: beside this folder, in the checkout."""
import os
TESTS = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(TESTS)
REPO = os.path.dirname(ENGINE)
SAMPLES = os.path.join(TESTS, "sample_projects")
NOTEBOOK = os.path.join(REPO, "Verifier.ipynb")
FLOWR_ARCHIVES = os.environ.get("VERIFIER_FLOWR_DIR", "")   # a folder holding a staged flowR archive, where GitHub cannot be reached
