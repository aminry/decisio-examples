# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The numbers for a relevance filter, from per-query rows. Used by `run.py` and by the cross-encoder baseline.

A row: {qid, answerable, gold_pid, candidates: [pid, ...] in retrieval order, scores: [float, ...] in the same order}.
Higher means more relevant. `keep_at` turns scores into kept passages.
"""

from __future__ import annotations

from common.stats import wilson


def auc(pos: list[float], neg: list[float]) -> float | None:
    """The probability that a random relevant passage outscores a random irrelevant one (ties count half)."""
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def _gold_index(r: dict) -> int | None:
    return r["candidates"].index(r["gold_pid"]) if r["answerable"] and r["gold_pid"] in r["candidates"] else None


def summarise(rows: list[dict], keep_at: float, bm25_scores: dict[str, list[float]] | None = None) -> dict:
    yes = [r for r in rows if r["answerable"]]
    no = [r for r in rows if not r["answerable"]]
    hit = [(r, _gold_index(r)) for r in yes if _gold_index(r) is not None]
    gold_kept = sum(r["scores"][i] >= keep_at for r, i in hit)
    kept_yes = sum(s >= keep_at for r in yes for s in r["scores"])
    kept_hit_gold = gold_kept
    top1 = sum(max(range(len(r["scores"])), key=lambda j: (r["scores"][j], -j)) == i for r, i in hit)
    pos = [r["scores"][i] for r, i in hit]
    neg = [s for r, i in hit for j, s in enumerate(r["scores"]) if j != i]
    kept_no = [sum(s >= keep_at for s in r["scores"]) for r in no]
    k = len(rows[0]["scores"]) if rows else 0
    out = {
        "queries": len(rows),
        "candidates_per_query": k,
        "keep_at": keep_at,
        "answerable": len(yes),
        "gold_retrieved": len(hit),
        "gold_kept": gold_kept,
        "gold_kept_ci95": [round(x, 3) for x in wilson(gold_kept, len(hit))],
        "kept_per_answerable_query": round(kept_yes / len(yes), 2) if yes else None,
        "precision_of_kept": round(kept_hit_gold / kept_yes, 3) if kept_yes else None,
        "top1_after_filter_scores": round(top1 / len(hit), 3) if hit else None,
        "auc": round(auc(pos, neg), 3) if hit else None,
        "unanswerable": len(no),
        "unanswerable_kept_none": sum(n == 0 for n in kept_no),
        "unanswerable_kept_none_ci95": [round(x, 3) for x in wilson(sum(n == 0 for n in kept_no), len(no))],
        "kept_per_unanswerable_query": round(sum(kept_no) / len(no), 2) if no else None,
    }
    if bm25_scores:
        b_pos = [bm25_scores[r["qid"]][i] for r, i in hit]
        b_neg = [s for r, i in hit for j, s in enumerate(bm25_scores[r["qid"]]) if j != i]
        out["bm25_auc"] = round(auc(b_pos, b_neg), 3)
        out["bm25_top1"] = round(sum(i == 0 for _, i in hit) / len(hit), 3)
    return out


def matched_threshold(rows: list[dict], target_kept_per_query: float) -> float:
    """The score threshold that keeps `target_kept_per_query` passages per query on average over all rows."""
    scores = sorted((s for r in rows for s in r["scores"]), reverse=True)
    n = max(1, round(target_kept_per_query * len(rows)))
    return scores[min(n, len(scores)) - 1]


def markdown(s: dict) -> str:
    def ci(x):
        return f"{x[0]:.1%} to {x[1]:.1%}"

    def pct(x):
        return "n/a" if x is None else f"{x:.1%}"

    lines = [
        f"Queries: {s['queries']} ({s['answerable']} answerable, {s['unanswerable']} unanswerable), "
        f"{s['candidates_per_query']} candidates each from BM25. A passage is kept at {s['keep_at']} or more "
        "(fixed before the run).",
        "",
        f"- BM25's top {s['candidates_per_query']} held the relevant paragraph for {s['gold_retrieved']} of "
        f"{s['answerable']} answerable queries.",
        f"- The filter kept that paragraph for {s['gold_kept']} of those {s['gold_retrieved']} "
        f"({s['gold_kept'] / max(1, s['gold_retrieved']):.1%}, 95% interval {ci(s['gold_kept_ci95'])}).",
        f"- It kept {s['kept_per_answerable_query']} passages per answerable query out of {s['candidates_per_query']}; "
        f"{pct(s['precision_of_kept'])} of the kept passages were the relevant paragraph.",
        "- Ordering the candidates by its probability put the relevant paragraph first in "
        f"{pct(s['top1_after_filter_scores'])}"
        + (f" of queries (BM25's own order: {pct(s['bm25_top1'])})." if "bm25_top1" in s else " of queries."),
        f"- Relevant against irrelevant, as an AUC: {s['auc']}"
        + (f" (BM25's score: {s['bm25_auc']})." if "bm25_auc" in s else "."),
        f"- Unanswerable queries: it kept nothing for {s['unanswerable_kept_none']} of {s['unanswerable']} "
        f"({s['unanswerable_kept_none'] / max(1, s['unanswerable']):.1%}, "
        f"95% interval {ci(s['unanswerable_kept_none_ci95'])}); "
        f"{s['kept_per_unanswerable_query']} kept per query on average.",
    ]
    return "\n".join(lines) + "\n"
