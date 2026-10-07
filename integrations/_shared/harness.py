# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""What every Python integration check shares: the URL guard, the logging proxy, and the results file.

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
These checks never call TypeSafe's hosted service: the URL is refused if it names a TypeSafe host, the integration is
pointed at a local logging proxy, and the API key is a dummy.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

SHARED = Path(__file__).resolve().parent
DUMMY_KEY = "dummy-key-not-a-real-credential"
CASES = json.loads((SHARED / "cases.json").read_text())


def decisio_url() -> str:
    """The server under test, from DECISIO_URL, refused when it names a TypeSafe host."""
    url = os.environ.get("DECISIO_URL", "").rstrip("/")
    if not url:
        sys.exit("DECISIO_URL is not set: point it at a Decisio server, for example DECISIO_URL=http://127.0.0.1:8000")
    host = (urlsplit(url).hostname or "").lower()
    if not host or "typesafe" in host:
        sys.exit(
            f"refusing DECISIO_URL={url}: these checks run against a Decisio server, never TypeSafe's hosted service"
        )
    os.environ["TYPESAFE_API_KEY"] = DUMMY_KEY
    for var in ("TYPESAFE_BASE_URL", "TYPESAFE_API_URL", "JEV_API_KEY"):
        os.environ.pop(var, None)
    os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"
    return url


def assert_local(url: str) -> None:
    """The integration must only ever be given the local proxy's URL."""
    host = urlsplit(url).hostname
    assert host == "127.0.0.1", f"integration pointed at {url}, not at the local proxy"


def http_json(method: str, url: str, body: dict | None = None, timeout: float = 120) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, text = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode()
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


class Proxy:
    """A `logproxy.py` child process in front of the server under test; stopped by its own PID."""

    def __init__(self, upstream: str):
        self.upstream = upstream
        self.proc = subprocess.Popen(
            [sys.executable, str(SHARED / "logproxy.py"), "--upstream", upstream],
            stdout=subprocess.PIPE,
            text=True,
        )
        line = self.proc.stdout.readline().strip()
        if not line.startswith("LISTENING "):
            self.stop()
            sys.exit(f"the logging proxy did not start: {line!r}")
        self.url = f"http://127.0.0.1:{line.split()[1]}"

    def records(self, path_prefix: str = "") -> list[dict]:
        _, recs = http_json("GET", f"{self.url}/__proxy/log")
        return [r for r in recs if r["path"].startswith(path_prefix)]

    def reset(self) -> None:
        http_json("POST", f"{self.url}/__proxy/reset", {})

    def emulate_abstention(self, mode: str | None) -> None:
        http_json("POST", f"{self.url}/__proxy/mode", {"emulate_abstention": mode})

    def last(self) -> dict:
        recs = self.records()
        assert recs, "the proxy saw no request"
        return recs[-1]

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def __enter__(self) -> Proxy:
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


class Results:
    """Checks (assertions, a failed one fails the script), observations (facts recorded) and findings (prose)."""

    def __init__(self, name: str, versions: dict[str, str], decisio_url: str):
        self.doc: dict = {
            "integration": name,
            "versions": versions,
            "date": time.strftime("%Y-%m-%d", time.gmtime()),
            "client_python": platform.python_version(),
            "client_host": platform.platform(),
            "decisio_url_given": decisio_url,
            "server_health": None,
            "checks": [],
            "observations": {},
            "findings": [],
            "requests": [],
        }
        try:
            status, health = http_json("GET", f"{decisio_url}/health", timeout=15)
        except OSError as e:
            sys.exit(f"cannot reach {decisio_url}/health: {e}")
        if status == 200 and isinstance(health, dict):
            self.doc["server_health"] = {k: health.get(k) for k in ("ok", "engine", "model", "base")}
        else:
            sys.exit(f"{decisio_url}/health answered {status}: is the server up?")

    def check(self, check_id: str, ok: bool, detail: str = "") -> bool:
        self.doc["checks"].append({"id": check_id, "passed": bool(ok), "detail": detail})
        print(f"  {'PASS' if ok else 'FAIL'}  {check_id}  {detail}".rstrip())
        return bool(ok)

    def observe(self, key: str, value) -> None:
        self.doc["observations"][key] = value

    def finding(self, text: str) -> None:
        self.doc["findings"].append(text)

    def add_request(self, label: str, rec: dict) -> None:
        body = rec.get("body", "")
        try:
            sent = json.loads(body) if body else None
        except ValueError:
            sent = body
        self.doc["requests"].append(
            {
                "label": label,
                "method": rec["method"],
                "path": rec["path"],
                "http_version": rec.get("http_version"),
                "headers": {k: v for k, v in rec["headers"].items() if k not in ("host", "content-length")},
                "body": sent,
                "status": rec.get("upstream_status"),
                "response": _maybe_json(rec.get("returned_body") or rec.get("upstream_body")),
                "emulated_abstention": rec.get("emulated"),
            }
        )

    def finish(self, out: Path) -> None:
        passed = sum(c["passed"] for c in self.doc["checks"])
        total = len(self.doc["checks"])
        self.doc["summary"] = {
            "passed": passed,
            "failed": total - passed,
            "result": "pass" if passed == total else "fail",
        }
        text = json.dumps(self.doc, indent=2, ensure_ascii=False) + "\n"
        out.write_text(text.replace("\u2014", "-"))  # a library's em dash in a quoted message is written as a hyphen
        print(f"{self.doc['integration']}: {passed}/{total} checks passed, wrote {out}")
        sys.exit(0 if passed == total else 1)


def _maybe_json(text):
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text


def json_body(rec: dict) -> dict:
    return json.loads(rec["body"])


def raw_answers(rec: dict) -> dict:
    """The answers object of the server's own reply, as the proxy recorded it before any emulation."""
    return json.loads(rec["upstream_body"])["answers"]
