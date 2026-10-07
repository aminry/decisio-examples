# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Route a feed of support tickets with one request per ticket, record the run, and report what it got right.

    python examples/01-support-routing/run.py --url http://127.0.0.1:8000 --label gemma-4-12b ...

Without --record the run is a plumbing check: it prints the report and writes nothing, which is what the CPU stand-in
and any development run should do. A recorded run names the server's machine (--card, --power-limit, --cpu,
--decisio-version) so its measured line can be written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from questions import ACCEPT_AT, HUMAN, PAGE_AT, QUESTIONS, route  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.stats import wilson  # noqa: E402

SWEEP = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def load_tickets(limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "tickets.jsonl").read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def acceptable(ticket: dict) -> set[str]:
    return {ticket["queue"], *([ticket["also"]] if ticket.get("also") else [])}


def lane_table(results: list[dict]) -> list[dict]:
    """Coverage and accuracy of the routed tickets at each threshold of the sweep, from the recorded probabilities."""
    out = []
    for t in SWEEP:
        routed = [r for r in results if r["p_queue"] >= t]
        right = sum(r["queue"] in r["acceptable"] for r in routed)
        lo, hi = wilson(right, len(routed))
        out.append(
            {
                "threshold": t,
                "routed": len(routed),
                "of": len(results),
                "coverage": round(len(routed) / len(results), 3),
                "correct": right,
                "accuracy": round(right / len(routed), 3) if routed else None,
                "accuracy_ci95": [round(lo, 3), round(hi, 3)] if routed else None,
            }
        )
    return out


def report(results: list[dict]) -> dict:
    at = next(r for r in lane_table(results) if r["threshold"] == ACCEPT_AT)
    urgent_gold = [r for r in results if r["gold_urgent"]]
    paged = [r for r in results if r["page"]]
    misses = sorted((r for r in results if r["queue"] not in r["acceptable"]), key=lambda r: -r["p_queue"])
    return {
        "tickets": len(results),
        "accept_at": ACCEPT_AT,
        "page_at": PAGE_AT,
        "at_preset": at,
        "all_tickets_accuracy": round(sum(r["queue"] in r["acceptable"] for r in results) / len(results), 3),
        "sweep": lane_table(results),
        "urgent": {
            "gold_urgent": len(urgent_gold),
            "paged": len(paged),
            "paged_and_urgent": sum(r["gold_urgent"] for r in paged),
            "urgent_missed": [r["id"] for r in urgent_gold if not r["page"]],
        },
        "confident_misses": [
            {k: r[k] for k in ("id", "gold", "queue", "p_queue", "lane")} for r in misses if r["lane"] != HUMAN
        ],
        "most_confident_misses": [{k: r[k] for k in ("id", "gold", "queue", "p_queue", "lane")} for r in misses[:3]],
    }


def markdown(rep: dict) -> str:
    at = rep["at_preset"]
    if at["routed"]:
        lo, hi = at["accuracy_ci95"]
        preset = (
            f"At the preset: {at['routed']} of {at['of']} routed ({at['coverage']:.0%}), {at['correct']} right "
            f"({at['accuracy']:.1%}, 95% interval {lo:.1%} to {hi:.1%}); the rest go to a person."
        )
    else:
        preset = "At the preset: nothing was routed."
    lines = [
        f"Tickets: {rep['tickets']}. A queue is accepted at {rep['accept_at']} and a page sent at {rep['page_at']}, "
        "both fixed before the run.",
        "",
        preset,
        f"Across all tickets, ignoring the threshold: {rep['all_tickets_accuracy']:.1%}.",
        "",
        "| Accept at | Routed | Coverage | Right | Accuracy | 95% interval |",
        "| ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for s in rep["sweep"]:
        ci = f"{s['accuracy_ci95'][0]:.1%} to {s['accuracy_ci95'][1]:.1%}" if s["routed"] else "n/a"
        acc = f"{s['accuracy']:.1%}" if s["routed"] else "n/a"
        lines.append(f"| {s['threshold']} | {s['routed']} | {s['coverage']:.0%} | {s['correct']} | {acc} | {ci} |")
    u = rep["urgent"]
    lines += [
        "",
        f"Urgent: {u['gold_urgent']} tickets need an answer within the hour; {u['paged']} were paged, "
        f"{u['paged_and_urgent']} of them urgent; missed: {', '.join(u['urgent_missed']) or 'none'}.",
        "",
        "Most confident wrong answers (ticket, gold queue, chosen queue, probability):",
    ]
    for m in rep["most_confident_misses"]:
        lines.append(f"- {m['id']}: {m['gold']} routed as {m['queue']} at {m['p_queue']:.2f} ({m['lane']})")
    if not rep["most_confident_misses"]:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=None, help="the model name, for Ollama's decision route only")
    ap.add_argument("--url", default=None, help="the server (default $DECISIO_URL or http://127.0.0.1:8000)")
    ap.add_argument("--label", default="run", help="the run folder's name after the date")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--record", action="store_true", help="write runs/<date>_<label>/ (a run that counts)")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None, help="the card's power limit in W")
    args = ap.parse_args()

    tickets = load_tickets(args.limit)
    machine = {
        "card": args.card,
        "power_limit_w": args.power_limit,
        "cpu": args.cpu,
        "host": args.host,
        "route": args.route,
        "provider": args.provider,
        "decisio_version": args.decisio_version,
    }
    results: list[dict] = []
    with Decisio(args.url, model=args.model) as d:
        health = d.health()
        print(f"server: {health.get('engine')}, base {health.get('base')}", file=sys.stderr)
        run = (
            Run("01-support-routing", args.label, client=d, root=args.runs_root, machine=machine)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for t in tickets:
                try:
                    a = d.ask(t["text"], QUESTIONS)
                except DecisioError as e:
                    print(f"{t['id']}: {e}", file=sys.stderr)
                    if run:
                        run.log(e, ticket=t["id"], request={"state": t["text"]})
                    continue
                lane = route(a)
                results.append(
                    {
                        "id": t["id"],
                        "gold": t["queue"],
                        "acceptable": sorted(acceptable(t)),
                        "gold_urgent": t["urgent"],
                        **lane,
                    }
                )
                if run:
                    run.log(a, ticket=t["id"], gold=t["queue"], gold_urgent=t["urgent"], **lane)
            rep = report(results)
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
