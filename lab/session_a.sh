#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
# Card session A: record examples 1, 2 and 3 against a running decisio server and print each run's measured line.
#
#   DECISIO_URL=http://127.0.0.1:18000 CARD="NVIDIA RTX PRO 6000 Blackwell Workstation Edition" POWER_W=585 \
#   CPU="AMD Ryzen Threadripper 9960X" DECISIO_VERSION=0.9.0 lab/session_a.sh
#
# The server must be quiet (nothing else on the card or the host) and already started with --base and no other flag the
# session did not mean to measure. The record's label is the base the server reports, so run this once per base.
# Warm-up uses text that is in neither example, so the recorded requests are first reads of new states.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${DECISIO_URL:?set DECISIO_URL}"
: "${CARD:?set CARD}"
: "${POWER_W:?set POWER_W}"
: "${CPU:?set CPU}"
: "${DECISIO_VERSION:?set DECISIO_VERSION}"
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

echo "warm-up (not recorded)"
uv run python - <<'PY'
from common import Decisio, noul
with Decisio() as d:
    for i in range(5):
        d.ask(f"Warm-up request number {i}: the quick brown fox jumps over the lazy dog in a text unrelated to any example.",
              {"q": noul("Does this text mention an animal?")})
PY

FLAGS=(--record --card "$CARD" --power-limit "$POWER_W" --cpu "$CPU" --decisio-version "$DECISIO_VERSION")
uv run python examples/01-support-routing/run.py --label "$BASE" "${FLAGS[@]}"
uv run python examples/02-moderation-gate/run.py --label "$BASE" "${FLAGS[@]}"
uv run python examples/03-form-validator/run.py --label "$BASE" "${FLAGS[@]}"

echo
echo "measured lines"
for run in examples/0[123]-*/runs/*_"$BASE"; do
    echo "$run"
    uv run python -m common.line "$run"
done
