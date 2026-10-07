#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
# Run the five integration checks against one Decisio server and print a summary.
#
#   DECISIO_URL=http://127.0.0.1:8000 ./run_all.sh [langchain ai-sdk ...]
#
# DECISIO_URL defaults to http://127.0.0.1:18000. It must be a Decisio server; a TypeSafe host is refused.
# Needs: uv (Python 3.12 venvs), node 22 or newer with npm, python3 (the logging proxy), and network access to
# PyPI and npm for the first install. Each check writes <integration>/results.json and exits non-zero on a failed check.
# Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
set -uo pipefail
cd "$(dirname "$0")"

DECISIO_URL="${DECISIO_URL:-http://127.0.0.1:18000}"
DECISIO_URL="${DECISIO_URL%/}"
case "$(printf '%s' "$DECISIO_URL" | tr '[:upper:]' '[:lower:]')" in
  *typesafe*) echo "refusing DECISIO_URL=$DECISIO_URL: these checks run against a Decisio server, never TypeSafe's hosted service" >&2; exit 2 ;;
esac
export DECISIO_URL

if ! curl -fsS --max-time 10 "$DECISIO_URL/health" >/dev/null; then
  echo "no healthy Decisio server at $DECISIO_URL (GET /health failed)" >&2
  exit 2
fi

ALL=(langchain ai-sdk n8n tanstack pipecat)
if [ "$#" -gt 0 ]; then TARGETS=("$@"); else TARGETS=("${ALL[@]}"); fi

failed=0
for name in "${TARGETS[@]}"; do
  echo
  echo "=== $name ==="
  rm -f "$name/results.json"
  if ! "./$name/run.sh"; then
    echo "!!! $name: failed" >&2
    failed=1
  fi
done

echo
python3 - "${TARGETS[@]}" <<'PY'
import json
import sys
from pathlib import Path

rows = []
for name in sys.argv[1:]:
    path = Path(name) / "results.json"
    if not path.exists():
        rows.append((name, "-", "no results.json (did not finish)"))
        continue
    doc = json.loads(path.read_text())
    s = doc["summary"]
    versions = ", ".join(f"{k} {v}" for k, v in doc["versions"].items() if k != "n8n-workflow")
    rows.append((name, versions, f"{s['result']} ({s['passed']}/{s['passed'] + s['failed']} checks)"))
width = [max(len(r[i]) for r in rows + [("integration", "versions", "result")]) for i in range(3)]
for r in [("integration", "versions", "result"), *rows]:
    print("  ".join(c.ljust(w) for c, w in zip(r, width)))
PY
exit "$failed"
