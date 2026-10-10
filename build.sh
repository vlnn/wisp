#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

cp workflow/info.plist workflow/icon.png "$stage"/
mkdir -p "$stage/wisp"
cp src/wisp/*.py "$stage/wisp"/

mkdir -p dist
rm -f dist/Wisp.alfredworkflow
(cd "$stage" && zip -qr -X "$OLDPWD/dist/Wisp.alfredworkflow" .)

/usr/bin/env python3 - "$stage" <<'EOF'
import json, os, subprocess, sys, tempfile
stage = sys.argv[1]
folder = tempfile.mkdtemp()
env = dict(os.environ, log_folder=folder)
subprocess.run([sys.executable, "-m", "wisp", "keep", "smoke test"], cwd=stage, env=env, check=True, capture_output=True)
out = subprocess.run([sys.executable, "-m", "wisp", "filter", "smoke"], cwd=stage, env=env, check=True, capture_output=True, text=True).stdout
titles = [row["title"] for row in json.loads(out)["items"]]
assert titles == ['Log "smoke"', "smoke test"], titles
EOF

echo "dist/Wisp.alfredworkflow"
