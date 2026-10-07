// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
// Verify the Vercel AI SDK's TypeSafe provider (@ai-sdk/typesafe-ai) against a Decisio server (needs DECISIO_URL).
//
// Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
// Everything goes through a local logging proxy in front of the server; TypeSafe's hosted service is never called.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as H from "../_shared/harness.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const PINNED = { ai: "7.0.131", "@ai-sdk/typesafe-ai": "3.0.15" };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function installedVersion(name) {
  const dir = path.dirname(require.resolve(`${name}/package.json`));
  return JSON.parse(readFileSync(path.join(dir, "package.json"), "utf8")).version;
}

const url = H.decisioUrl();
const versions = { ai: installedVersion("ai"), "@ai-sdk/typesafe-ai": installedVersion("@ai-sdk/typesafe-ai") };
const res = await new H.Results("ai-sdk", versions, url).init();
for (const [name, v] of Object.entries(PINNED)) res.check(`pinned ${name}`, versions[name] === v, versions[name]);

const proxy = await H.Proxy.start(url);
let code = 1;
try {
  H.assertLocal(proxy.url);
  // The default instance reads TYPESAFE_AI_BASE_URL when the module loads, so set it before the import.
  process.env.TYPESAFE_AI_BASE_URL = `${proxy.url}/v1`;
  const { createTypeSafeAi, typeSafeAi } = await import("@ai-sdk/typesafe-ai");
  const ai = await import("ai");
  delete process.env.TYPESAFE_AI_BASE_URL;

  // Which name this version exports
  res.observe("exports", {
    experimental_decide: typeof ai.experimental_decide,
    experimental_evaluate: typeof ai.experimental_evaluate,
    evaluate_is_alias_of_decide: ai.experimental_evaluate === ai.experimental_decide,
  });
  res.check("ai exports experimental_decide", typeof ai.experimental_decide === "function");
  res.check("experimental_evaluate is only a deprecated alias of experimental_decide", ai.experimental_evaluate === ai.experimental_decide);

  const sdk = createTypeSafeAi({ baseURL: `${proxy.url}/v1`, apiKey: H.DUMMY_KEY });
  const model = sdk.decisionModel("jev-latest");
  const q = H.CASES.questions;
  const questions = {
    urgent: { type: "boolean", instructions: q.urgent.instructions, criteria: q.urgent.criteria },
    department: { type: "choice", instructions: q.department.instructions, criteria: q.department.criteria },
    frustration: { type: "score", instructions: q.frustration.instructions, criteria: q.frustration.criteria },
  };
  const state = H.CASES.state;

  // (e) defaults, read from the provider without sending anything
  const defaultCfg = createTypeSafeAi({ apiKey: H.DUMMY_KEY }).decisionModel("jev-latest").config;
  res.observe("default_baseURL", defaultCfg.baseURL);
  res.check("default baseURL is the hosted /v1 (read from config, never called)", defaultCfg.baseURL === "https://api.typesafe.ai/v1", defaultCfg.baseURL);
  res.observe("timeout", "none set by the provider or by experimental_decide (only abortSignal); Node's fetch applies undici's defaults, 300 s to response headers and 300 s between body chunks. maxRetries defaults to 2.");

  // (a, b, c) each type alone
  for (const [qid, kind] of [["urgent", "noul"], ["department", "choice"], ["frustration", "score"]]) {
    await proxy.reset();
    const result = await ai.experimental_decide({ model, state, questions: { [qid]: questions[qid] } });
    const rec = await proxy.last();
    res.addRequest(`${kind} alone`, rec);
    const raw = H.rawAnswers(rec)[qid];
    const rawAll = JSON.parse(rec.upstream_body);
    const sent = H.jsonBody(rec);
    const got = result.answers[qid];
    res.check(`${kind}: POST /v1/systemone hit`, rec.method === "POST" && rec.path === "/v1/systemone", rec.path);
    res.check(`${kind}: status 200`, rec.upstream_status === 200);
    if (kind === "noul") {
      res.check("noul: boolean question sent as type noul", sent.questions[qid].type === "noul");
      res.check("noul: result type boolean, probability identical to raw noul", got.type === "boolean" && got.probability === raw.noul, got.probability);
    } else if (kind === "choice") {
      res.check("choice: label identical to raw", got.choice === raw.choice, got.choice);
      res.check("choice: probabilities identical to raw", same(got.probabilities, raw.probabilities));
      res.check("choice: confidence moved to providerMetadata.typesafe.confidence", result.providerMetadata.typesafe.confidence[qid] === raw.confidence);
    } else {
      res.check("score: value identical to raw", got.score === raw.score, got.score);
      res.check("score: probabilities identical to raw", same(got.probabilities, raw.probabilities));
      res.check("score: confidence moved to providerMetadata.typesafe.confidence", result.providerMetadata.typesafe.confidence[qid] === raw.confidence);
      res.check("score: legend is not in the result", !("legend" in got) && Object.keys(got).sort().join() === "probabilities,score,type", Object.keys(got).join());
    }
    res.check(`${kind}: response modelId is the server's echoed model`, result.response.modelId === rawAll.model, result.response.modelId);
    res.check(`${kind}: usage mapped`, result.usage.inputTokens === rawAll.usage.input_tokens && result.usage.outputTokens === rawAll.usage.output_tokens);
    if (kind === "noul") {
      res.observe("request_body_fields", Object.keys(sent).sort());
      res.observe("model_sent", sent.model);
      res.observe("request_headers_sent", Object.fromEntries(Object.entries(rec.headers).filter(([k]) => k !== "host")));
      res.observe("auth_header", "Authorization: Bearer <key>; User-Agent ai/<version> ai-sdk-provider-utils/<version> node.js/<major> (decide() overrides the provider's own ai-sdk-typesafe-ai suffix)");
      res.observe("rounding_declared", result.rounding);
      res.observe("response_headers_exposed", Object.keys(result.response.headers ?? {}).sort());
      res.check("response headers (x-decisio-*) are exposed on result.response.headers", Object.keys(result.response.headers ?? {}).some((k) => k.startsWith("x-decisio-")));
    }
  }

  // all three in one request, and an object state
  await proxy.reset();
  const combined = await ai.experimental_decide({ model, state: { customer_message: state }, questions });
  let rec = await proxy.last();
  res.addRequest("noul + choice + score in one request, state as an object", rec);
  const raw = H.rawAnswers(rec);
  res.check("combined: status 200, object state accepted", rec.upstream_status === 200 && typeof H.jsonBody(rec).state === "object");
  res.check(
    "combined: all three identical to raw",
    combined.answers.urgent.probability === raw.urgent.noul &&
      same(combined.answers.department.probabilities, raw.department.probabilities) &&
      combined.answers.frustration.score === raw.frustration.score,
  );

  // baseURL handling
  await proxy.reset();
  const slash = createTypeSafeAi({ baseURL: `${proxy.url}/v1/`, apiKey: H.DUMMY_KEY });
  await ai.experimental_decide({ model: slash.decisionModel("jev-latest"), state, questions: { urgent: questions.urgent } });
  res.check("trailing slash on baseURL is stripped", (await proxy.last()).path === "/v1/systemone", (await proxy.last()).path);

  await proxy.reset();
  const noV1 = createTypeSafeAi({ baseURL: proxy.url, apiKey: H.DUMMY_KEY });
  let err;
  try {
    await ai.experimental_decide({ model: noV1.decisionModel("jev-latest"), state, questions: { urgent: questions.urgent } });
  } catch (e) {
    err = e;
  }
  rec = await proxy.last();
  res.addRequest("baseURL without /v1 (server 404)", rec);
  res.check("baseURL without /v1 posts to /systemone and fails with a 404 error, not silently", rec.path === "/systemone" && err?.statusCode === 404, `${rec.path} ${err?.name} ${err?.statusCode}`);
  res.finding("baseURL must include /v1 (http://host:port/v1): the provider appends only /systemone, so a base URL written the way other integrations take it (no /v1) hits /systemone, which Decisio does not serve, and fails with a 404 APICallError.");

  // the key is read at call time, the base URL when the provider is created
  await proxy.reset();
  err = undefined;
  try {
    await ai.experimental_decide({ model: typeSafeAi.decisionModel("jev-latest"), state, questions: { urgent: questions.urgent } });
  } catch (e) {
    err = e;
  }
  res.check("no API key: LoadAPIKeyError before any request", err?.name === "AI_LoadAPIKeyError" && (await proxy.records()).length === 0, err?.name);
  res.finding("The provider refuses to send without an API key (TYPESAFE_AI_API_KEY or the apiKey option) even though Decisio ignores keys: a self-hosted setup still has to pass a dummy key.");
  process.env.TYPESAFE_AI_API_KEY = H.DUMMY_KEY;
  await proxy.reset();
  await ai.experimental_decide({ model: typeSafeAi.decisionModel("jev-latest"), state, questions: { urgent: questions.urgent } });
  delete process.env.TYPESAFE_AI_API_KEY;
  rec = await proxy.last();
  res.check("env TYPESAFE_AI_BASE_URL / TYPESAFE_AI_API_KEY are honoured by the default instance", rec.path === "/v1/systemone" && /^Bearer </.test(rec.headers.authorization ?? ""), rec.headers.authorization);

  // (d) errors
  await proxy.reset();
  err = undefined;
  try {
    await ai.experimental_decide({ model, state, questions: { department: { type: "choice", instructions: "Which team?" } } });
  } catch (e) {
    err = e;
  }
  res.check("choice without criteria: rejected by experimental_decide before any request", err?.name === "AI_InvalidArgumentError" && (await proxy.records()).length === 0, `${err?.name}: ${err?.message}`);
  res.observe("client_side_validation", { choice_without_criteria: `${err?.name}: ${err?.message}` });

  await proxy.reset();
  err = undefined;
  try {
    await model.doDecide({ state, questions: { department: { type: "choice", instructions: "Which team?" } } });
  } catch (e) {
    err = e;
  }
  res.check("choice without criteria through doDecide: a TypeError, no request sent", err instanceof TypeError && (await proxy.records()).length === 0, `${err?.name}: ${err?.message}`);
  res.finding("Calling the model's doDecide directly with a choice question that has no criteria throws a bare TypeError (Object.keys of undefined) in the provider, not an InvalidArgumentError; experimental_decide validates first and gives a proper InvalidArgumentError, so only direct doDecide callers see it.");

  await proxy.reset();
  err = undefined;
  try {
    await model.doDecide({ state, questions: { department: { type: "choice", instructions: "Which team?", criteria: {} } } });
  } catch (e) {
    err = e;
  }
  rec = await proxy.last();
  res.addRequest("choice with empty criteria through doDecide (server 422)", rec);
  res.check("422 surfaces as APICallError with statusCode 422", ai.APICallError.isInstance(err) && err.statusCode === 422, `${err?.name} ${err?.statusCode}`);
  res.check("422: Decisio's detail is in the error message", /at least 1 item/.test(err?.message ?? ""), (err?.message ?? "").slice(0, 120));
  res.check("422: not retried (one request seen)", (await proxy.records()).length === 1);
  res.check("422: not retryable", err?.isRetryable === false);
  res.observe("422_message", err?.message);

  // (f) fields dropped, and an answer the SDK refuses
  for (const mode of ["answered", "abstained"]) {
    await proxy.reset();
    await proxy.emulate(mode);
    const result = await ai.experimental_decide({ model, state, questions: { department: questions.department } });
    rec = await proxy.last();
    res.addRequest(`choice with emulated abstention fields (${mode})`, rec);
    const a = result.answers.department;
    res.check(`emulated ${mode}: parses, abstained and unknown_probability not surfaced`, !("abstained" in a) && !("unknown_probability" in a) && JSON.stringify(result.response.body).includes("abstained"), Object.keys(a).join());
  }
  await proxy.reset();
  await proxy.emulate("abstained_not_argmax");
  err = undefined;
  try {
    await ai.experimental_decide({ model, state, questions: { department: questions.department } });
  } catch (e) {
    err = e;
  }
  rec = await proxy.last();
  res.addRequest("choice with emulated abstention, answer is not the most probable key", rec);
  res.check("emulated abstention with a non-argmax choice is refused by the SDK's answer validation", err?.name === "AI_InvalidResponseDataError", `${err?.name}: ${err?.message}`);
  res.observe("abstention_not_argmax_error", `${err?.name}: ${err?.message}`);
  res.finding("EMULATED, not seen on the stand-in: docs/api.md says a server with --abstain-option answers the best of the other options while reporting the probabilities unchanged, so `choice` need not be the most probable key. experimental_decide checks that the selected option has the highest probability and throws InvalidResponseDataError when it does not. A real abstaining Decisio server would therefore make experimental_decide throw on exactly the answers where it abstains. The proxy rewrote a real answer to show the error; no abstaining server was run.");
  await proxy.emulate(null);

  res.finding("`legend` is dropped from score answers and `confidence` is moved out of the answer into result.providerMetadata.typesafe.confidence; `unknown_probability` and `abstained` are not surfaced on the answer (they remain in result.response.body). `usage` maps to inputTokens, outputTokens and totalTokens.");
  res.finding("Decisio's x-decisio-* response headers are exposed on result.response.headers.");
} finally {
  proxy.stop();
}
code = res.finish(path.join(HERE, "results.json"));
process.exit(code);
