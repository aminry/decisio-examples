# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""A logging reverse proxy between an integration and a Decisio server, standard library only.

It forwards every request unchanged to the upstream, and records what the integration sent (method, path, headers,
body) and what the server answered (status, headers, body).
Authorization-like header values are redacted before they are recorded.

    python logproxy.py --upstream http://HOST:PORT [--port 0]

On start it prints `LISTENING <port>` on stdout.
Admin routes, under `/__proxy/`, are not forwarded:

    GET  /__proxy/log     the records so far, as JSON
    POST /__proxy/reset   forget the records
    POST /__proxy/mode    {"emulate_abstention": null | "answered" | "abstained" | "abstained_not_argmax"}

The mode rewrites a 200 answer on its way back, adding the two fields Decisio documents for `--abstain-option`
(`unknown_probability`, `abstained`) to every choice and score answer.
"abstained_not_argmax" also sets a choice to its second most probable option: docs/api.md says an abstaining server
answers "the best of the other options" while the probabilities are "reported unchanged", so the answer need not be the
most probable key.
The stand-in server is not started with that option, so these are emulations of the documented shape and are labelled
so wherever a result depends on them.
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

REDACT = {"authorization", "x-api-key", "api-key", "x-typesafe-api-key", "proxy-authorization", "cookie"}
HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-connection"}


def redact(name: str, value: str) -> str:
    if name.lower() not in REDACT:
        return value
    scheme, _, rest = value.partition(" ")
    return f"{scheme} <redacted, {len(rest)} chars>" if rest else f"<redacted, {len(value)} chars>"


def emulate(body: bytes, mode: str) -> bytes:
    try:
        data = json.loads(body)
    except ValueError:
        return body
    for answer in (data.get("answers") or {}).values():
        if isinstance(answer, dict) and answer.get("type") in ("choice", "score"):
            answer["unknown_probability"] = 0.0123
            answer["abstained"] = mode != "answered"
            if mode == "abstained_not_argmax" and answer["type"] == "choice" and len(answer["probabilities"]) > 1:
                ranked = sorted(answer["probabilities"], key=answer["probabilities"].get, reverse=True)
                answer["unknown_probability"] = answer["probabilities"][ranked[0]]
                answer["choice"] = ranked[1]
    return json.dumps(data).encode()


class State:
    def __init__(self, upstream: str):
        parts = urlsplit(upstream)
        self.scheme, self.host = parts.scheme, parts.hostname
        self.port = parts.port or (443 if parts.scheme == "https" else 80)
        self.prefix = parts.path.rstrip("/")
        self.records: list[dict] = []
        self.mode: str | None = None
        self.lock = threading.Lock()


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None):
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _admin(self, length: int) -> bool:
            if not self.path.startswith("/__proxy/"):
                return False
            raw = self.rfile.read(length) if length else b""
            route = self.path[len("/__proxy/") :]
            if route == "log" and self.command == "GET":
                with state.lock:
                    out = json.dumps(state.records).encode()
            elif route == "reset" and self.command == "POST":
                with state.lock:
                    state.records.clear()
                out = b"{}"
            elif route == "mode" and self.command == "POST":
                state.mode = json.loads(raw or b"{}").get("emulate_abstention")
                out = b"{}"
            else:
                self._send(404, b"{}", {"content-type": "application/json"})
                return True
            self._send(200, out, {"content-type": "application/json"})
            return True

        def _forward(self):
            length = int(self.headers.get("content-length") or 0)
            if self._admin(length):
                return
            body = self.rfile.read(length) if length else b""
            record: dict = {
                "t": time.time(),
                "method": self.command,
                "path": self.path,
                "http_version": self.request_version,
                "headers": {k.lower(): redact(k, v) for k, v in self.headers.items()},
                "body": body.decode("utf-8", "replace"),
            }
            fwd = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP | {"host", "content-length"}}
            fwd["Host"] = f"{state.host}:{state.port}"
            conn_class = http.client.HTTPSConnection if state.scheme == "https" else http.client.HTTPConnection
            conn = conn_class(state.host, state.port, timeout=300)
            try:
                conn.request(self.command, state.prefix + self.path, body=body or None, headers=fwd)
                resp = conn.getresponse()
                data = resp.read()
                status, rheaders = resp.status, resp.getheaders()
            except OSError as e:
                record["upstream_error"] = str(e)
                with state.lock:
                    state.records.append(record)
                self._send(502, json.dumps({"detail": f"proxy could not reach upstream: {e}"}).encode())
                return
            finally:
                conn.close()
            record["upstream_status"] = status
            record["upstream_headers"] = {k.lower(): v for k, v in rheaders}
            record["upstream_body"] = data.decode("utf-8", "replace")
            if state.mode and status == 200:
                data = emulate(data, state.mode)
                record["emulated"] = state.mode
                record["returned_body"] = data.decode()
            with state.lock:
                state.records.append(record)
            out = {k: v for k, v in rheaders if k.lower() not in HOP_BY_HOP | {"content-length"}}
            self.send_response(status)
            for k, v in out.items():
                self.send_header(k, v)
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _forward

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream", required=True)
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()
    if "typesafe" in args.upstream.lower():
        sys.exit("refusing to forward to a TypeSafe host: these checks run against a Decisio server only")
    state = State(args.upstream)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    server.daemon_threads = True
    print(f"LISTENING {server.server_address[1]}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
