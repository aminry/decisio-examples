# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The one recurring question, with the same 77 options in the same order every time: that is what makes it a task."""

from common import choice

TASK_ID = "banking77-intent"
INSTRUCTIONS = "Which intent does this message from a bank's customer express?"


def question(intents: list[str]) -> dict:
    return choice(INSTRUCTIONS, {k: None for k in intents})


def registration_body(examples: list[dict], intents: list[str]) -> dict:
    """The body of POST /v1/tasks: each example is an ordinary one-question request plus the answer wanted."""
    q = question(intents)
    return {
        "id": TASK_ID,
        "examples": [
            {"request": {"state": e["text"], "questions": {"intent": q}}, "answer": e["label"]} for e in examples
        ],
    }
