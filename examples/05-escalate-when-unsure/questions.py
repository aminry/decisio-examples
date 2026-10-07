# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""One multiple-choice question per request, and the rule that sends an unsure answer up."""

from common import choice

# Chosen before any run and not tuned on the questions: an answer is kept when its probability is at least this, and
# escalated below it. The report's sweep shows what other values would have done.
KEEP_AT = 0.80


def ask_for(item: dict) -> tuple[str, dict]:
    """The state and the questions for one item: the question is the state, the options are the choice."""
    options = dict(zip(item["labels"], item["texts"], strict=True))
    return item["question"], {"answer": choice("Which option answers the question correctly?", options)}


def lane(p: float, keep_at: float = KEEP_AT) -> str:
    return "keep" if p >= keep_at else "escalate"
