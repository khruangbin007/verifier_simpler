"""Hygiene the review of af0cc53 found untested: the installer, the access token in what cell 2 shows and in a failed
step's file, and the packages each run's manifest records. Exits 1 when any check fails.
  python3 test_hygiene.py                 the checks that need no network
  python3 test_hygiene.py --fresh-flowr   also fetch flowR into a fresh folder, check it and unpack it (needs GitHub)"""
import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from paths import TESTS, ENGINE, REPO, SAMPLES, NOTEBOOK, FLOWR_ARCHIVES
import ast, contextlib, glob, importlib.metadata, io, subprocess, tempfile, types, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ENGINE)
import verifier
from harness import Gateway, SETTINGS, attach, open_sample, TOKEN
failed = []
def check(label, ok, detail=""):
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", label, (" - " + detail) if detail and not ok else ""))
    if not ok:
        failed.append(label)

print("the installer, with pip replaced by a stand-in that records each command:")
real_run, restarted, calls = subprocess.run, [], []
dbutils = types.SimpleNamespace(library=types.SimpleNamespace(restartPython=lambda: restarted.append(True)))
def install_with(fail):
    calls.clear(); restarted.clear()
    def stand_in(command, capture_output=True, text=True):
        calls.append(command)
        optional = any(spec in command for spec in verifier.OPTIONAL_REQUIREMENTS)
        return types.SimpleNamespace(returncode=1 if fail == "required" or (fail == "optional" and optional) else 0,
                                     stderr="ERROR: No matching distribution found (from versions: none)", stdout="")
    subprocess.run = stand_in
    try:
        with contextlib.redirect_stdout(io.StringIO()) as said:
            verifier.install(["rdata"], dbutils)
    finally:
        subprocess.run = real_run
    return [c for c in calls if c[1:4] == ["-m", "pip", "install"]], said.getvalue()
pip, said = install_with(None)
check("the required step asks for exactly REQUIREMENTS, with pins, from PyPI",
      [a for a in pip[0] if ">=" in a] == list(verifier.REQUIREMENTS) and "-c" in pip[0] and pip[0][-1] == verifier.PYPI)
check("the optional step asks for exactly OPTIONAL_REQUIREMENTS", [a for a in pip[1] if ">=" in a] == list(verifier.OPTIONAL_REQUIREMENTS))
check("Python restarts after an install", bool(restarted))
pip, said = install_with("optional")
check("an optional package that fails is a plain note, and Python still restarts", "not installed" in said and bool(restarted))
pip, said = install_with("required")
check("a required package that fails stops before any restart", len(pip) == 1 and not restarted and "did not finish" in said)

print("the access token, in what cell 2 shows and in a failed step's file:")
attach(Gateway())
def leaking_chat(system, main, history=()):
    raise RuntimeError("401 Unauthorized: the token %s has expired" % verifier.live("llm_token"))
with contextlib.redirect_stdout(io.StringIO()) as shown:
    verifier.check_chat(leaking_chat)
check("cell 2 never shows the token a chat() error holds", TOKEN not in shown.getvalue() and "[token removed]" in shown.getvalue())
work = tempfile.mkdtemp()
verifier.step_failure({"id": "99", "name": "a step"}, RuntimeError("the token %s was refused" % TOKEN), work)
kept = open(os.path.join(work, "step_99_did_not_finish.txt")).read()
check("a failed step's file never keeps the token", TOKEN not in kept and "[token removed]" in kept)

print("the packages each run records:")
tree = ast.parse(open(os.path.join(ENGINE, "verifier.py")).read())
modules = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)} | \
          {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
owners = importlib.metadata.packages_distributions()
imported = {(owners.get(m) or [m])[0] for m in modules if m not in sys.stdlib_module_names}
check("every third-party package the engine imports is recorded, and nothing else",
      imported == set(verifier.PACKAGES_RECORDED), "imported %s, recorded %s" % (sorted(imported), sorted(verifier.PACKAGES_RECORDED)))
settings = verifier.make_settings({})
paths = open_sample("D_dosing", settings)
attach(Gateway(delay=(0, 0.001)))
verifier.run_pipeline(paths, settings)
manifest = verifier.open_store(paths, settings).read("run_manifest")[0]
check("a run's manifest holds Python's version and each package recorded", set(manifest["versions"]) == {"python"} | set(verifier.PACKAGES_RECORDED),
      "the manifest holds %s" % sorted(manifest["versions"]))

if "--fresh-flowr" in sys.argv:
    print("flowR, fetched into a fresh folder, checked and unpacked:")
    fresh = tempfile.mkdtemp(prefix="flowr-fresh-")
    done = subprocess.run([sys.executable, "-W", "always", "-c", "import verifier; print(verifier.flowr_ready())"], cwd=ENGINE,
                          env=dict(os.environ, TMPDIR=fresh), capture_output=True, text=True)
    ready = done.stdout.strip().startswith(fresh)
    executables = [p for p in glob.glob(fresh + "/**/*", recursive=True) if os.path.isfile(p) and os.access(p, os.X_OK)]
    check("flowR is ready from a fresh folder", ready, (done.stdout + done.stderr)[-300:])
    check("its programs are executable after tarfile's data filter", any(os.path.basename(p) == "flowr" for p in executables))
    check("unpacking raises no warning from tarfile", "filter" not in done.stderr.lower())

print("%d check(s) failed: %s" % (len(failed), failed) if failed else "every check passed")
sys.exit(1 if failed else 0)
