# /// script
# requires-python = ">=3.10"
# dependencies = ["sentence-transformers>=3", "httpx>=0.28"]
# ///
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The usual alternative: a cross-encoder reranker, on the same queries and the same BM25 candidates.

    uv run examples/06-relevance-filter/baseline_crossencoder.py --match-run examples/06-relevance-filter/runs/<run>

It scores every (query, passage) pair with `cross-encoder/ms-marco-MiniLM-L-6-v2` (Apache-2.0, trained on MS MARCO)
and keeps, over all queries, as many passages per query on average as the Decisio run kept (the threshold is chosen to
match), so the two are compared at the same amount of context. Quality only: it runs on whatever CPU you have, and no
latency from it is comparable with a server on a card. A reranker is the standard tool for this job, and it may win.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import report  # noqa: E402
from run import retrieve  # noqa: E402

MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def target_kept(match_run: Path) -> tuple[float, float]:
    """Decisio's mean kept passages per query over all queries, and its keep_at, from its report.json."""
    rep = json.loads((match_run / "report.json").read_text())
    n_yes, n_no = rep["answerable"], rep["unanswerable"]
    mean = (rep["kept_per_answerable_query"] * n_yes + rep["kept_per_unanswerable_query"] * n_no) / (n_yes + n_no)
    return mean, rep["keep_at"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--match-run", type=Path, help="a recorded Decisio run of this example; keep as many per query")
    g.add_argument("--match-kept", type=float, help="keep this many passages per query on average")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--runs-root", default=str(HERE / "runs"))
    args = ap.parse_args()

    from sentence_transformers import CrossEncoder

    _, plan = retrieve(args.limit)
    model = CrossEncoder(MODEL)
    t0 = time.time()
    pairs = [(q["query"], c["title"] + ". " + c["text"]) for q, cands, _ in plan for c in cands]
    flat = [float(x) for x in model.predict(pairs, batch_size=32)]
    k = len(plan[0][1])
    rows, bm25_scores = [], {}
    for i, (q, cands, bm) in enumerate(plan):
        rows.append(
            {
                "qid": q["qid"], "answerable": q["answerable"], "gold_pid": q["pid"],
                "candidates": [c["pid"] for c in cands], "scores": flat[i * k : (i + 1) * k],
            }
        )  # fmt: skip
        bm25_scores[q["qid"]] = bm
    target = args.match_kept if args.match_kept is not None else target_kept(args.match_run)[0]
    threshold = report.matched_threshold(rows, target)
    summary = report.summarise(rows, threshold, bm25_scores)
    summary["matched_kept_per_query"] = round(target, 3)
    summary["model"] = MODEL
    text = report.markdown(summary).replace(
        "(fixed before the run)", "(chosen to keep as many per query as the Decisio run)"
    )
    print(text)
    if args.record:
        out = Path(args.runs_root) / f"{date.today().isoformat()}_baseline-crossencoder"
        out.mkdir(parents=True)
        with open(out / "scores.jsonl.gz", "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            for r in rows:
                gz.write((json.dumps({"qid": r["qid"], "scores": [round(s, 4) for s in r["scores"]]}) + "\n").encode())
        (out / "report.json").write_text(json.dumps(summary, indent=2) + "\n")
        (out / "report.md").write_text(text)
        (out / "manifest.json").write_text(
            json.dumps(
                {
                    "example": "06-relevance-filter-baseline", "model": MODEL, "date": date.today().isoformat(),
                    "command": " ".join(sys.argv), "python": platform.python_version(), "host": platform.platform(),
                    "seconds": round(time.time() - t0, 1),
                    "note": "quality only; this CPU's time is not comparable with a server on a card",
                },
                indent=2,
            )
            + "\n"
        )  # fmt: skip
        files = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name != "files.json"
        }
        (out / "files.json").write_text(json.dumps(files, indent=2) + "\n")
        print(f"record written to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
