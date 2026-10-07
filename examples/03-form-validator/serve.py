# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Serve the form page and pass its questions on to a Decisio server.

A Decisio server sends no CORS headers, so a page cannot call it from another origin. This small server is the same
origin: it serves `index.html` and forwards `POST /ask` to the server's `/v1/systemone`, adding nothing and changing
nothing. With --record every forwarded request and its full answer is written to a run record, so a clip of a session
at the page can be checked against it.

    python examples/03-form-validator/serve.py --url http://127.0.0.1:8000 --port 18080 [--record --label <name> ...]

Stop it with Ctrl-C or a SIGTERM to its PID; the record is closed on the way out.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from questions import QUESTIONS, WARN_BELOW  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.client import Answer  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    decisio: Decisio
    run: Run | None
    lock = threading.Lock()

    def log_message(self, *args):  # the page asks often; the record is the log
        pass

    def _send(self, status: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/config":
            cfg = {"warn_below": WARN_BELOW, "questions": QUESTIONS}
            self._send(200, json.dumps(cfg).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if self.path != "/ask":
            return self._send(404, b"not found", "text/plain")
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        meta = body.pop("meta", {})
        try:
            answer: Answer = self.decisio.ask(body["state"], body["questions"])
        except DecisioError as e:
            if self.run:
                with self.lock:
                    self.run.log(e, request=body, **meta)
            return self._send(e.status, json.dumps({"detail": str(e.detail)}).encode(), "application/json")
        if self.run:
            with self.lock:
                self.run.log(answer, **meta)
        out = {"answers": answer.raw.get("answers", answer.answers), "latency_ms": answer.latency_ms}
        self._send(
            200,
            json.dumps(out).encode(),
            "application/json",
            {"x-decisio-server-ms": str(answer.server_ms) if answer.server_ms is not None else ""},
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=None, help="the Decisio server")
    ap.add_argument("--model", default=None, help="the model name, for Ollama's decision route only")
    ap.add_argument("--port", type=int, default=18080)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--label", default="session")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None)
    args = ap.parse_args()

    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    d = Decisio(args.url, model=args.model)
    run = (
        Run("03-form-validator-session", args.label, client=d, root=args.runs_root, machine=machine)
        if args.record
        else None
    )
    if run:
        run.__enter__()
    Handler.decisio, Handler.run = d, run
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    def stop(*_):
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"form page at http://127.0.0.1:{args.port}/ , questions go to {d.base_url}", file=sys.stderr)
    t0 = time.time()
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        if run:
            run.__exit__(None, None, None)
            print(f"record written to {run.dir} after {time.time() - t0:.0f} s", file=sys.stderr)
        d.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
