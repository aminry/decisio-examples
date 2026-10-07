# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Answer questions live: keep a confident answer, send an unsure one up, and show the key afterwards.

A seeded sample of the test split, so a clip is reproducible. Without --escalate-model an escalated question goes
to "a stronger model or a person" and nothing answers it. With it, a local chat model (Ollama) answers the escalated
ones and the demo says whether it was right, so you can see what the second step buys. Nothing is hosted.

    python examples/05-escalate-when-unsure/demo.py --url http://127.0.0.1:8000 --questions 12 [--escalate-model NAME]
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import data  # noqa: E402
from questions import ask_for, lane  # noqa: E402

from common import Decisio, Run  # noqa: E402

SEED = 20261007


def ask_chat(client: httpx.Client, model: str, item: dict) -> str:
    options = "\n".join(f"{label}. {text}" for label, text in zip(item["labels"], item["texts"], strict=True))
    r = client.post(
        "/api/chat",
        json={
            "model": model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": 8},
            "messages": [
                {
                    "role": "user",
                    "content": f"{item['question']}\n{options}\nReply with only the letter of the correct option.",
                }
            ],
        },
    )
    r.raise_for_status()
    reply = r.json()["message"]["content"].strip().upper()
    return next((c for c in reply if c in item["labels"]), reply[:1])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=None)
    ap.add_argument("--model", default=None, help="the Decisio model name, for Ollama's decision route only")
    ap.add_argument("--questions", type=int, default=12)
    ap.add_argument("--escalate-model", default=None, help="a local Ollama chat model for the escalated questions")
    ap.add_argument("--chat-url", default="http://127.0.0.1:11434")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--label", default="clip")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None)
    args = ap.parse_args()

    items = random.Random(SEED).sample(data.load(), args.questions)
    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    kept = kept_right = esc = esc_right = 0
    with Decisio(args.url, model=args.model) as d, httpx.Client(base_url=args.chat_url, timeout=120) as chat:
        run = (
            Run("05-escalate-when-unsure-demo", args.label, client=d, root=args.runs_root, machine=machine, redact=True)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for i, item in enumerate(items, 1):
                state, questions = ask_for(item)
                a = d.ask(state, questions)
                chose, p = a.top("answer")
                step = lane(p)
                extra: dict = {
                    "item": item["id"],
                    "gold": item["answer"],
                    "chose": chose,
                    "p": round(p, 4),
                    "lane": step,
                }
                print(f"{i:>2}. {state[:110]}{'...' if len(state) > 110 else ''}")
                print(f"    decisio: {chose} at {p:.2f} in {a.server_ms or a.latency_ms:.0f} ms -> {step.upper()}")
                if step == "keep":
                    kept += 1
                    kept_right += chose == item["answer"]
                    print(f"    key: {item['answer']} -> {'right' if chose == item['answer'] else 'WRONG'}")
                else:
                    esc += 1
                    if args.escalate_model:
                        second = ask_chat(chat, args.escalate_model, item)
                        extra.update(escalated_to=args.escalate_model, second_choice=second)
                        esc_right += second == item["answer"]
                        print(
                            f"    escalated to {args.escalate_model}: {second}; key: {item['answer']} -> "
                            f"{'right' if second == item['answer'] else 'WRONG'}"
                        )
                    else:
                        print(
                            f"    escalated; key: {item['answer']} (decisio said {chose}: "
                            f"{'it would have been right' if chose == item['answer'] else 'it would have been wrong'})"
                        )
                print()
                if run:
                    run.log(a, **extra)
            print(
                f"kept {kept}: {kept_right} right; escalated {esc}"
                + (f": {esc_right} right after the second step" if args.escalate_model else "")
            )
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
