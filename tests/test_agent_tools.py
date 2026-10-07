# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The agent example's calculator takes arithmetic and nothing else; its search finds the matching note."""

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "examples" / "04-tool-decision"


@pytest.fixture(scope="module")
def agent():
    sys.modules.pop("questions", None)
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location("agent04", HERE / "agent.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod
    sys.path.remove(str(HERE))
    sys.modules.pop("questions", None)


def test_calc_does_arithmetic(agent):
    assert agent.calc("2 * 3 + 4") == 10
    assert agent.calc("0.175 * 2,340") == pytest.approx(409.5)
    assert agent.calc("-2 ** 2") == -4


@pytest.mark.parametrize("bad", ["__import__('os').system('true')", "open('x')", "a + 1", "[1, 2]"])
def test_calc_refuses_everything_else(agent, bad):
    with pytest.raises((ValueError, SyntaxError)):
        agent.calc(bad)


def test_search_finds_the_matching_note(agent):
    assert "Frankfurt" in agent.search("Which regions do we host customer data in?")[0]
    assert "50 MB" in agent.search("maximum file size for uploads")[0]
