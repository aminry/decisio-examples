# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The one measured line each example's README carries, built from a run record and nothing else.

    N decisions, median X ms server time, <base>, <card> at <power> W, <cpu>, decisio <version>;
    $Z per 1,000 decisions at $1.50 per card-hour (run `runs/...`).

Cost is EVAL_CARD's: the card-hour price divided by measured throughput, one request at a time, with nothing else
counted. Here that is the mean server time per decision times the price. The line refuses to render a cost for a run
whose server machine is not recorded, or that ran on the CPU stand-in or through Ollama, which are not the
measured system.
"""

from __future__ import annotations

import json
from pathlib import Path

CARD_HOUR_USD = 1.50


class NotMeasurable(ValueError):
    pass


def measured_line(run_dir: Path | str, card_hour_usd: float = CARD_HOUR_USD) -> str:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    summary = json.loads((run_dir / "summary.json").read_text())
    machine = manifest["server_machine"]
    health = manifest.get("server_health") or {}
    missing = [k for k in ("card", "power_limit_w", "cpu", "decisio_version") if not machine.get(k)]
    if missing:
        raise NotMeasurable(f"{run_dir}: the server's {', '.join(missing)} is not recorded; no line is written")
    engine = str(health.get("engine", ""))
    if "stand-in" in engine or machine.get("route") == "ollama":
        raise NotMeasurable(f"{run_dir}: the {engine or 'ollama'} server is not the measured system")
    server = summary.get("server_ms")
    if not server or summary["errors"]:
        raise NotMeasurable(f"{run_dir}: {summary['errors']} errors or no server times; no line is written")
    mean_s = server["mean"] / 1000
    per_1000 = card_hour_usd / 3600 * mean_s * 1000
    base = health.get("base") or "unknown base"
    return (
        f"{summary['answered']} decisions, median {server['p50']:.1f} ms server time, {base}, "
        f"{machine['card']} at {machine['power_limit_w']} W, {machine['cpu']}, decisio {machine['decisio_version']}; "
        f"${per_1000:.4f} per 1,000 decisions at ${card_hour_usd:.2f} per card-hour (run `{run_dir.as_posix()}`)."
    )
