#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

cp workflow/info.plist workflow/icon.png workflow/view "$stage"/
mkdir -p "$stage/icons"
cp workflow/icons/*.png "$stage/icons"/
chmod +x "$stage/view"
mkdir -p "$stage/wisp"
cp src/wisp/*.py src/wisp/*.swift "$stage/wisp"/

version=$(git describe --tags --match 'v*' --always --dirty 2>/dev/null || echo 0.0.0)
/usr/bin/env python3 - "$stage/info.plist" "${version#v}" <<'PY'
import plistlib, sys
path, version = sys.argv[1:]
with open(path, "rb") as f:
    plist = plistlib.load(f)
plist["version"] = version
with open(path, "wb") as f:
    plistlib.dump(plist, f, sort_keys=False)
PY

mkdir -p dist
rm -f dist/Wisp.alfredworkflow
(cd "$stage" && zip -qr -X "$OLDPWD/dist/Wisp.alfredworkflow" .)

/usr/bin/env python3 - "$stage" <<'EOF'
import json, os, subprocess, sys, tempfile
stage = sys.argv[1]
with tempfile.TemporaryDirectory() as folder:
    env = dict(os.environ, log_folder=folder)
    subprocess.run([sys.executable, "-m", "wisp", "keep", "smoke test"], cwd=stage, env=env, check=True, capture_output=True)
    out = subprocess.run([sys.executable, "-m", "wisp", "filter", "smoke"], cwd=stage, env=env, check=True, capture_output=True, text=True).stdout
    template = subprocess.run([sys.executable, "-m", "wisp", "start", "# smoke"], cwd=stage, env=env, check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run([sys.executable, "-m", "wisp", "add", "one step"], cwd=stage, env=dict(env, path=template), check=True, capture_output=True)
    steps = subprocess.run([sys.executable, "-m", "wisp", "items", template, ""], cwd=stage, env=env, check=True, capture_output=True, text=True).stdout
titles = [row["title"] for row in json.loads(out)["items"]]
assert titles == ['Log "smoke"', "smoke test"], titles
step_titles = [row["title"] for row in json.loads(steps)["items"]]
assert step_titles == ['Start "smoke"', "☐ one step"], step_titles
EOF

echo "dist/Wisp.alfredworkflow ($version)"
