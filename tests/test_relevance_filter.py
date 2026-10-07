# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Example 6's retriever and report arithmetic."""

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "examples" / "06-relevance-filter"


def load(name: str):
    sys.path.insert(0, str(HERE))
    try:
        spec = importlib.util.spec_from_file_location(f"ex06_{name}", HERE / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(HERE))


@pytest.fixture(scope="module")
def report():
    return load("report")


@pytest.fixture(scope="module")
def bm25():
    return load("bm25")


def row(qid, answerable, gold, scores):
    return {"qid": qid, "answerable": answerable, "gold_pid": gold, "candidates": [10, 11, 12], "scores": scores}


def test_auc_counts_ties_half(report):
    assert report.auc([0.9], [0.1, 0.2]) == 1.0
    assert report.auc([0.5], [0.5]) == 0.5
    assert report.auc([0.1], [0.9]) == 0.0
    assert report.auc([], [0.1]) is None


def test_summary_counts_gold_kept_context_and_empty_answers(report):
    rows = [
        row("a", True, 10, [0.9, 0.2, 0.1]),  # gold kept, one passage kept
        row("b", True, 11, [0.8, 0.3, 0.1]),  # gold dropped, a wrong passage kept
        row("c", True, 99, [0.9, 0.9, 0.9]),  # gold not retrieved: leaves the gold counts alone
        row("d", False, 5, [0.1, 0.2, 0.3]),  # unanswerable, nothing kept: right
        row("e", False, 5, [0.9, 0.2, 0.3]),  # unanswerable, one kept: wrong
    ]
    s = report.summarise(rows, 0.5)
    assert (s["answerable"], s["gold_retrieved"], s["gold_kept"]) == (3, 2, 1)
    assert s["kept_per_answerable_query"] == pytest.approx((1 + 1 + 3) / 3, abs=0.01)
    assert s["precision_of_kept"] == pytest.approx(1 / 5, abs=1e-3)
    assert (s["unanswerable"], s["unanswerable_kept_none"]) == (2, 1)
    assert s["top1_after_filter_scores"] == 0.5  # query a ranks its gold first, query b does not


def test_matched_threshold_keeps_the_requested_average(report):
    rows = [row("a", True, 10, [0.9, 0.5, 0.1]), row("b", True, 10, [0.8, 0.4, 0.2])]
    t = report.matched_threshold(rows, 1.5)  # three passages over two queries
    assert sum(s >= t for r in rows for s in r["scores"]) == 3


def test_markdown_survives_nothing_kept(report):
    s = report.summarise([row("a", True, 10, [0.1, 0.1, 0.1])], 0.5)
    assert "n/a" in report.markdown(s)


def test_bm25_finds_the_matching_passage_first(bm25):
    docs = [
        "the cat sat on the mat",
        "stock markets fell sharply on friday",
        "photosynthesis converts sunlight into sugar",
    ]
    top = bm25.BM25(docs).top("which process turns sunlight into sugar", 2)
    assert top[0][0] == 2 and top[0][1] > top[1][1]
    assert bm25.BM25(docs).top("zzz unknown", 1)[0][1] == 0.0
