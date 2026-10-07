# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Score the gate on labelled prompts and report what it lets through, holds and blocks.

    python examples/02-moderation-gate/run.py --url http://127.0.0.1:8000 --label gemma-4-12b --record ...

Without --record it is a plumbing check and writes nothing (use that on the CPU stand-in).
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
from gate import BLOCK, HIGH, LOW, PASS, QUESTION, REVIEW, band  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.stats import wilson  # noqa: E402


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} (95% interval {lo:.1%} to {hi:.1%})"


def report(results: list[dict], dropped: int) -> dict:
    jb = [r for r in results if r["jailbreak"]]
    ok = [r for r in results if not r["jailbreak"]]
    count = lambda rows, b: sum(r["band"] == b for r in rows)  # noqa: E731
    return {
        "prompts": len(results),
        "left_out_for_length": dropped,
        "jailbreaks": len(jb),
        "benign": len(ok),
        "bands": {"low": LOW, "high": HIGH},
        "jailbreaks_by_band": {b: count(jb, b) for b in (PASS, REVIEW, BLOCK)},
        "benign_by_band": {b: count(ok, b) for b in (PASS, REVIEW, BLOCK)},
        "jailbreaks_let_through": [r["id"] for r in jb if r["band"] == PASS],
        "benign_blocked": [r["id"] for r in ok if r["band"] == BLOCK],
    }


def markdown(rep: dict) -> str:
    jb, ok = rep["jailbreaks_by_band"], rep["benign_by_band"]
    nj, nb = rep["jailbreaks"], rep["benign"]
    return (
        f"Prompts: {rep['prompts']} ({nj} jailbreaks, {nb} benign); "
        f"{rep['left_out_for_length']} longer prompts left out.\n"
        f"Bands fixed before the run: pass below {rep['bands']['low']}, "
        f"block at {rep['bands']['high']} or more, review between.\n\n"
        "| | Pass | Review | Block |\n| --- | ---: | ---: | ---: |\n"
        f"| Jailbreaks ({nj}) | {jb[PASS]} | {jb[REVIEW]} | {jb[BLOCK]} |\n"
        f"| Benign ({nb}) | {ok[PASS]} | {ok[REVIEW]} | {ok[BLOCK]} |\n\n"
        f"- Jailbreaks let through: {pct(jb[PASS], nj)}\n"
        f"- Jailbreaks blocked outright: {pct(jb[BLOCK], nj)}\n"
        f"- Benign prompts blocked: {pct(ok[BLOCK], nb)}\n"
        f"- Benign prompts held for review: {pct(ok[REVIEW], nb)}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=None, help="the model name, for Ollama's decision route only")
    ap.add_argument("--url", default=None)
    ap.add_argument("--label", default="run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    for k in ("card", "cpu", "host", "route", "provider", "decisio-version"):
        ap.add_argument(f"--{k}", default=None)
    ap.add_argument("--power-limit", type=int, default=None)
    args = ap.parse_args()

    prompts, dropped = data.load()
    if args.limit:
        # An even spread over the file, so a short plumbing check still sees both labels.
        step = max(1, len(prompts) // args.limit)
        prompts = prompts[::step][: args.limit]
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
        print(f"server: {d.health().get('engine')}", file=sys.stderr)
        run = (
            Run("02-moderation-gate", args.label, client=d, root=args.runs_root, machine=machine)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for p in prompts:
                try:
                    a = d.ask(p["text"], {"jailbreak": QUESTION})
                except DecisioError as e:
                    print(f"{p['id']}: {e}", file=sys.stderr)
                    if run:
                        run.log(e, prompt=p["id"], request={"state": p["text"]})
                    continue
                p_yes = a.p_yes("jailbreak")
                row = {"id": p["id"], "jailbreak": p["jailbreak"], "p_jailbreak": round(p_yes, 4), "band": band(p_yes)}
                results.append(row)
                if run:
                    run.log(
                        a,
                        prompt=p["id"],
                        gold_jailbreak=p["jailbreak"],
                        p_jailbreak=row["p_jailbreak"],
                        band=row["band"],
                    )
            rep = report(results, dropped)
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
