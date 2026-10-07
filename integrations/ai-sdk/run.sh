#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
# Verify the AI SDK TypeSafe provider against a Decisio server: DECISIO_URL=http://127.0.0.1:8000 ./run.sh
set -euo pipefail
cd "$(dirname "$0")"
: "${DECISIO_URL:?set DECISIO_URL to a Decisio server}"
npm ci --silent --no-audit --no-fund
exec node verify.mjs
