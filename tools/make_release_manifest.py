"""make_release_manifest.py - freezes a version: writes docs/release_manifest.json (plan, Phase 12).

The manifest holds the SHA-256 of every file of the engine (code, pipeline, skills, references),
of the notebook and of the tools, the version of every skill and the pinned requirements, so that
an evidence pack can name exactly the code that produced it.

    python tools/make_release_manifest.py            writes the manifest
    python tools/make_release_manifest.py --check    exit code 1 when a file differs from the manifest
"""
import glob
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "engine") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "engine"))

PATTERNS = ("engine/*.py", "engine/pipeline.yaml", "engine/requirements.txt", "engine/skills/*/SKILL.md", "engine/references/**/*",
            "AIVA_Interface.ipynb", "tools/*.py")


def current():
    import core
    import runner
    files = {}
    for pattern in PATTERNS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern), recursive=True)):
            if os.path.isfile(path) and "__pycache__" not in path:
                with open(path, "rb") as handle:
                    files[os.path.relpath(path, ROOT).replace(os.sep, "/")] = hashlib.sha256(handle.read()).hexdigest()
    skills = {step["skill"]: step["step_version"] for step in runner.load_pipeline()["steps"]}
    with open(os.path.join(ROOT, "engine", "requirements.txt"), encoding="utf-8") as handle:
        requirements = [line.strip() for line in handle if line.strip() and not line.startswith("#")]
    return {"engine_version": core.ENGINE_VERSION, "files": files, "skill_versions": skills, "requirements": requirements}


def main(arguments):
    target = os.path.join(ROOT, "docs", "release_manifest.json")
    now = current()
    if "--check" in arguments:
        with open(target, encoding="utf-8") as handle:
            frozen = json.load(handle)
        changed = sorted(name for name in set(now["files"]) | set(frozen["files"]) if now["files"].get(name) != frozen["files"].get(name))
        print("\n".join("differs from the release: " + name for name in changed) if changed else "Every file equals the release manifest.")
        return 1 if changed else 0
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(now, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print("%s: %d files" % (target, len(now["files"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
