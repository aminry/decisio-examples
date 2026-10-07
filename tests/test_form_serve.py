# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The form page's same-origin server passes a question on unchanged, records it, and reports an error as it came."""

import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from common import Decisio, Run
from common.recorder import read_decisions
from tests.test_common import Handler as FakeDecisio

HERE = Path(__file__).resolve().parents[1] / "examples" / "03-form-validator"


@pytest.fixture()
def serve_module():
    import sys

    sys.modules.pop("questions", None)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location("form_serve", HERE / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod
    sys.path.remove(str(HERE))
    sys.modules.pop("questions", None)


def start(handler_cls):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_page_config_and_forwarding_are_recorded(serve_module, tmp_path):
    upstream, upstream_url = start(FakeDecisio)
    with Decisio(upstream_url) as d, Run("t", "form", client=d, root=tmp_path, stamp="2026-01-01") as run:
        serve_module.Handler.decisio, serve_module.Handler.run = d, run
        front, front_url = start(serve_module.Handler)
        try:
            assert "Contact us" in httpx.get(front_url + "/").text
            cfg = httpx.get(front_url + "/config").json()
            assert cfg["warn_below"] == 0.3 and set(cfg["questions"]) == {"job_title", "company", "message"}
            body = {
                "state": {"job_title": "asdf"},
                "questions": {"job_title": {"type": "noul", "instructions": "ok?"}},
                "meta": {"trigger": "typing"},
            }
            r = httpx.post(front_url + "/ask", json=body)
            assert r.status_code == 200 and r.json()["answers"]["job_title"]["noul"] == 0.75
            assert r.headers["x-decisio-server-ms"] == "12.5"
            bad = httpx.post(front_url + "/ask", json={"state": "boom", "questions": body["questions"]})
            assert bad.status_code == 422 and bad.json()["detail"] == "bad request"
        finally:
            front.shutdown()
            upstream.shutdown()
    rows = read_decisions(tmp_path / "2026-01-01_form" / "decisions.jsonl.gz")
    assert [r.get("trigger") for r in rows] == ["typing", None]
    assert rows[0]["request"]["state"] == {"job_title": "asdf"} and "meta" not in rows[0]["request"]
    assert "error" in rows[1]
    json.dumps(rows)
