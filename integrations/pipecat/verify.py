# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Verify Pipecat's Jev client and classifier against a Decisio server (needs DECISIO_URL).

Decisio is an independent project, not affiliated with or endorsed by TypeSafe or by Pipecat's maintainers.
Everything goes through a local logging proxy in front of the server; TypeSafe's hosted service is never called.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))

import harness  # noqa: E402
from loguru import logger  # noqa: E402
from pipecat.classifiers.base_classifier import (  # noqa: E402
    ChoiceQuestion,
    ChoiceResult,
    ClassifierError,
    ScoreQuestion,
    ScoreResult,
    YesNoQuestion,
    YesNoResult,
)
from pipecat.classifiers.jev.classifier import JevClassifier  # noqa: E402
from pipecat.classifiers.jev.client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT, JevClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

PINNED = "1.12.0"
logger.remove()


async def run(res: harness.Results, proxy: harness.Proxy) -> None:
    q = harness.CASES["questions"]
    state = harness.CASES["state"]
    yes_no = {
        "urgent": YesNoQuestion(
            instructions=q["urgent"]["instructions"],
            yes=q["urgent"]["criteria"]["true"],
            no=q["urgent"]["criteria"]["false"],
        )
    }
    choice = {
        "department": ChoiceQuestion(instructions=q["department"]["instructions"], options=q["department"]["criteria"])
    }
    score = {
        "frustration": ScoreQuestion(instructions=q["frustration"]["instructions"], levels=q["frustration"]["criteria"])
    }

    # (e) defaults, from the module and the client it builds
    client = JevClient(api_key=harness.DUMMY_KEY, base_url=proxy.url)
    res.observe("default_base_url", DEFAULT_BASE_URL)
    res.observe("default_model", DEFAULT_MODEL)
    res.observe("default_timeout_s", DEFAULT_TIMEOUT)
    res.observe("client_timeout", str(client._http.timeout))
    res.observe("max_retries", "3 (JevClient.max_retries); only HTTP 429 and 529 are retried")
    res.check(
        "defaults: base_url, model, timeout",
        (DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT) == ("https://api.typesafe.ai", "jev-1.13.0", 10.0),
    )

    # connect() lists the models
    proxy.reset()
    await client.connect()
    rec = proxy.last()
    res.add_request("JevClient.connect()", rec)
    res.check(
        "connect(): GET /v1/models answered 200",
        rec["method"] == "GET" and rec["path"] == "/v1/models" and rec["upstream_status"] == 200,
    )
    res.check("connect(): Authorization Bearer sent", rec["headers"].get("authorization", "").startswith("Bearer <"))

    clf = JevClassifier(client=client)
    usage_seen: list = []

    @clf.event_handler("on_metrics")
    async def on_metrics(_classifier, data):
        usage_seen.append(data)

    # (a, b, c) each type alone through the typed classifier
    for qid, kind in (("urgent", "noul"), ("department", "choice"), ("frustration", "score")):
        proxy.reset()
        if kind == "noul":
            out = (await clf.yes_no(state, yes_no))[qid]
        elif kind == "choice":
            out = (await clf.choice(state, choice))[qid]
        else:
            out = (await clf.score(state, score))[qid]
        rec = proxy.last()
        res.add_request(f"{kind} alone (JevClassifier)", rec)
        raw = harness.raw_answers(rec)[qid]
        sent = harness.json_body(rec)
        res.check(
            f"{kind}: POST /v1/systemone hit", rec["method"] == "POST" and rec["path"] == "/v1/systemone", rec["path"]
        )
        res.check(f"{kind}: status 200", rec["upstream_status"] == 200)
        if kind == "noul":
            res.check(
                "noul: result type and probability identical to raw",
                isinstance(out, YesNoResult) and out.probability == raw["noul"],
                f"{out.probability}",
            )
            res.check("noul: is_yes is probability >= 0.5", out.is_yes == (raw["noul"] >= 0.5))
            res.observe("request_body_fields", sorted(sent))
            res.observe("model_sent", sent["model"])
            res.observe("request_headers_sent", {k: v for k, v in rec["headers"].items() if k != "host"})
            res.observe("auth_header", "Authorization: Bearer <api_key>; User-Agent python-httpx/<version>")
            res.observe("http_version_seen_by_server", rec["http_version"])
            res.check("body fields are model, state, questions", sorted(sent) == ["model", "questions", "state"])
            res.check("model sent is the default jev-1.13.0", sent["model"] == "jev-1.13.0", sent["model"])
        elif kind == "choice":
            res.check(
                "choice: type, label, probabilities, confidence identical to raw",
                isinstance(out, ChoiceResult)
                and out.choice == raw["choice"]
                and out.probabilities == raw["probabilities"]
                and out.confidence == raw["confidence"],
                out.choice,
            )
            res.check(
                "choice: options sent as criteria", sent["questions"][qid]["criteria"] == q["department"]["criteria"]
            )
        else:
            res.check(
                "score: type, score, confidence identical to raw",
                isinstance(out, ScoreResult) and out.score == raw["score"] and out.confidence == raw["confidence"],
                f"{out.score}",
            )
            res.check(
                "score: level probabilities identical to raw, in the question's order",
                [lv.probability for lv in out.levels] == [raw["probabilities"][str(i)] for i in range(3)]
                and [lv.level for lv in out.levels] == q["frustration"]["criteria"],
            )
            res.check(
                "score: levels sent as criteria", sent["questions"][qid]["criteria"] == q["frustration"]["criteria"]
            )
    await asyncio.sleep(0.2)  # event handlers run as tasks
    res.check(
        "on_metrics fired with usage after each call", len(usage_seen) == 3 and all(len(d) == 2 for d in usage_seen)
    )
    res.observe("metrics_example", [d.model_dump() if hasattr(d, "model_dump") else str(d) for d in usage_seen[-1]])

    # all three in one request, with the client's own raw interface and an object state
    proxy.reset()
    obj_state = {"customer_message": state}
    mixed = await clf.ask(obj_state, {**yes_no, **choice, **score})
    rec = proxy.last()
    res.add_request("noul + choice + score in one request, state as an object (JevClassifier.ask)", rec)
    raw = harness.raw_answers(rec)
    res.check(
        "combined: status 200, object state sent as an object",
        rec["upstream_status"] == 200 and isinstance(harness.json_body(rec)["state"], dict),
    )
    res.check(
        "combined: all three identical to raw",
        mixed["urgent"].probability == raw["urgent"]["noul"]
        and mixed["department"].probabilities == raw["department"]["probabilities"]
        and mixed["frustration"].score == raw["frustration"]["score"],
    )

    proxy.reset()
    answers, usage = await client.ask(
        state,
        {
            "urgent": {"type": "noul", "instructions": q["urgent"]["instructions"]},
            "department": {
                "type": "choice",
                "instructions": q["department"]["instructions"],
                "criteria": q["department"]["criteria"],
            },
        },
    )
    rec = proxy.last()
    raw_all = harness.json.loads(rec["upstream_body"])
    res.check(
        "JevClient.ask returns Jev's answers unchanged and usage",
        answers == {k: raw_all["answers"][k] for k in answers}
        and (usage.input_tokens, usage.output_tokens)
        == (raw_all["usage"]["input_tokens"], raw_all["usage"]["output_tokens"]),
    )
    res.check("JevClient counts usage across requests", client.usage.input_tokens > usage.input_tokens)

    # what the classifier sends for a yes/no question with only one criterion
    proxy.reset()
    await clf.yes_no(
        state,
        {"urgent": YesNoQuestion(instructions=q["urgent"]["instructions"], yes="The customer needs help right now.")},
    )
    rec = proxy.last()
    res.add_request("yes/no with only a yes criterion", rec)
    crit = harness.json_body(rec)["questions"]["urgent"].get("criteria")
    res.observe("noul_with_only_yes_sent_criteria", crit)
    res.check(
        "yes/no with only `yes`: sent criteria {true, false: ''} and the server accepts it",
        crit == {"true": "The customer needs help right now.", "false": ""} and rec["upstream_status"] == 200,
        str(crit),
    )
    res.finding(
        "A YesNoQuestion with only `yes` (or only `no`) sends the other side as an empty string, not as an "
        "absent key; Decisio accepts it (200)."
    )

    # own client path, via api_key and base_url
    own = JevClassifier(api_key=harness.DUMMY_KEY, base_url=proxy.url)
    proxy.reset()
    await own.yes_no(state, yes_no)
    res.check(
        "JevClassifier(api_key, base_url) builds its own client and reaches /v1/systemone",
        proxy.last()["path"] == "/v1/systemone",
    )
    await own.cleanup()

    try:
        JevClient(api_key="", base_url=proxy.url)
        no_key = "accepted"
    except ValueError as e:
        no_key = f"ValueError: {e}"
    res.observe("empty_api_key", no_key)
    res.check("an empty API key is refused at construction", no_key.startswith("ValueError"), no_key)

    # (d) errors
    for label, make in (
        (
            "ChoiceQuestion with no options",
            lambda: clf.choice(state, {"department": ChoiceQuestion(instructions="Which team?", options={})}),
        ),
        ("empty questions", lambda: clf.ask(state, {})),
    ):
        proxy.reset()
        err = None
        try:
            await make()
        except Exception as e:  # noqa: BLE001 - the type is the check
            err = e
        recs = proxy.records("/v1/")
        res.add_request(f"{label} (server 422)", recs[-1])
        res.check(f"422 ({label}): raised ClassifierError", isinstance(err, ClassifierError), type(err).__name__)
        res.check(f"422 ({label}): message names the status", "422" in str(err), str(err))
        res.check(
            f"422 ({label}): Decisio's detail is NOT in the message",
            "Field required" not in str(err) and "at least 1 item" not in str(err),
            str(err),
        )
        res.check(f"422 ({label}): not retried", len(recs) == 1)
        res.observe(f"422_message_{label.replace(' ', '_')}", str(err))
    res.finding(
        "A server 422 surfaces as ClassifierError('Jev rejected the request: HTTP 422') and nothing else: the "
        "response body, which in Decisio carries the field path and reason, is discarded, so the caller "
        "cannot see what was wrong with the question."
    )
    try:
        ScoreQuestion(instructions="x", levels=["only"])
        blocked = "accepted"
    except ValidationError:
        blocked = "rejected before any request: ValidationError"
    res.observe("client_side_validation", {"score_with_one_level": blocked})
    res.check("score with one level is refused in the client", blocked.startswith("rejected"))

    # (f) fields dropped, emulated
    for mode in ("answered", "abstained", "abstained_not_argmax"):
        proxy.reset()
        proxy.emulate_abstention(mode)
        err = None
        try:
            out = await clf.ask(state, {**choice, **score})
        except Exception as e:  # noqa: BLE001
            err = e
        rec = proxy.last()
        res.add_request(f"choice and score with emulated abstention fields ({mode})", rec)
        text = repr(out) if err is None else ""
        res.check(
            f"emulated {mode}: parses and does not surface abstained or unknown_probability",
            err is None and "abstained" not in text and "unknown_probability" not in text,
            str(err or ""),
        )
    proxy.emulate_abstention(None)
    res.finding(
        "EMULATED (the stand-in has no abstain option; the proxy adds the documented fields to a real "
        "answer): `abstained` and `unknown_probability` are dropped by JevClassifier, so a caller cannot tell "
        "the server abstained. JevClient.ask() returns the answer dicts unchanged, so they are visible there."
    )
    res.finding(
        "`legend` is not in a ScoreResult (the levels are the question's own, with their probabilities); "
        "`confidence` is kept on choice and score results; `usage` is summed in JevClient.usage and sent as "
        "on_metrics token usage."
    )

    await client.close()


def main() -> None:
    url = harness.decisio_url()
    version = importlib.metadata.version("pipecat-ai")
    res = harness.Results("pipecat", {"pipecat-ai": version}, url)
    res.check("pinned version installed", version == PINNED, version)
    with harness.Proxy(url) as proxy:
        harness.assert_local(proxy.url)
        asyncio.run(run(res, proxy))
    res.finish(HERE / "results.json")


if __name__ == "__main__":
    main()
