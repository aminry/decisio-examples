# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Ask a 77-intent question before and after teaching it from ten labelled messages per intent, and measure the change.

    python examples/07-teach-it-your-question/run.py --url http://127.0.0.1:8000 --label <base> --record ...

For each draw of examples the server is taught afresh, the same held-out test messages are asked again, and the answer
is compared with the untaught one on the same messages. Without --record it is a plumbing check and writes nothing.
Registration replaces any earlier task of the same id, and the last draw's task is deleted at the end.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import data  # noqa: E402
import questions  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.stats import bootstrap_mean  # noqa: E402


def summarise_registration(resp: dict) -> dict:
    """What the server said about each correction, as it said it: applied, why, and the cross-validation numbers."""
    out = {}
    for k in ("calibration", "head"):
        v = resp.get(k)
        if isinstance(v, dict):
            keep = ("cv_logloss",)
            out[k] = {kk: vv for kk, vv in v.items() if not isinstance(vv, (list, dict)) or kk in keep}
    return out


def report(
    plain: dict[str, bool],
    taught: list[dict[str, bool]],
    regs: list[dict],
    plain_ms: list[float],
    taught_ms: list[float],
) -> dict:
    ids = list(plain)
    n = len(ids)
    per_draw = []
    for d in taught:
        fixed = sum(1 for i in ids if d[i] and not plain[i])
        broken = sum(1 for i in ids if plain[i] and not d[i])
        per_draw.append({"accuracy": round(sum(d.values()) / n, 4), "fixed": fixed, "broken": broken})
    deltas = [sum(d[i] for d in taught) / len(taught) - plain[i] for i in ids]  # per message, over the draws
    lo, hi = bootstrap_mean(deltas)
    return {
        "test_messages": n,
        "draws": len(taught),
        "accuracy_plain": round(sum(plain.values()) / n, 4),
        "accuracy_taught_by_draw": [p["accuracy"] for p in per_draw],
        "accuracy_taught_mean": round(statistics.fmean(p["accuracy"] for p in per_draw), 4),
        "change_points": round(100 * statistics.fmean(deltas), 2),
        "change_ci95_points": [round(100 * lo, 2), round(100 * hi, 2)],
        "per_draw": per_draw,
        "registration": regs,
        "server_ms_median_plain": round(statistics.median(plain_ms), 1) if plain_ms else None,
        "server_ms_median_taught": round(statistics.median(taught_ms), 1) if taught_ms else None,
    }


def markdown(rep: dict) -> str:
    lo, hi = rep["change_ci95_points"]
    lines = [
        f"Test messages: {rep['test_messages']}, the same ones before and after, none among the registered examples.",
        "",
        f"- Untaught accuracy: {rep['accuracy_plain']:.1%}.",
        f"- Taught, mean of {rep['draws']} draws of examples: {rep['accuracy_taught_mean']:.1%} "
        "(by draw: " + ", ".join(f"{a:.1%}" for a in rep["accuracy_taught_by_draw"]) + ").",
        f"- Change: {rep['change_points']:+.1f} points (95% paired bootstrap interval "
        f"{lo:+.1f} to {hi:+.1f}, over test messages).",
        "- Per draw, messages fixed and broken: "
        + ", ".join(f"{p['fixed']} and {p['broken']}" for p in rep["per_draw"])
        + ".",
        f"- Server time per question, median: {rep['server_ms_median_plain']} ms untaught, "
        f"{rep['server_ms_median_taught']} ms taught.",
        "",
        "What the server said about each registration:",
    ]
    for i, r in enumerate(rep["registration"], 1):
        parts = [f"{k}: applied {v.get('applied')}, {v.get('reason')}" for k, v in r["server"].items()]
        lines.append(f"- Draw {i}: {r['examples']} examples registered in {r['seconds']:.0f} s; " + "; ".join(parts))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=None)
    ap.add_argument("--model", default=None, help="the model name, for Ollama's decision route only")
    ap.add_argument("--label", default="run")
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--per-intent", type=int, default=10)
    ap.add_argument("--test-size", type=int, default=1000)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None)
    args = ap.parse_args()

    train, test, intents = data.load()
    sample = data.test_sample(test, args.test_size)
    q = {"intent": questions.question(intents)}
    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip

    def ask_all(d: Decisio, run: Run | None, stage: str) -> tuple[dict[str, bool], list[float]]:
        right: dict[str, bool] = {}
        ms: list[float] = []
        for m in sample:
            try:
                a = d.ask(m["text"], q)
            except DecisioError as e:
                print(f"{m['id']}: {e}", file=sys.stderr)
                if run:
                    run.log(e, stage=stage, message=m["id"], request={"state": m["text"]})
                right[m["id"]] = False
                continue
            chose, p = a.top("intent")
            right[m["id"]] = chose == m["label"]
            if a.server_ms is not None:
                ms.append(a.server_ms)
            if run:
                run.log(a, stage=stage, message=m["id"], gold=m["label"], chose=chose, p=round(p, 4))
        return right, ms

    with Decisio(args.url, model=args.model, timeout=3600) as d:
        print(f"server: {d.health().get('engine')}", file=sys.stderr)
        d.delete_task(questions.TASK_ID)
        run = (
            Run("07-teach-it-your-question", args.label, client=d, root=args.runs_root, machine=machine)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            plain, plain_ms = ask_all(d, run, "plain")
            taught, regs, taught_ms = [], [], []
            for k in range(args.draws):
                ex = data.draw(train, intents, args.per_intent, k)
                t0 = time.time()
                resp = d.register_task(questions.registration_body(ex, intents))
                secs = time.time() - t0
                reg = {
                    "draw": k,
                    "examples": len(ex),
                    "seconds": round(secs, 1),
                    "example_ids": sorted(e["id"] for e in ex),
                    "server": summarise_registration(resp),
                }
                regs.append(reg)
                if run:
                    (run.dir / f"registration_draw{k}.json").write_text(
                        json.dumps({**reg, "response": resp}, indent=2) + "\n"
                    )
                right, ms = ask_all(d, run, f"taught_draw{k}")
                taught.append(right)
                taught_ms += ms
            d.delete_task(questions.TASK_ID)
            rep = report(plain, taught, regs, plain_ms, taught_ms)
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
