# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Answer 1,172 science questions with one request each, and report how well the probability says when to escalate.

    python examples/05-escalate-when-unsure/run.py --url http://127.0.0.1:8000 --label <base> --record ...

Without --record it is a plumbing check and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import data  # noqa: E402
from questions import KEEP_AT, ask_for, lane  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.stats import wilson  # noqa: E402

SWEEP = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)


def ece_equal_mass(rows: list[dict], bins: int = 10) -> float:
    """Expected calibration error over equal-mass bins of the top probability, as EVAL_CARD defines it."""
    ordered = sorted(rows, key=lambda r: r["p"])
    n = len(ordered)
    total = 0.0
    for b in range(bins):
        chunk = ordered[b * n // bins : (b + 1) * n // bins]
        if chunk:
            conf = sum(r["p"] for r in chunk) / len(chunk)
            acc = sum(r["right"] for r in chunk) / len(chunk)
            total += len(chunk) / n * abs(conf - acc)
    return total


def reliability(rows: list[dict], bins: int = 5) -> list[dict]:
    ordered = sorted(rows, key=lambda r: r["p"])
    n = len(ordered)
    out = []
    for b in range(bins):
        chunk = ordered[b * n // bins : (b + 1) * n // bins]
        if chunk:
            out.append(
                {
                    "items": len(chunk),
                    "p_low": round(chunk[0]["p"], 3),
                    "p_high": round(chunk[-1]["p"], 3),
                    "mean_p": round(sum(r["p"] for r in chunk) / len(chunk), 3),
                    "accuracy": round(sum(r["right"] for r in chunk) / len(chunk), 3),
                }
            )
    return out


def at(rows: list[dict], t: float) -> dict:
    kept = [r for r in rows if r["p"] >= t]
    wrong = [r for r in rows if not r["right"]]
    caught = sum(r["p"] < t for r in wrong)
    k = sum(r["right"] for r in kept)
    lo, hi = wilson(k, len(kept))
    return {
        "keep_at": t,
        "kept": len(kept),
        "escalated": len(rows) - len(kept),
        "coverage": round(len(kept) / len(rows), 3),
        "accuracy_kept": round(k / len(kept), 3) if kept else None,
        "accuracy_kept_ci95": [round(lo, 3), round(hi, 3)] if kept else None,
        "errors": len(wrong),
        "errors_escalated": caught,
    }


def report(rows: list[dict]) -> dict:
    overall = sum(r["right"] for r in rows) / len(rows)
    return {
        "questions": len(rows),
        "keep_at": KEEP_AT,
        "accuracy_all": round(overall, 3),
        "ece_10_equal_mass": round(ece_equal_mass(rows), 4),
        "at_preset": at(rows, KEEP_AT),
        "sweep": [at(rows, t) for t in SWEEP],
        "reliability": reliability(rows),
        "most_confident_wrong": [
            {"id": r["id"], "p": round(r["p"], 3), "chose": r["chose"], "answer": r["answer"]}
            for r in sorted((r for r in rows if not r["right"]), key=lambda r: -r["p"])[:3]
        ],
    }


def markdown(rep: dict) -> str:
    n = rep["questions"]
    a = rep["at_preset"]
    lines = [
        f"Questions: {n}. Overall accuracy {rep['accuracy_all']:.1%}; ECE {rep['ece_10_equal_mass']:.3f} "
        "(10 equal-mass bins of the top probability).",
        "",
        f"At the preset (keep at {rep['keep_at']} or more): {a['kept']} kept ({a['coverage']:.0%}), "
        f"{a['accuracy_kept']:.1%} right among them "
        f"(95% interval {a['accuracy_kept_ci95'][0]:.1%} to {a['accuracy_kept_ci95'][1]:.1%}); "
        f"{a['escalated']} escalated, which holds {a['errors_escalated']} of the {a['errors']} wrong answers."
        if a["kept"]
        else "At the preset nothing was kept.",
        "",
        "| Keep at | Kept | Coverage | Right among kept | Escalated | Wrong answers escalated |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in rep["sweep"]:
        acc = f"{s['accuracy_kept']:.1%}" if s["kept"] else "n/a"
        lines.append(
            f"| {s['keep_at']} | {s['kept']} | {s['coverage']:.0%} | {acc} | {s['escalated']} | "
            f"{s['errors_escalated']} of {s['errors']} |"
        )
    lines += ["", "| Top probability | Items | Mean probability | Accuracy |", "| --- | ---: | ---: | ---: |"]
    for b in rep["reliability"]:
        lines.append(f"| {b['p_low']} to {b['p_high']} | {b['items']} | {b['mean_p']} | {b['accuracy']:.1%} |")
    lines += [
        "",
        "Most confident wrong answers: "
        + (", ".join(f"{m['id']} ({m['p']})" for m in rep["most_confident_wrong"]) or "none"),
    ]
    return "\n".join(lines) + "\n"


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

    items = data.load()
    if args.limit:
        step = max(1, len(items) // args.limit)
        items = items[::step][: args.limit]
    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    rows: list[dict] = []
    with Decisio(args.url, model=args.model) as d:
        print(f"server: {d.health().get('engine')}", file=sys.stderr)
        run = (
            Run("05-escalate-when-unsure", args.label, client=d, root=args.runs_root, machine=machine, redact=True)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for item in items:
                state, questions = ask_for(item)
                try:
                    a = d.ask(state, questions)
                except DecisioError as e:
                    print(f"{item['id']}: {e}", file=sys.stderr)
                    if run:
                        run.log(e, item=item["id"], request={"item": item["id"]})
                    continue
                chose, p = a.top("answer")
                row = {
                    "id": item["id"],
                    "answer": item["answer"],
                    "chose": chose,
                    "p": p,
                    "right": chose == item["answer"],
                }
                rows.append(row)
                if run:
                    run.log(a, item=item["id"], gold=item["answer"], chose=chose, p=round(p, 4), lane=lane(p))
            rep = report(rows)
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
