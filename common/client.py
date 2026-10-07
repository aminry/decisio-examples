# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""A client for a Decisio server's System One route, in plain httpx.

It does not use TypeSafe's SDK: nothing here depends on a vendor's package, and the wire format is four fields.
Decisio is an independent project, not affiliated with or endorsed by TypeSafe; it implements TypeSafe's published
System One wire format.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8000"


class DecisioError(RuntimeError):
    """The server answered with an error status; `status` and `detail` are what it said."""

    def __init__(self, status: int, detail: Any):
        super().__init__(f"decisio answered {status}: {detail}")
        self.status = status
        self.detail = detail


def noul(instructions: str, true: str | None = None, false: str | None = None) -> dict:
    """A yes/no question. The answer's `noul` is the probability of yes."""
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true, "false": false}
    return q


def choice(instructions: str, options: dict[str, str | None] | list[str]) -> dict:
    """A choice among named options. A list of keys is the same as keys with no description."""
    criteria = options if isinstance(options, dict) else {k: None for k in options}
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions: str, levels: list[str]) -> dict:
    """A score on an ordered scale, lowest level first. The answer's `score` is the probability-weighted level."""
    return {"type": "score", "instructions": instructions, "criteria": levels}


@dataclass
class Answer:
    """One request's result: the server's answers by question name, and what was measured around it."""

    answers: dict[str, dict]
    request: dict
    latency_ms: float  # the client's round trip
    server_ms: float | None  # x-decisio-server-ms
    tasks: list[str] = field(default_factory=list)  # x-decisio-tasks, the registered tasks applied
    raw: dict = field(default_factory=dict)

    def __getitem__(self, name: str) -> dict:
        return self.answers[name]

    def p_yes(self, name: str) -> float:
        return float(self.answers[name]["noul"])

    def top(self, name: str) -> tuple[str, float]:
        """The chosen option and its probability."""
        a = self.answers[name]
        return a["choice"], float(a["probabilities"][a["choice"]])


class Decisio:
    """`Decisio()` talks to `$DECISIO_URL`, else http://127.0.0.1:8000.

    A decisio server needs no model name. Ollama's decision route does: pass `model="aminroudaki/decisio-gemma"` (or set
    `$DECISIO_MODEL`) and it is sent in the request body.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 120.0, model: str | None = None):
        self.model = model or os.environ.get("DECISIO_MODEL") or None
        self.base_url = (base_url or os.environ.get("DECISIO_URL") or DEFAULT_URL).rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Decisio:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def ask(self, state: str | dict | list, questions: dict[str, dict]) -> Answer:
        body = {"state": state, "questions": questions}
        if self.model:
            body = {"model": self.model, **body}
        t0 = time.perf_counter()
        r = self._http.post("/v1/systemone", json=body)
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code != 200:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise DecisioError(r.status_code, detail)
        server_ms = r.headers.get("x-decisio-server-ms")
        tasks = [t for t in r.headers.get("x-decisio-tasks", "").split(",") if t]
        data = r.json()
        return Answer(data["answers"], body, ms, float(server_ms) if server_ms else None, tasks, data)

    def health(self) -> dict:
        r = self._http.get("/health")
        r.raise_for_status()
        return r.json()

    def models(self) -> list[str]:
        r = self._http.get("/v1/models")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def register_task(self, body: dict) -> dict:
        """POST /v1/tasks with the body docs/tasks.md describes."""
        r = self._http.post("/v1/tasks", json=body)
        if r.status_code != 200:
            raise DecisioError(r.status_code, r.text)
        return r.json()
