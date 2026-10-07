# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Verify langchain-typesafe's TypeSafeClassifier against a Decisio server (needs DECISIO_URL).

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
Everything goes through a local logging proxy in front of the server; TypeSafe's hosted service is never called.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))

import harness  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_typesafe import (  # noqa: E402
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    NoulCriteria,
    Score,
    ScoreAnswer,
    TypeSafeClassifier,
)
from langchain_typesafe.client import TypeSafeAPIError, TypeSafeUnprocessableEntityError  # noqa: E402

PINNED = "0.0.1a3"


def build_questions() -> dict:
    q = harness.CASES["questions"]
    return {
        "urgent": Noul(instructions=q["urgent"]["instructions"], criteria=NoulCriteria(**q["urgent"]["criteria"])),
        "department": Choice(instructions=q["department"]["instructions"], criteria=q["department"]["criteria"]),
        "frustration": Score(instructions=q["frustration"]["instructions"], criteria=q["frustration"]["criteria"]),
    }


def main() -> None:
    url = harness.decisio_url()
    version = importlib.metadata.version("langchain-typesafe")
    res = harness.Results("langchain", {"langchain-typesafe": version}, url)
    res.check("pinned version installed", version == PINNED, version)
    state = harness.CASES["state"]
    questions = build_questions()

    with harness.Proxy(url) as proxy:
        harness.assert_local(proxy.url)
        clf = TypeSafeClassifier(base_url=proxy.url, api_key=harness.DUMMY_KEY)

        # (e) defaults from the class, and the client the class built
        res.observe("default_timeout_s", clf.timeout)
        res.observe("client_timeout", str(clf.client.timeout))
        res.observe("default_model", clf.model)
        res.check("default timeout is 30 s", clf.timeout == 30.0, f"timeout={clf.timeout}")

        # (a, b, c) each type alone, through the base_url argument
        for qid, kind in (("urgent", "noul"), ("department", "choice"), ("frustration", "score")):
            proxy.reset()
            out = clf.invoke({"state": state, "questions": {qid: questions[qid]}})
            rec = proxy.last()
            res.add_request(f"{kind} alone (base_url argument)", rec)
            raw = harness.raw_answers(rec)[qid]
            sent = harness.json_body(rec)
            res.check(
                f"{kind}: POST /v1/systemone hit",
                rec["method"] == "POST" and rec["path"] == "/v1/systemone",
                rec["path"],
            )
            res.check(f"{kind}: status 200", rec["upstream_status"] == 200)
            parsed = out.answers[qid]
            if kind == "noul":
                res.check("noul: parsed type", isinstance(parsed, NoulAnswer))
                res.check("noul: probability identical to raw", parsed.noul == raw["noul"], f"{parsed.noul}")
            elif kind == "choice":
                res.check("choice: parsed type", isinstance(parsed, ChoiceAnswer))
                res.check("choice: label identical to raw", parsed.choice == raw["choice"], parsed.choice)
                res.check("choice: probabilities identical to raw", parsed.probabilities == raw["probabilities"])
                res.check("choice: confidence identical to raw", parsed.confidence == raw["confidence"])
            else:
                res.check("score: parsed type", isinstance(parsed, ScoreAnswer))
                res.check("score: value identical to raw", parsed.score == raw["score"], f"{parsed.score}")
                res.check(
                    "score: probabilities identical to raw (int keys vs string keys)",
                    {str(k): v for k, v in parsed.probabilities.items()} == raw["probabilities"],
                )
                res.check(
                    "score: legend identical to raw",
                    {str(k): v for k, v in parsed.legend.items()} == raw["legend"],
                )
                res.check("score: confidence identical to raw", parsed.confidence == raw["confidence"])
            res.check(f"{kind}: model echoed", out.model == sent["model"], out.model)
            res.check(
                f"{kind}: usage parsed", out.usage.input_tokens is not None and out.usage.output_tokens is not None
            )
            if kind == "noul":
                res.observe("request_body_fields", sorted(sent))
                res.observe("model_sent", sent.get("model"))
                res.observe("request_headers_sent", {k: v for k, v in rec["headers"].items() if k != "host"})
                res.observe("auth_header", "Authorization: Bearer <key> (also User-Agent langchain-typesafe/<version>)")
                res.observe("noul_criteria_sent", sent["questions"][qid].get("criteria"))

        # all three in one request
        proxy.reset()
        out = clf.invoke({"state": state, "questions": questions})
        rec = proxy.last()
        res.add_request("noul + choice + score in one request", rec)
        raw = harness.raw_answers(rec)
        res.check("combined: status 200 and three answers", rec["upstream_status"] == 200 and len(out.answers) == 3)
        res.check(
            "combined: all three identical to raw",
            out.nouls["urgent"].noul == raw["urgent"]["noul"]
            and out.choices["department"].probabilities == raw["department"]["probabilities"]
            and out.scores["frustration"].score == raw["frustration"]["score"],
        )

        # async path uses its own client
        proxy.reset()
        aout = asyncio.run(clf.ainvoke({"state": state, "questions": {"urgent": questions["urgent"]}}))
        rec = proxy.last()
        res.check(
            "ainvoke: same path, identical probability",
            rec["path"] == "/v1/systemone" and aout.nouls["urgent"].noul == harness.raw_answers(rec)["urgent"]["noul"],
        )

        # LangChain messages as state
        proxy.reset()
        msgs = [HumanMessage(content="Stripe has failed to connect for three days."), AIMessage(content="Looking.")]
        out = clf.invoke({"state": msgs, "questions": {"urgent": questions["urgent"]}})
        rec = proxy.last()
        res.add_request("LangChain messages as state", rec)
        sent_state = harness.json_body(rec)["state"]
        res.check(
            "messages: sent as role/content list and accepted",
            rec["upstream_status"] == 200 and isinstance(sent_state, list),
        )
        res.observe("messages_state_sent", sent_state)

        # base_url from the environment, no argument
        os.environ["TYPESAFE_BASE_URL"] = proxy.url
        env_clf = TypeSafeClassifier()
        proxy.reset()
        env_clf.invoke({"state": state, "questions": {"urgent": questions["urgent"]}})
        res.check(
            "env TYPESAFE_BASE_URL is honoured",
            proxy.last()["path"] == "/v1/systemone" and env_clf.base_url == proxy.url,
        )
        del os.environ["TYPESAFE_BASE_URL"]
        trailing = TypeSafeClassifier(base_url=proxy.url + "/", api_key=harness.DUMMY_KEY)
        proxy.reset()
        trailing.invoke({"state": state, "questions": {"urgent": questions["urgent"]}})
        res.check(
            "trailing slash on base_url is stripped", proxy.last()["path"] == "/v1/systemone", proxy.last()["path"]
        )

        # a key is required even though Decisio ignores keys
        saved_key = os.environ.pop("TYPESAFE_API_KEY")
        try:
            TypeSafeClassifier(base_url=proxy.url)
            no_key = "accepted"
        except ValueError as e:
            no_key = f"ValueError: {e}"
        os.environ["TYPESAFE_API_KEY"] = saved_key
        res.observe("no_api_key", no_key)
        res.check("no API key: ValueError at construction, before any request", no_key.startswith("ValueError"), no_key)
        res.finding(
            "The classifier refuses to be built without an API key (api_key or TYPESAFE_API_KEY) even though Decisio "
            "ignores keys: a self-hosted setup still has to pass a dummy key."
        )

        # (d) errors
        blocked = {}
        for label, make in (
            ("choice with empty criteria", lambda: Choice(instructions="x", criteria={})),
            ("score with one level", lambda: Score(instructions="x", criteria=["only"])),
        ):
            try:
                make()
                blocked[label] = "accepted"
            except ValueError as e:
                blocked[label] = f"rejected before any request: {type(e).__name__}"
        res.observe("client_side_validation", blocked)
        res.finding(
            "The classes validate before sending: a Choice with no criteria and a Score with one level raise "
            "a pydantic "
            "ValidationError in the client and never reach the server, so the 422 check below uses a request the "
            "classes do not validate (an empty questions mapping, and a Choice built with model_construct)."
        )

        proxy.reset()
        err = None
        try:
            clf.invoke({"state": state, "questions": {}})
        except Exception as e:  # noqa: BLE001 - the type is the check
            err = e
        rec = proxy.last()
        res.add_request("empty questions (server 422)", rec)
        res.check("422 (empty questions): raised", err is not None)
        res.check(
            "422: typed TypeSafeUnprocessableEntityError",
            isinstance(err, TypeSafeUnprocessableEntityError),
            type(err).__name__,
        )
        res.check("422: status attribute", getattr(err, "status", None) == 422)
        detail = getattr(err, "body", None)
        res.check("422: Decisio's detail is on .body", isinstance(detail, dict) and "detail" in detail)
        res.observe("422_str", str(err))
        res.check("422: str() does not carry the server's detail", "Dictionary should have" not in str(err), str(err))

        proxy.reset()
        bad = Choice.model_construct(type="choice", instructions="Which team?")
        err = None
        try:
            clf.invoke({"state": state, "questions": {"department": bad}})
        except Exception as e:  # noqa: BLE001
            err = e
        rec = proxy.last()
        res.add_request("choice without criteria via model_construct (server 422)", rec)
        res.check(
            "422 (choice without criteria): raised as TypeSafeAPIError",
            isinstance(err, TypeSafeAPIError) and getattr(err, "status", None) == 422,
            type(err).__name__,
        )
        res.observe("choice_without_criteria_sent", harness.json_body(rec)["questions"])

        # (f) fields the integration drops
        proxy.reset()
        out = clf.invoke(
            {
                "state": state,
                "questions": {"department": questions["department"], "frustration": questions["frustration"]},
            }
        )
        raw = harness.raw_answers(proxy.last())
        raw_fields = sorted({f for a in raw.values() for f in a})
        res.observe("raw_answer_fields", raw_fields)
        for mode in ("answered", "abstained"):
            proxy.reset()
            proxy.emulate_abstention(mode)
            out = clf.invoke({"state": state, "questions": {"department": questions["department"]}})
            rec = proxy.last()
            res.add_request(f"choice with emulated abstention fields ({mode})", rec)
            ans = out.choices["department"]
            kept = set(type(ans).model_fields)
            dropped = [f for f in ("unknown_probability", "abstained") if f not in kept]
            res.check(f"emulated {mode}: request still parses", ans.choice in questions["department"].criteria)
            res.check(
                f"emulated {mode}: unknown_probability and abstained are dropped",
                dropped == ["unknown_probability", "abstained"] and not hasattr(ans, "abstained"),
            )
        proxy.emulate_abstention(None)
        res.observe(
            "answer_fields_parsed",
            {
                "noul": sorted(NoulAnswer.model_fields),
                "choice": sorted(ChoiceAnswer.model_fields),
                "score": sorted(ScoreAnswer.model_fields),
            },
        )
        res.observe("usage_parsed", out.usage.model_dump())
        res.observe("request_id", out.request_id)
        res.finding(
            "Decisio's `unknown_probability` and `abstained` (documented for --abstain-option) are silently dropped by "
            "the answer models: a caller using this package cannot tell that the server abstained. They are emulated "
            "here (the stand-in has no abstain option): the proxy adds them to a real answer."
        )
        res.finding(
            "x-decisio-* response headers (server time, tasks, stages) are not surfaced; request_id is None because "
            "the package reads x-typesafe-request-id, which Decisio does not send."
        )
        res.observe("model_note", "Decisio echoes the request's `model` (jev-latest by default) as the response model.")

    res.finish(HERE / "results.json")


if __name__ == "__main__":
    main()
