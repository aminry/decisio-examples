# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Example 7: the registration body, the draws, and the report's arithmetic."""

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "examples" / "07-teach-it-your-question"


def load(name):
    for m in ("questions", "data", "run07"):
        sys.modules.pop(m, None)
    sys.path.insert(0, str(HERE))
    try:
        spec = importlib.util.spec_from_file_location(name, HERE / f"{'run' if name == 'run07' else name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(str(HERE))


def test_registration_body_is_one_question_requests_with_the_same_options():
    q = load("questions")
    intents = ["a_one", "b_two", "c_three"]
    body = q.registration_body([{"text": "hello", "label": "b_two"}, {"text": "bye", "label": "a_one"}], intents)
    assert body["id"] == q.TASK_ID and [e["answer"] for e in body["examples"]] == ["b_two", "a_one"]
    for e in body["examples"]:
        assert list(e["request"]["questions"]) == ["intent"]
        assert list(e["request"]["questions"]["intent"]["criteria"]) == intents  # same keys, same order


def test_draws_have_ten_per_intent_differ_by_draw_and_repeat_for_the_same_draw():
    d = load("data")
    train = [{"id": f"t{i}", "text": str(i), "label": f"l{i % 4}"} for i in range(80)]
    intents = ["l0", "l1", "l2", "l3"]
    a, b, a2 = d.draw(train, intents, 5, 0), d.draw(train, intents, 5, 1), d.draw(train, intents, 5, 0)
    assert [x["id"] for x in a] == [x["id"] for x in a2] and {x["id"] for x in a} != {x["id"] for x in b}
    assert all(sum(x["label"] == i for x in a) == 5 for i in intents)


def test_report_pairs_the_same_messages_and_counts_fixed_and_broken():
    r = load("run07")
    plain = {"m1": True, "m2": False, "m3": False, "m4": True}
    taught = [{"m1": True, "m2": True, "m3": False, "m4": False}, {"m1": True, "m2": True, "m3": True, "m4": True}]
    rep = r.report(plain, taught, [], [10.0, 20.0], [30.0, 50.0])
    assert rep["accuracy_plain"] == 0.5 and rep["accuracy_taught_mean"] == 0.75
    assert [(p["fixed"], p["broken"]) for p in rep["per_draw"]] == [(1, 1), (2, 0)]
    assert rep["change_points"] == pytest.approx(25.0) and rep["server_ms_median_taught"] == 40.0
    assert rep["change_ci95_points"][0] <= 25.0 <= rep["change_ci95_points"][1]


def test_registration_summary_keeps_what_the_server_said_and_drops_the_arrays():
    r = load("run07")
    s = r.summarise_registration(
        {
            "head": {"applied": True, "reason": "cross-validated gain", "w": [1, 2]},
            "calibration": {"applied": False, "reason": "not needed"},
        }
    )
    assert s["head"] == {"applied": True, "reason": "cross-validated gain"} and s["calibration"]["applied"] is False
