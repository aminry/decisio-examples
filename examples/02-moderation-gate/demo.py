# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The gate in front of a local chat model, on real prompts, with both times measured.

For each message the gate asks one question.
A pass goes on to the chat model (Ollama's /api/chat, streamed, so the time to its first token is measured).
A block is refused, and a review is held.
The messages are a seeded sample of the test split, short enough to read in a clip.
The chat model is not Decisio and is not hosted: it runs on your machine.

    python examples/02-moderation-gate/demo.py --url http://127.0.0.1:11434 --model aminroudaki/decisio-gemma \\
        --chat-model qwen3:0.6b --record --label laptop-clip --route ollama

A recorded laptop run carries no cost line and its probabilities are Ollama's, which applies no calibration.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import data  # noqa: E402
from gate import BLOCK, PASS, QUESTION, band  # noqa: E402

from common import Decisio, Run  # noqa: E402

SEED = 20261007
CLIP_MAX_CHARS = 300
REFUSAL = "I cannot help with that."


def chat(client: httpx.Client, model: str, text: str, num_predict: int) -> dict:
    """Stream a reply from Ollama; the time to the first content token and to the end, and the reply."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": text}],
        "stream": True,
        "think": False,
        "options": {"num_predict": num_predict, "temperature": 0},
    }
    t0 = time.perf_counter()
    first = None
    parts: list[str] = []
    with client.stream("POST", "/api/chat", json=body) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            piece = json.loads(line).get("message", {}).get("content", "")
            if piece and first is None:
                first = (time.perf_counter() - t0) * 1000
            parts.append(piece)
    return {
        "ttft_ms": round(first, 1) if first is not None else None,
        "total_ms": round((time.perf_counter() - t0) * 1000, 1),
        "reply": "".join(parts),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=None, help="the Decisio server (the gate)")
    ap.add_argument("--model", default=None, help="the gate's model name, for Ollama's decision route only")
    ap.add_argument("--chat-url", default="http://127.0.0.1:11434", help="Ollama, for the chat model")
    ap.add_argument("--chat-model", default="qwen3:0.6b")
    ap.add_argument("--messages", type=int, default=12)
    ap.add_argument("--num-predict", type=int, default=60, help="tokens the chat model may write per reply")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--label", default="clip")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None)
    args = ap.parse_args()

    prompts, _ = data.load()
    short = [p for p in prompts if len(p["text"]) <= CLIP_MAX_CHARS]
    rng = random.Random(SEED)
    half = args.messages // 2
    pool_jb = [p for p in short if p["jailbreak"]]
    pool_ok = [p for p in short if not p["jailbreak"]]
    picked = rng.sample(pool_jb, min(half, len(pool_jb))) + rng.sample(pool_ok, min(args.messages - half, len(pool_ok)))
    rng.shuffle(picked)

    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    with Decisio(args.url, model=args.model) as d, httpx.Client(base_url=args.chat_url, timeout=120) as c:
        run = (
            Run("02-moderation-gate-demo", args.label, client=d, root=args.runs_root, machine=machine)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for p in picked:
                a = d.ask(p["text"], {"jailbreak": QUESTION})
                p_yes = a.p_yes("jailbreak")
                b = band(p_yes)
                extra: dict = {
                    "prompt": p["id"],
                    "gold_jailbreak": p["jailbreak"],
                    "p_jailbreak": round(p_yes, 4),
                    "band": b,
                }
                shown = p["text"].replace("\n", " ")
                print(f"> {shown}")
                print(f"  gate: {p_yes:.2f} jailbreak, {a.server_ms or a.latency_ms:.0f} ms -> {b.upper()}")
                if b == PASS:
                    r = chat(c, args.chat_model, p["text"], args.num_predict)
                    extra.update(
                        chat_model=args.chat_model,
                        chat_ttft_ms=r["ttft_ms"],
                        chat_total_ms=r["total_ms"],
                        chat_reply=r["reply"],
                    )
                    print(f"  chat: first token after {r['ttft_ms']} ms: {r['reply'].strip()[:200]!r}")
                elif b == BLOCK:
                    print(f"  refused: {REFUSAL}")
                else:
                    print("  held for review")
                print()
                if run:
                    run.log(a, **extra)
        except BaseException as e:
            if run:
                run.__exit__(type(e), e, None)
            raise
        else:
            if run:
                run.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
