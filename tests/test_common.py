# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The client, the recorder and the measured line, against a stdlib stand-in for the server (not a model)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from common import Decisio, DecisioError, Run, choice, measured_line, noul, score
from common.line import NotMeasurable
from common.recorder import read_decisions, summarise

HEALTH = {"ok": True, "engine": "vllm", "base": "gemma-4-12b"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, status, body, headers=None):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, HEALTH)
        elif self.path == "/v1/models":
            self._send(200, {"models": [{"name": "decisio-test"}]})
        else:
            self._send(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        if body["state"] == "boom":
            return self._send(422, {"detail": "bad request"})
        answers = {}
        for name, q in body["questions"].items():
            if q["type"] == "noul":
                answers[name] = {"type": "noul", "noul": 0.75}
            elif q["type"] == "choice":
                keys = list(q["criteria"])
                p = {k: 0.0 for k in keys}
                p[keys[0]] = 1.0
                answers[name] = {"type": "choice", "choice": keys[0], "probabilities": p}
        self._send(200, {"answers": answers}, {"x-decisio-server-ms": "12.5"})


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_ask_parses_answers_and_headers(server):
    with Decisio(server) as d:
        a = d.ask("text", {"q": noul("yes?"), "c": choice("which?", ["a", "b"])})
    assert a.p_yes("q") == 0.75
    assert a.top("c") == ("a", 1.0)
    assert a.server_ms == 12.5 and a.latency_ms > 0
    assert a.request["questions"]["c"]["criteria"] == {"a": None, "b": None}


def test_error_status_raises_with_detail(server):
    with Decisio(server) as d, pytest.raises(DecisioError) as e:
        d.ask("boom", {"q": noul("yes?")})
    assert e.value.status == 422 and e.value.detail == "bad request"


def test_health_and_models(server):
    with Decisio(server) as d:
        assert d.health()["base"] == "gemma-4-12b"
        assert d.models() == ["decisio-test"]


def test_builders():
    assert score("how bad?", ["low", "high"])["criteria"] == ["low", "high"]
    assert noul("x", true="t", false="f")["criteria"] == {"true": "t", "false": "f"}


def test_run_record_and_measured_line(server, tmp_path):
    machine = {"card": "RTX PRO 6000", "power_limit_w": 585, "cpu": "Threadripper 9960X", "decisio_version": "0.9.0"}
    with Decisio(server) as d, Run("t", "x", client=d, root=tmp_path, machine=machine, stamp="2026-01-01") as run:
        for i in range(4):
            run.log(d.ask(f"s{i}", {"q": noul("yes?")}), item=i)
    folder = tmp_path / "2026-01-01_x"
    assert sorted(p.name for p in folder.iterdir()) == [
        "decisions.jsonl.gz",
        "files.json",
        "manifest.json",
        "summary.json",
    ]
    rows = read_decisions(folder / "decisions.jsonl.gz")
    assert [r["item"] for r in rows] == [0, 1, 2, 3] and rows[0]["request"]["state"] == "s0"
    assert summarise(rows)["server_ms"]["p50"] == 12.5
    line = measured_line(folder)
    assert line.startswith("4 decisions, median 12.5 ms server time, gemma-4-12b, RTX PRO 6000 at 585 W")
    assert "$0.0052 per 1,000 decisions" in line  # 1.50 / 3600 * 0.0125 s * 1000
    with pytest.raises(FileExistsError), Run("t", "x", client=d, root=tmp_path, stamp="2026-01-01"):
        pass


def test_redacted_run_keeps_hash_not_text(server, tmp_path):
    with Decisio(server) as d, Run("t", "r", client=d, root=tmp_path, redact=True, stamp="2026-01-02") as run:
        run.log(d.ask("licensed text", {"q": noul("yes?")}), item="id-7")
    row = read_decisions(tmp_path / "2026-01-02_r" / "decisions.jsonl.gz")[0]
    assert "request" not in row and len(row["request_sha256"]) == 64 and "licensed text" not in json.dumps(row)


def test_line_refuses_unrecorded_machine_and_stand_in(server, tmp_path):
    with Decisio(server) as d, Run("t", "u", client=d, root=tmp_path, stamp="2026-01-03") as run:
        run.log(d.ask("s", {"q": noul("yes?")}))
    with pytest.raises(NotMeasurable, match="card, power_limit_w, cpu, decisio_version"):
        measured_line(tmp_path / "2026-01-03_u")
