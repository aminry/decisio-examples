# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""A small agent loop with no framework: Decisio decides what to do next, a local chat model writes what is needed.

Decisio's two questions (`questions.py`) choose the step and gate the risky calls.
A local chat model (Ollama, on your machine) writes the text a step needs: an answer, an arithmetic expression, a
question for the user, the arguments of a call. Calls are a dry run: they print what they would do and change nothing.

    python examples/04-tool-decision/agent.py --url http://127.0.0.1:8000 "What is 17.5% of 2,340?"
"""

from __future__ import annotations

import argparse
import ast
import json
import operator
import re
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from questions import HOLD_AT, NEXT_STEP, RISK, next_step, risk_state  # noqa: E402

from common import Decisio  # noqa: E402

TOOLS = "send_email, issue_refund, create_ticket, add_note, delete_workspace, close_account, reset_password"
OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.Mod: operator.mod,
}  # fmt: skip


def calc(expr: str) -> float:
    """Arithmetic only: numbers and the operators above, never eval."""

    def walk(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](walk(n.left), walk(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](walk(n.operand))
        raise ValueError(f"not arithmetic: {expr!r}")

    return walk(ast.parse(expr.replace(",", ""), mode="eval").body)


STOP = {
    "a",
    "an",
    "the",
    "of",
    "in",
    "for",
    "to",
    "and",
    "or",
    "is",
    "are",
    "do",
    "we",
    "our",
    "what",
    "which",
    "how",
    "can",
}


def _terms(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def search(query: str, k: int = 2) -> list[str]:
    """The k notes sharing the most words with the query: plain word overlap, no model."""
    lines = [ln for ln in (HERE / "corpus.md").read_text().splitlines() if ln and not ln.startswith("#")]
    words = _terms(query)
    return sorted(lines, key=lambda ln: -len(words & _terms(ln)))[:k]


class Chat:
    def __init__(self, url: str, model: str):
        self.model = model
        self.http = httpx.Client(base_url=url, timeout=120)

    def __call__(self, system: str, user: str, num_predict: int = 120) -> str:
        r = self.http.post(
            "/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": num_predict},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


def run(request: str, d: Decisio, chat: Chat) -> None:
    a = d.ask(request, {"next": NEXT_STEP})
    chosen, p, step = next_step(a)
    print(f"request: {request}")
    print(f"  decisio: {chosen} at {p:.2f} in {a.server_ms or a.latency_ms:.0f} ms -> {step}")
    if step == "answer":
        print("  reply:", chat("Answer briefly.", request))
    elif step == "search":
        found = search(request)
        print("  found:", " | ".join(found))
        print("  reply:", chat("Answer briefly, using only these notes:\n" + "\n".join(found), request))
    elif step == "calculate":
        expr = chat("Reply with only one arithmetic expression using numbers and + - * / ** %.", request, 40)
        try:
            print(f"  calculator: {expr} = {calc(expr)}")
        except (ValueError, SyntaxError, ZeroDivisionError) as e:
            print(f"  calculator refused {expr!r}: {e}")
    elif step == "ask_user":
        print("  asks:", chat("Ask one short clarifying question; do not guess.", request, 60))
    else:
        raw = chat(
            f'Reply with only JSON {{"tool": one of [{TOOLS}], "args": {{...}}}} for this request.', request, 160
        )
        try:
            call = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except (AttributeError, json.JSONDecodeError):
            print(f"  could not read a call from: {raw!r}")
            return
        g = d.ask(risk_state(request, call), {"risk": RISK})
        p_hard = g.p_yes("risk")
        verdict = "HELD for approval" if p_hard >= HOLD_AT else "would run"
        print(f"  gate: {p_hard:.2f} hard to undo in {g.server_ms or g.latency_ms:.0f} ms -> {verdict}")
        print(f"  dry run: {call}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("request", nargs="*", help="requests to run; default: the first of each kind in requests.jsonl")
    ap.add_argument("--url", default=None)
    ap.add_argument("--model", default=None, help="the Decisio model name, for Ollama's decision route only")
    ap.add_argument("--chat-url", default="http://127.0.0.1:11434")
    ap.add_argument("--chat-model", default="qwen3:0.6b")
    args = ap.parse_args()
    requests = args.request or [
        json.loads(ln)["request"] for ln in (HERE / "requests.jsonl").read_text().splitlines()[::12][:5]
    ]
    chat = Chat(args.chat_url, args.chat_model)
    with Decisio(args.url, model=args.model) as d:
        for r in requests:
            run(r, d, chat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
