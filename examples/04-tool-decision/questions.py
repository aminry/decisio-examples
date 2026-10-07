# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The two decisions an agent makes before it acts: what to do next, and whether a proposed call needs a person."""

from common import choice, noul

ACTIONS = {
    "answer": "Reply directly from general knowledge; no tool is needed",
    "search": "Look up company documents or policies before answering",
    "calculate": "Do arithmetic, or a unit or date calculation",
    "ask_user": "The request is missing something the assistant needs, so ask a clarifying question",
    "act": "Take an action that changes something: send, create, move, refund, delete, close or reset",
}

NEXT_STEP = choice("What should the assistant do next?", ACTIONS)

RISK = noul(
    "Would this call be hard to undo, send something outside the team, move money, or delete data?",
    true="Yes: a person should approve it first",
    false="No: it is easy to undo and stays inside the team",
)

# Chosen before any run and not tuned on the requests. A next step is taken when the model puts at least this much on
# it; below it the assistant asks the user instead, which is always safe. A call is held for approval from this
# probability of "hard to undo".
TAKE_AT = 0.60
HOLD_AT = 0.50
FALLBACK = "ask_user"


def next_step(answer, take_at: float = TAKE_AT) -> tuple[str, float, str]:
    """(the model's choice, its probability, the step taken): the choice when it is sure enough, else ask the user."""
    chosen, p = answer.top("next")
    return chosen, p, chosen if p >= take_at else FALLBACK


def risk_state(request: str, call: dict) -> dict:
    return {"request": request, "proposed_call": call}
