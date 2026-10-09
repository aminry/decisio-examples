#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
# Card session B: record example 7 (teach it your question) against a running decisio server.
#
#   DECISIO_URL=http://127.0.0.1:18000 CARD="..." POWER_W=600 CPU="..." DECISIO_VERSION=0.10.0 lab/session_b.sh
#
# The server must be quiet and started with no flag the session did not mean to measure. Registration is held in the
# server's memory, so nothing else may register a task with the id `banking77-intent` during the run.
# Expect about 3 x 770 registered examples and 4 x 1,000 questions: on the 31B that is roughly 30 minutes of server time.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${DECISIO_URL:?set DECISIO_URL}"; : "${CARD:?set CARD}"; : "${POWER_W:?set POWER_W}"; : "${CPU:?set CPU}"; : "${DECISIO_VERSION:?set DECISIO_VERSION}"
export DECISIO_URL
BASE=$(uv run python - <<'PY'
from common import Decisio
with Decisio() as d:
    h = d.health()
    assert h.get("ok"), h
    assert "stand-in" not in str(h.get("engine")), "this is the CPU stand-in: nothing here would be a measurement"
    print(h["base"])
PY
)
echo "server base: $BASE"
uv run python examples/07-teach-it-your-question/run.py --label "$BASE" --record --card "$CARD" --power-limit "$POWER_W" \
    --cpu "$CPU" --decisio-version "$DECISIO_VERSION"
run=$(ls -d examples/07-teach-it-your-question/runs/*_"$BASE")
echo "$run"; uv run python -m common.line "$run" || true
