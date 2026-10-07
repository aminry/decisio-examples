#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
# Verify Pipecat's Jev client against a Decisio server: DECISIO_URL=http://127.0.0.1:8000 ./run.sh
# The install is pipecat-ai's base dependencies plus the jev extra (about 330 MB with numba and onnxruntime, no audio extras).
set -euo pipefail
cd "$(dirname "$0")"
: "${DECISIO_URL:?set DECISIO_URL to a Decisio server}"
uv venv -q --python 3.12 --allow-existing .venv
uv pip install -q --python .venv/bin/python -r requirements.txt
exec .venv/bin/python verify.py
