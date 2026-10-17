"""Open the built bundle and walk a log, a search and a checklist through it on this python."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile

BUNDLE = sys.argv[1] if len(sys.argv) > 1 else "dist/wisp.alfredworkflow"


def run(stage, env, *argv, **extra):
    command = [sys.executable, "-m", "wisp", *argv]
    finished = subprocess.run(
        command, cwd=stage, env={**env, **extra}, check=True, capture_output=True, text=True
    )
    return finished.stdout


def titles(output):
    return [row["title"] for row in json.loads(output)["items"]]


with tempfile.TemporaryDirectory() as stage, tempfile.TemporaryDirectory() as folder:
    zipfile.ZipFile(BUNDLE).extractall(stage)
    env = dict(os.environ, log_folder=folder)
    run(stage, env, "keep", "smoke test")
    assert titles(run(stage, env, "filter", "smoke")) == ['Log "smoke"', "smoke test"]
    template = run(stage, env, "start", "# smoke").strip()
    run(stage, env, "add", "one step", path=template)
    assert titles(run(stage, env, "items", template, "")) == ['Start "smoke"', "☐ one step"]
print(f"ok: {BUNDLE} answers")
