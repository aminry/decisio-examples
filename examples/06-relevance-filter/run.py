# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Filter BM25's top 10 for 400 SQuAD 2.0 queries with one request per query, and report what the filter kept.

    python examples/06-relevance-filter/run.py --url http://127.0.0.1:8000 --label <base> --record ...

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
import report  # noqa: E402
from bm25 import BM25  # noqa: E402
from questions import KEEP_AT, K, request_for  # noqa: E402

from common import Decisio, DecisioError, Run  # noqa: E402


def retrieve(limit: int | None = None):
    paragraphs, queries = data.load()
    if limit:  # an even spread over answerable and unanswerable
        half = max(1, limit // 2)
        queries = queries[: data.ANSWERABLE][:half] + queries[data.ANSWERABLE :][:half]
    index = BM25([p["title"] + " " + p["text"] for p in paragraphs])
    plan = []
    for q in queries:
        top = index.top(q["query"], K)
        plan.append((q, [paragraphs[i] for i, _ in top], [s for _, s in top]))
    return paragraphs, plan


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

    _, plan = retrieve(args.limit)
    machine = {
        "card": args.card, "power_limit_w": args.power_limit, "cpu": args.cpu, "host": args.host,
        "route": args.route, "provider": args.provider, "decisio_version": args.decisio_version,
    }  # fmt: skip
    rows: list[dict] = []
    bm25_scores: dict[str, list[float]] = {}
    with Decisio(args.url, model=args.model) as d:
        print(f"server: {d.health().get('engine')}", file=sys.stderr)
        run = (
            Run("06-relevance-filter", args.label, client=d, root=args.runs_root, machine=machine, redact=True)
            if args.record
            else None
        )
        if run:
            run.__enter__()
        try:
            for q, candidates, bm in plan:
                state, questions = request_for(q, candidates)
                try:
                    a = d.ask(state, questions)
                except DecisioError as e:
                    print(f"{q['qid']}: {e}", file=sys.stderr)
                    if run:
                        run.log(e, qid=q["qid"], request={"qid": q["qid"]})
                    continue
                scores = [a.p_yes(f"p{r}") for r in range(len(candidates))]
                pids = [c["pid"] for c in candidates]
                rows.append(
                    {
                        "qid": q["qid"],
                        "answerable": q["answerable"],
                        "gold_pid": q["pid"],
                        "candidates": pids,
                        "scores": scores,
                    }
                )
                bm25_scores[q["qid"]] = bm
                if run:
                    run.log(
                        a, qid=q["qid"], answerable=q["answerable"], gold_pid=q["pid"], candidates=pids,
                        p_yes=[round(s, 4) for s in scores], bm25=[round(s, 3) for s in bm],
                    )  # fmt: skip
            summary = report.summarise(rows, KEEP_AT, bm25_scores)
            if run:
                (run.dir / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
                (run.dir / "report.md").write_text(report.markdown(summary))
        except BaseException as e:
            if run:
                run.__exit__(type(e), e, None)
            raise
        else:
            if run:
                run.__exit__(None, None, None)
    print(report.markdown(summary))
    if not args.record:
        print("Plumbing check: nothing was recorded.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
