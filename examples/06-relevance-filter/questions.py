# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""One request per query: the query is the state, and each retrieved passage is a yes/no question about it."""

from common import noul

K = 10
# Chosen before any run and not tuned on the queries: a passage is kept when the probability that it contains the
# answer is at least this.
KEEP_AT = 0.50


def passage_question(passage: dict) -> dict:
    return noul(
        "Does the passage below contain the answer to the query?\n\n"
        f"Passage ({passage['title'].replace('_', ' ')}):\n{passage['text']}",
        true="The passage states the answer to the query",
        false="The passage is about something else, or is related but does not state the answer",
    )


def request_for(query: dict, candidates: list[dict]) -> tuple[dict, dict]:
    """The state and the questions for one query and its candidates; the question names are the candidates' ranks."""
    return {"query": query["query"]}, {f"p{rank}": passage_question(c) for rank, c in enumerate(candidates)}
