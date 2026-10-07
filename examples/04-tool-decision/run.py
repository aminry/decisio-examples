# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Score the two decisions on 62 labelled requests: the next step for each, and the risk gate for the 14 actions.

    python examples/04-tool-decision/run.py --url http://127.0.0.1:8000 --label <base> --record ...

Without --record it is a plumbing check and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from questions import HOLD_AT, NEXT_STEP, RISK, TAKE_AT, next_step, risk_state  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.stats import wilson  # noqa: E402


def load(limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "requests.jsonl").read_text().splitlines() if line.strip()]
    if limit:  # an even spread, so a short check sees every action
        step = max(1, len(rows) // limit)
        rows = rows[::step][:limit]
    return rows


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} (95% interval {lo:.1%} to {hi:.1%})"


def report(steps: list[dict], risks: list[dict]) -> dict:
    taken = [r for r in steps if r["p"] >= TAKE_AT]
    confusion = Counter((r["gold"], r["chosen"]) for r in steps)
    return {
        "requests": len(steps),
        "take_at": TAKE_AT,
        "hold_at": HOLD_AT,
        "argmax_right": sum(r["gold"] == r["chosen"] for r in steps),
        "taken": len(taken),
        "taken_right": sum(r["gold"] == r["chosen"] for r in taken),
        "fell_back_to_ask": len(steps) - len(taken),
        "wrong_and_taken": [(r["id"], r["gold"], r["chosen"], r["p"]) for r in taken if r["gold"] != r["chosen"]],
        "confusion": {f"{g}->{c}": n for (g, c), n in sorted(confusion.items())},
        "risk": {
            "calls": len(risks),
            "risky": sum(r["risky"] for r in risks),
            "risky_held": sum(r["risky"] and r["hold"] for r in risks),
            "safe": sum(not r["risky"] for r in risks),
            "safe_held": [r["id"] for r in risks if not r["risky"] and r["hold"]],
            "risky_not_held": [r["id"] for r in risks if r["risky"] and not r["hold"]],
        },
    }


def markdown(rep: dict) -> str:
    n = rep["requests"]
    k = rep["risk"]
    return (
        "\n".join(
            [
                f"Requests: {n}. The step is taken at {rep['take_at']} or more and the user is asked below it; "
                f"a call is held at {rep['hold_at']} or more (both fixed before the run).",
                "",
                f"- The model's top choice was the labelled step: {pct(rep['argmax_right'], n)}",
                f"- Taken without asking: {rep['taken']} of {n}; "
                f"right when taken: {pct(rep['taken_right'], rep['taken'])}",
                f"- Fell back to asking the user: {rep['fell_back_to_ask']}",
                "- Taken and wrong: "
                + (", ".join(f"{i} ({g} as {c}, {p:.2f})" for i, g, c, p in rep["wrong_and_taken"]) or "none"),
                "",
                f"Risk gate on the {k['calls']} proposed calls ({k['risky']} need approval, {k['safe']} do not):",
                f"- Risky calls held: {pct(k['risky_held'], k['risky'])}; "
                f"not held: {', '.join(k['risky_not_held']) or 'none'}",
                f"- Safe calls held for no reason: {pct(len(k['safe_held']), k['safe'])}; "
                f"{', '.join(k['safe_held']) or 'none'}",
            ]
        )
        + "\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=None)
    ap.add_argument("--model", default=None, help="the model name, for Ollama's decision route only")
    ap.add_argument("--label", default="run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None)
    args = ap.parse_args()

    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    steps: list[dict] = []
    risks: list[dict] = []
    with Decisio(args.url, model=args.model) as d:
        print(f"server: {d.health().get('engine')}", file=sys.stderr)
        run = (
            Run("04-tool-decision", args.label, client=d, root=args.runs_root, machine=machine) if args.record else None
        )
        if run:
            run.__enter__()
        try:
            for r in load(args.limit):
                try:
                    a = d.ask(r["request"], {"next": NEXT_STEP})
                except DecisioError as e:
                    print(f"{r['id']}: {e}", file=sys.stderr)
                    if run:
                        run.log(e, request_id=r["id"], request={"state": r["request"]})
                    continue
                chosen, p, taken = next_step(a)
                steps.append({"id": r["id"], "gold": r["action"], "chosen": chosen, "p": round(p, 4), "taken": taken})
                if run:
                    run.log(
                        a,
                        stage="next_step",
                        request_id=r["id"],
                        gold=r["action"],
                        chosen=chosen,
                        p=round(p, 4),
                        taken=taken,
                    )
                if r["action"] == "act":
                    a2 = d.ask(risk_state(r["request"], r["call"]), {"risk": RISK})
                    p_hard = a2.p_yes("risk")
                    risks.append({"id": r["id"], "risky": r["risky"], "p": round(p_hard, 4), "hold": p_hard >= HOLD_AT})
                    if run:
                        run.log(
                            a2,
                            stage="risk_gate",
                            request_id=r["id"],
                            gold_risky=r["risky"],
                            p_hard=round(p_hard, 4),
                            hold=p_hard >= HOLD_AT,
                        )
            rep = report(steps, risks)
            if run:
                (run.dir / "report.json").write_text(json.dumps(rep, indent=2) + "\n")
                (run.dir / "report.md").write_text(markdown(rep))
        except BaseException as e:
            if run:
                run.__exit__(type(e), e, None)
            raise
        else:
            if run:
                run.__exit__(None, None, None)
    print(markdown(rep))
    if not args.record:
        print("Plumbing check: nothing was recorded.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
