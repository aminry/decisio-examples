# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The three questions a form is checked with, and the rule that turns a probability into a soft warning."""

from common import noul

QUESTIONS = {
    "job_title": noul(
        "Is the job_title field a plausible job title?",
        true="A real job title or role, in any industry",
        false="A placeholder, random characters, a joke, or something that is not a role",
    ),
    "company": noul(
        "Is the company field a plausible name of an organisation?",
        true="The name of a company, school, council, charity or other organisation",
        false="A placeholder, random characters, a number, or a bare person's name",
    ),
    "message": noul(
        "Does the message field state a real question, problem or request?",
        true="A genuine question, problem or request, even a short one",
        false="Placeholder or random text, a greeting alone, or nothing meaningful",
    ),
}

# Chosen before any run and not tuned on the forms: a field is flagged when the probability that it is fine falls
# below this. The flag is a soft warning beside the field. It never blocks the form.
WARN_BELOW = 0.30


def state(form: dict) -> dict:
    """The form as the state: the fields the person typed, under their names."""
    return {k: form[k] for k in QUESTIONS}


def warnings(answer, warn_below: float = WARN_BELOW) -> dict[str, bool]:
    return {name: answer.p_yes(name) < warn_below for name in QUESTIONS}
