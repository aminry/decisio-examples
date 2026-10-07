# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Check 40 submitted forms the way the page does on Send: one request per form, three questions about it.

    python examples/03-form-validator/run.py --url http://127.0.0.1:8000 --label <base> --record ...

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

from questions import QUESTIONS, WARN_BELOW, state, warnings  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402
from common.stats import wilson  # noqa: E402


def load_forms(limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in (HERE / "forms.jsonl").read_text().splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.1%} (95% interval {lo:.1%} to {hi:.1%})"


def report(results: list[dict]) -> dict:
    out: dict = {"forms": len(results), "warn_below": WARN_BELOW, "fields": {}}
    for name in QUESTIONS:
        good = [r for r in results if r["valid"][name]]
        bad = [r for r in results if not r["valid"][name]]
        out["fields"][name] = {
            "valid_fields": len(good),
            "invalid_fields": len(bad),
            "valid_flagged": [r["id"] for r in good if r["warn"][name]],
            "invalid_caught": sum(r["warn"][name] for r in bad),
            "invalid_missed": [r["id"] for r in bad if not r["warn"][name]],
        }
    return out


def markdown(rep: dict) -> str:
    lines = [
        f"Forms: {rep['forms']}. A field is flagged when the probability that it is fine is below {rep['warn_below']}, "
        "a value fixed before the run.",
        "",
        "| Field | Valid values flagged (false warnings) | Invalid values flagged (caught) |",
        "| --- | --- | --- |",
    ]
    for name, f in rep["fields"].items():
        lines.append(
            f"| {name} | {pct(len(f['valid_flagged']), f['valid_fields'])} | "
            f"{pct(f['invalid_caught'], f['invalid_fields'])} |"
        )
    missed = [f"{name}: {', '.join(f['invalid_missed'])}" for name, f in rep["fields"].items() if f["invalid_missed"]]
    flagged = [f"{name}: {', '.join(f['valid_flagged'])}" for name, f in rep["fields"].items() if f["valid_flagged"]]
    lines += [
        "",
        "Invalid values not flagged: " + ("; ".join(missed) or "none"),
        "Valid values flagged: " + ("; ".join(flagged) or "none"),
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

    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    results: list[dict] = []
    with Decisio(args.url, model=args.model) as d:
        print(f"server: {d.health().get('engine')}", file=sys.stderr)
        run = (
            Run("03-form-validator", args.label, client=d, root=args.runs_root, machine=machine)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for form in load_forms(args.limit):
                try:
                    a = d.ask(state(form), QUESTIONS)
                except DecisioError as e:
                    print(f"{form['id']}: {e}", file=sys.stderr)
                    if run:
                        run.log(e, form=form["id"], request={"state": state(form)})
                    continue
                warn = warnings(a)
                p = {name: round(a.p_yes(name), 4) for name in QUESTIONS}
                results.append({"id": form["id"], "valid": form["valid"], "warn": warn, "p": p})
                if run:
                    run.log(a, form=form["id"], gold_valid=form["valid"], p_fine=p, warn=warn)
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
