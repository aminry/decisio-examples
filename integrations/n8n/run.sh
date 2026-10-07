#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
# Verify n8n-nodes-jev against a Decisio server inside a real n8n: DECISIO_URL=http://127.0.0.1:8000 ./run.sh
# Needs node 22 or newer, npm and python3 (for the logging proxy). The first install pulls n8n (about 2,000 packages).
set -euo pipefail
cd "$(dirname "$0")"
: "${DECISIO_URL:?set DECISIO_URL to a Decisio server}"
npm ci --silent --no-audit --no-fund
exec node verify.mjs
