// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
// Verify TanStack AI's TypeSafe adapter (@tanstack/ai-typesafe) against a Decisio server (needs DECISIO_URL).
//
// Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
// Everything goes through a local logging proxy in front of the server; TypeSafe's hosted service is never called.

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as H from "../_shared/harness.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PINNED = { "@tanstack/ai": "0.65.1", "@tanstack/ai-typesafe": "0.1.8" };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function installedVersion(name) {
  return JSON.parse(readFileSync(path.join(HERE, "node_modules", name, "package.json"), "utf8")).version;
}

const url = H.decisioUrl();
const versions = Object.fromEntries(Object.keys(PINNED).map((n) => [n, installedVersion(n)]));
const res = await new H.Results("tanstack", versions, url).init();
for (const [name, v] of Object.entries(PINNED)) res.check(`pinned ${name}`, versions[name] === v, versions[name]);

const { boolean, choice, decide, score } = await import("@tanstack/ai");
const { createTypesafeDecider, typesafeDecider, TYPESAFE_EVALUATE_MODELS } = await import("@tanstack/ai-typesafe");

const q = H.CASES.questions;
const questions = {
  urgent: boolean({ instructions: q.urgent.instructions, criteria: q.urgent.criteria }),
  department: choice({ instructions: q.department.instructions, options: q.department.criteria }),
  frustration: score({ instructions: q.frustration.instructions, levels: q.frustration.criteria }),
};
const state = H.CASES.state;

