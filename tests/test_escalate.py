# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The report's arithmetic for example 5: coverage, accuracy among kept answers, errors escalated, and ECE."""

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "examples" / "05-escalate-when-unsure"


@pytest.fixture(scope="module")
def run05():
    sys.modules.pop("questions", None)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location("run05", HERE / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod
    sys.path.remove(str(HERE))
    sys.modules.pop("questions", None)


def rows(*pairs):
    return [{"id": f"q{i}", "answer": "A", "chose": "A", "p": p, "right": ok} for i, (p, ok) in enumerate(pairs)]


def test_at_counts_kept_escalated_and_the_errors_caught(run05):
    r = rows((0.95, True), (0.9, True), (0.85, False), (0.6, False), (0.5, True), (0.4, False))
    a = run05.at(r, 0.8)
    assert (a["kept"], a["escalated"], a["coverage"]) == (3, 3, 0.5)
    assert a["accuracy_kept"] == pytest.approx(0.667, abs=1e-3)
    assert (a["errors"], a["errors_escalated"]) == (3, 2)


def test_nothing_kept_is_reported_not_divided_by_zero(run05):
    a = run05.at(rows((0.3, True), (0.2, False)), 0.8)
    assert a["kept"] == 0 and a["accuracy_kept"] is None and a["errors_escalated"] == 1


def test_a_calibrated_set_has_zero_ece_and_an_overconfident_one_does_not(run05):
    # ten groups of ten: at confidence c, exactly c of the ten are right, so every equal-mass bin is calibrated
    calibrated = rows(*[(i / 10, k < i) for i in range(1, 11) for k in range(10)])
    assert run05.ece_equal_mass(calibrated) == pytest.approx(0.0, abs=1e-9)
    overconfident = rows(*[(0.99, True), (0.99, False)] * 20)  # every bin is 99% sure and 50% right
    assert run05.ece_equal_mass(overconfident) == pytest.approx(0.49, abs=1e-9)


def test_reliability_bins_cover_every_item(run05):
    r = rows(*[(0.1 * i, i % 2 == 0) for i in range(1, 11)])
    bins = run05.reliability(r, bins=5)
    assert sum(b["items"] for b in bins) == 10 and bins[0]["p_low"] == 0.1 and bins[-1]["p_high"] == 1.0


def test_the_report_names_the_most_confident_errors(run05):
    rep = run05.report(rows((0.99, False), (0.9, False), (0.8, True), (0.7, False), (0.6, False)))
    assert [m["p"] for m in rep["most_confident_wrong"]] == [0.99, 0.9, 0.7]
