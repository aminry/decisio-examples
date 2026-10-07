# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The three questions asked about every ticket, and the rule that turns the answers into a lane."""

from common import choice, noul, score

QUEUES = {
    "billing": "Invoices, payments, refunds, prices, VAT",
    "access": "Login, passwords, two-factor, SSO, permissions, invitations, account security",
    "bug": "The product behaves wrongly: errors, crashes, wrong numbers, lost data",
    "feature": "A request for something the product does not do yet",
    "cancellation": "Cancelling, pausing or closing an account, deleting data",
    "other": "Press, partners, jobs, sales pitches, wrong address, thanks, general questions",
}

QUESTIONS = {
    "urgent": noul("Does this ticket need a response within the hour?"),
    "queue": choice("Which team should handle this ticket?", QUEUES),
    "impact": score(
        "Rate the business impact using only the reported facts.",
        [
            "No function impaired",
            "One user impaired, with a workaround",
            "Many users blocked from a core function",
            "Data loss or legal exposure",
        ],
    ),
}

# Chosen before any run, and not tuned on the tickets: a queue is accepted when the model puts at least this much
# probability on it; below it the ticket goes to a person. The README's sweep shows what other values would have done.
ACCEPT_AT = 0.80
# A ticket is paged when the probability of "yes, within the hour" is at least this.
PAGE_AT = 0.50
HUMAN = "human-review"


def route(answer, accept_at: float = ACCEPT_AT, page_at: float = PAGE_AT) -> dict:
    """The lane for one ticket from its answer: the queue when the model is sure enough, else a person; and a page."""
    queue, p = answer.top("queue")
    return {
        "queue": queue,
        "p_queue": round(p, 4),
        "lane": queue if p >= accept_at else HUMAN,
        "p_urgent": round(answer.p_yes("urgent"), 4),
        "page": answer.p_yes("urgent") >= page_at,
        "impact": round(float(answer["impact"]["score"]), 2),
    }
