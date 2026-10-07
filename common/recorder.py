# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The run record every example writes, and the only input a clip is rendered from.

A run is a folder `runs/<date>_<label>/` holding:

    manifest.json        what ran: the example, the server's own /health, the machine the caller names, the command
    decisions.jsonl.gz   one line per request: the request as sent, the full answer, both latencies, example fields
    summary.json         counts and latency percentiles, computed from the decisions file alone
    files.json           the sha256 of every other file in the folder

The row format is the one decisio's demos write (`examples/demos/tools/decision_log.py`), so the same tools read both.
A row for third-party data keeps the item's id and the request's sha256, not its text, when the data's licence does not
allow redistribution (`redact=True`); the example's README says which.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

FORMAT = "decisio-examples-run/1"
MACHINE_FIELDS = ("card", "power_limit_w", "cpu", "host", "route", "provider", "decisio_version")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation between closest ranks, as numpy's default."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def summarise(rows: list[dict]) -> dict:
    """Counts and latency percentiles from the decision rows. Failed requests are counted, not timed."""
    ok = [r for r in rows if "error" not in r]
    out: dict = {"decisions": len(rows), "answered": len(ok), "errors": len(rows) - len(ok)}
    for key in ("latency_ms", "server_ms"):
        values = sorted(r[key] for r in ok if r.get(key) is not None)
        if values:
            out[key] = {
                "n": len(values),
                "mean": round(statistics.fmean(values), 2),
                "p50": round(_percentile(values, 0.5), 2),
                "p95": round(_percentile(values, 0.95), 2),
                "max": round(values[-1], 2),
            }
    return out


def git_commit(path: Path) -> str | None:
    try:
        sha = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
        if not sha:
            return None
        dirty = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return None


class Run:
    """Use as a context manager: `with Run("support-routing", "<base>", client=d) as run: run.log(...)`.

    `machine` names the hardware the SERVER ran on (card, power_limit_w, cpu, host, route, provider); a field not given
    is recorded as null and never guessed (/health does not report the server's version, so the caller states
    `decisio_version`). A line quoting cost needs card, power_limit_w, cpu and decisio_version.
    """

    def __init__(
        self,
        example: str,
        label: str,
        *,
        client=None,
        root: Path | str = "runs",
        machine: dict | None = None,
        stamp: str | None = None,
        redact: bool = False,
    ):
        self.example = example
        self.redact = redact
        self.dir = Path(root) / f"{stamp or date.today().isoformat()}_{label}"
        self.machine = {k: (machine or {}).get(k) for k in MACHINE_FIELDS}
        self.client = client
        self.rows: list[dict] = []
        self._path = self.dir / "decisions.jsonl"
        self.started = time.time()

    def __enter__(self) -> Run:
        if (self.dir / "manifest.json").exists():
            raise FileExistsError(f"{self.dir} already holds a run record; records are added, never rewritten")
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text("")
        self.server = self.client.health() if self.client else None
        return self

    def log(self, answer, **fields) -> dict:
        """Record one request. `answer` is a client.Answer, or an Exception for a failed request."""
        row: dict = {"ts": round(time.time(), 3), **fields}
        if isinstance(answer, Exception):
            row["error"] = str(answer)
            row["request"] = fields.pop("request", None)
        else:
            request = answer.request
            if self.redact:
                row["request_sha256"] = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            else:
                row["request"] = request
            row["response"] = answer.raw.get("answers", answer.answers)
            row["latency_ms"] = round(answer.latency_ms, 2)
            row["server_ms"] = answer.server_ms
            if answer.tasks:
                row["tasks"] = answer.tasks
        self.rows.append(row)
        with open(self._path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            return  # a failed run leaves its partial decisions file and no manifest
        gz = self.dir / "decisions.jsonl.gz"
        with open(self._path, "rb") as src, open(gz, "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as dst:
                dst.writelines(src)
        self._path.unlink()
        summary = summarise(self.rows)
        (self.dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        manifest = {
            "format": FORMAT,
            "example": self.example,
            "date": date.today().isoformat(),
            "code_commit": git_commit(Path(__file__).resolve().parent),
            "command": " ".join(sys.argv),
            "client_python": platform.python_version(),
            "client_host": platform.platform(),
            "server_machine": self.machine,
            "server_health": self.server,
            "redacted_requests": self.redact,
            "seconds": round(time.time() - self.started, 1),
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        files = {p.name: sha256_file(p) for p in sorted(self.dir.iterdir()) if p.name != "files.json"}
        (self.dir / "files.json").write_text(json.dumps(files, indent=2) + "\n")


def read_decisions(path: Path | str) -> list[dict]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]