const proxy = await H.Proxy.start(url);
let code = 1;
try {
  H.assertLocal(proxy.url);
  const adapter = createTypesafeDecider("jev-latest", H.DUMMY_KEY, { baseURL: proxy.url });

  // (e) defaults, from source
  res.observe("default_baseURL", "https://api.typesafe.ai (TYPESAFE_DEFAULT_BASE_URL; the adapter appends /v1/systemone)");
  res.observe("timeout", "none: plain fetch, only the abortSignal option; no retries. Node's fetch applies undici's defaults, 300 s to response headers.");
  res.observe("known_models", TYPESAFE_EVALUATE_MODELS);

  // (a, b, c) each type alone
  for (const [qid, kind] of [["urgent", "noul"], ["department", "choice"], ["frustration", "score"]]) {
    await proxy.reset();
    const result = await decide({ debug: false, adapter, state, questions: { [qid]: questions[qid] } });
    const rec = await proxy.last();
    res.addRequest(`${kind} alone`, rec);
    const rawAll = JSON.parse(rec.upstream_body);
    const raw = rawAll.answers[qid];
    const sent = H.jsonBody(rec);
    const got = result[qid];
    res.check(`${kind}: POST /v1/systemone hit`, rec.method === "POST" && rec.path === "/v1/systemone", rec.path);
    res.check(`${kind}: status 200`, rec.upstream_status === 200);
    if (kind === "noul") {
      res.check("noul: boolean question sent as type noul with criteria", sent.questions[qid].type === "noul" && same(sent.questions[qid].criteria, q.urgent.criteria));
      res.check("noul: probability identical to raw noul, value is noul >= 0.5", got.type === "boolean" && got.probability === raw.noul && got.value === raw.noul >= 0.5, `${got.probability} ${got.value}`);
    } else if (kind === "choice") {
      res.check("choice: options sent as criteria", same(sent.questions[qid].criteria, q.department.criteria));
      res.check("choice: value is the raw label", got.value === raw.choice, got.value);
      res.check("choice: probability is the raw probability of that label", got.probability === raw.probabilities[raw.choice]);
      res.check("choice: probabilities and confidence identical to raw", same(got.probabilities, raw.probabilities) && got.confidence === raw.confidence);
    } else {
      res.check("score: levels sent as criteria", same(sent.questions[qid].criteria, q.frustration.criteria));
      const idx = Math.min(Math.max(Math.round(raw.score), 0), q.frustration.criteria.length - 1);
      res.check("score: score identical to raw; value is the nearest level label", got.score === raw.score && got.value === q.frustration.criteria[idx], `${got.score} -> ${got.value}`);
      res.check("score: probabilities, legend and confidence identical to raw", same(got.probabilities, raw.probabilities) && same(got.legend, raw.legend) && got.confidence === raw.confidence);
      res.check("score: probability is that of the nearest level", got.probability === raw.probabilities[String(idx)]);
    }
    res.check(`${kind}: meta.model is the server's model and usage is mapped`, result.meta.model === rawAll.model && result.meta.usage.promptTokens === rawAll.usage.input_tokens && result.meta.usage.completionTokens === rawAll.usage.output_tokens && result.meta.usage.totalTokens === rawAll.usage.input_tokens + rawAll.usage.output_tokens);
    if (kind === "noul") {
      res.observe("request_body_fields", Object.keys(sent).sort());
      res.observe("model_sent", sent.model);
      res.observe("request_headers_sent", Object.fromEntries(Object.entries(rec.headers).filter(([k]) => k !== "host")));
      res.observe("auth_header", "Authorization: Bearer <key>; Content-Type: application/json; no User-Agent of its own (Node fetch default)");
      res.check("body fields are model, state, questions", same(Object.keys(sent).sort(), ["model", "questions", "state"]));
      res.check("model sent is the adapter's model", sent.model === "jev-latest");
      res.check("Authorization is Bearer with the key", /^Bearer </.test(rec.headers.authorization ?? ""), rec.headers.authorization);
    }
  }

  // all three in one request, object state
  await proxy.reset();
  const all = await decide({ debug: false, adapter, state: { customer_message: state }, questions });
  let rec = await proxy.last();
  res.addRequest("noul + choice + score in one request, state as an object", rec);
  const rawA = JSON.parse(rec.upstream_body).answers;
  res.check("combined: status 200, object state accepted", rec.upstream_status === 200 && typeof H.jsonBody(rec).state === "object");
  res.check("combined: all three identical to raw", all.urgent.probability === rawA.urgent.noul && same(all.department.probabilities, rawA.department.probabilities) && all.frustration.score === rawA.frustration.score);

  // configuration routes
  await proxy.reset();
  process.env.TYPESAFE_API_KEY = H.DUMMY_KEY;
  const viaEnv = typesafeDecider("jev-latest", { baseURL: `${proxy.url}/` });
  delete process.env.TYPESAFE_API_KEY;
  await decide({ debug: false, adapter: viaEnv, state, questions: { urgent: questions.urgent } });
  res.check("typesafeDecider reads TYPESAFE_API_KEY; a trailing slash on baseURL is stripped", (await proxy.last()).path === "/v1/systemone" && /^Bearer </.test((await proxy.last()).headers.authorization));
  await proxy.reset();
  const alias = createTypesafeDecider("jev-latest", H.DUMMY_KEY, { baseUrl: proxy.url, headers: { "x-example": "1" } });
  await decide({ debug: false, adapter: alias, state, questions: { urgent: questions.urgent } });
  res.check("baseUrl alias and extra headers are honoured", (await proxy.last()).path === "/v1/systemone" && (await proxy.last()).headers["x-example"] === "1");
  let err;
  try {
    delete process.env.TYPESAFE_API_KEY;
    typesafeDecider("jev-latest", { baseURL: proxy.url });
  } catch (e) {
    err = e;
  }
  res.check("no TYPESAFE_API_KEY: typesafeDecider throws before any request", Boolean(err), String(err?.message).slice(0, 100));
  res.finding("typesafeDecider() requires TYPESAFE_API_KEY even for a server that ignores keys; createTypesafeDecider(model, 'any-string', { baseURL }) takes the key directly.");

  await proxy.reset();
  const withV1 = createTypesafeDecider("jev-latest", H.DUMMY_KEY, { baseURL: `${proxy.url}/v1` });
  err = undefined;
  try {
    await decide({ debug: false, adapter: withV1, state, questions: { urgent: questions.urgent } });
  } catch (e) {
    err = e;
  }
  rec = await proxy.last();
  res.addRequest("baseURL with /v1 (server 404)", rec);
  res.check("baseURL ending in /v1 posts to /v1/v1/systemone and fails with an error naming the 404", rec.path === "/v1/v1/systemone" && /404/.test(err?.message ?? ""), `${rec.path} ${err?.message}`.slice(0, 120));
  res.finding("baseURL must NOT include /v1: the adapter appends /v1/systemone itself (the opposite of @ai-sdk/typesafe-ai). A base URL ending in /v1 posts to /v1/v1/systemone and fails with a 404 error.");

  // (d) errors
  await proxy.reset();
  err = undefined;
  try {
    await decide({ debug: false, adapter, state, questions: { department: choice({ instructions: "Which team?" }) } });
  } catch (e) {
    err = e;
  }
  rec = await proxy.last();
  res.addRequest("choice without options (server 422)", rec);
  res.check("choice without options: sent without criteria and the server answered 422", rec.upstream_status === 422 && !("criteria" in H.jsonBody(rec).questions.department));
  res.check("422 surfaces as a thrown Error naming the status", err instanceof Error && /422/.test(err.message), (err?.message ?? "").slice(0, 100));
  res.check("422: Decisio's detail is in the error message", /criteria/.test(err?.message ?? ""));
  res.check("422: not retried (one request)", (await proxy.records()).length === 1);
  res.observe("422_message", err?.message);
  err = undefined;
  try {
    score({ instructions: "x", levels: ["only"] });
  } catch (e) {
    err = e;
  }
  res.observe("client_side_validation", { score_with_one_level: String(err?.message), empty_questions: "decide() requires at least one question", reserved_key: 'decide() reserves the question key "meta"' });
  res.check("score with one level is refused in the client", /at least two levels/.test(err?.message ?? ""));
  err = undefined;
  await proxy.reset();
  try {
    await decide({ debug: false, adapter, state, questions: {} });
  } catch (e) {
    err = e;
  }
  res.check("empty questions refused in the client, no request", /at least one question/.test(err?.message ?? "") && (await proxy.records()).length === 0);
  res.finding("choice() does not check that options is present or non-empty: a choice with no options is sent and Decisio's 422 comes back as a thrown Error whose message carries the response body.");

  // (f) fields dropped, emulated
  for (const mode of ["answered", "abstained", "abstained_not_argmax"]) {
    await proxy.reset();
    await proxy.emulate(mode);
    err = undefined;
    let result;
    try {
      result = await decide({ debug: false, adapter, state, questions: { department: questions.department, frustration: questions.frustration } });
    } catch (e) {
      err = e;
    }
    rec = await proxy.last();
    res.addRequest(`emulated abstention fields (${mode})`, rec);
    const text = JSON.stringify(result ?? {});
    res.check(`emulated ${mode}: parses and does not surface abstained or unknown_probability`, !err && !/abstained|unknown_probability/.test(text), err?.message ?? Object.keys(result?.department ?? {}).join());
  }
  await proxy.emulate(null);
  res.finding("EMULATED (the stand-in has no abstain option; the proxy adds the documented fields to a real answer): `abstained` and `unknown_probability` are dropped, so a caller cannot tell that the server abstained. When the choice is not the most probable key (documented abstention behaviour) the adapter still reports it as `value` with that key's own probability.");
  res.finding("Decisio's x-decisio-* response headers are not surfaced; `legend` is passed through on score answers; `confidence` is passed through on choice and score answers; `usage` is mapped to promptTokens, completionTokens, totalTokens.");
} finally {
  proxy.stop();
}
code = res.finish(path.join(HERE, "results.json"));
process.exit(code);
