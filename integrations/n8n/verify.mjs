// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
// Verify the n8n community node n8n-nodes-jev against a Decisio server (needs DECISIO_URL).
//
// Decisio is an independent project, not affiliated with or endorsed by TypeSafe or by the node's maintainer.
// The node is run inside a real n8n (the `n8n execute` command, no web server, no port), through a local logging proxy
// in front of the server; TypeSafe's hosted service is never called.
// Two parts run in a hand-written context instead, and the README says so: the model list and the credential test.

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as H from "../_shared/harness.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const PINNED = { n8n: "2.35.7", "n8n-nodes-jev": "0.2.3", "n8n-workflow": "2.35.3" };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function installedVersion(name) {
  const dir = path.dirname(require.resolve(`${name}/package.json`));
  return JSON.parse(readFileSync(path.join(dir, "package.json"), "utf8")).version;
}

const url = H.decisioUrl();
const versions = Object.fromEntries(Object.keys(PINNED).map((n) => [n, installedVersion(n)]));
const res = await new H.Results("n8n", versions, url).init();
for (const [name, v] of Object.entries(PINNED)) res.check(`pinned ${name}`, versions[name] === v, versions[name]);

const q = H.CASES.questions;
const MODEL = { __rl: true, mode: "id", value: "jev-latest" };
const CRED = { jevApi: { id: "cred1", name: "Decisio" } };
const TYPE = "n8n-nodes-jev.jev";
let nodeNo = 1;
const node = (name, parameters, extra = {}) => ({
  parameters,
  id: `n${nodeNo++}`,
  name,
  type: TYPE,
  typeVersion: 1,
  position: [300, 120 * nodeNo],
  credentials: CRED,
  ...extra,
});
const base = { operation: "ask", model: MODEL, stateSource: "text", stateText: H.CASES.state };
const fieldQ = {
  noul: { type: "noul", id: "urgent", instructions: q.urgent.instructions, trueCriterion: q.urgent.criteria.true, falseCriterion: q.urgent.criteria.false },
  choice: {
    type: "choice",
    id: "department",
    instructions: q.department.instructions,
    choiceOptions: Object.entries(q.department.criteria).map(([k, v]) => `${k}: ${v}`).join("\n"),
  },
  score: { type: "score", id: "frustration", instructions: q.frustration.instructions, scoreLevels: q.frustration.criteria.join("\n") },
};
const routes = Object.entries(q.department.criteria).map(([name, description]) => ({ name, description }));

const nodes = [
  node("A noul fields", { ...base, questionMode: "fields", questions: { question: [fieldQ.noul] }, options: { simplify: false } }),
  node("B choice fields", { ...base, questionMode: "fields", questions: { question: [fieldQ.choice] }, options: { simplify: false } }),
  node("C score fields", { ...base, questionMode: "fields", questions: { question: [fieldQ.score] }, options: { simplify: false } }),
  node("D all three simplified", { ...base, questionMode: "fields", questions: { question: [fieldQ.noul, fieldQ.choice, fieldQ.score] } }),
  node("E all three JSON, object state, full output", {
    ...base,
    stateSource: "json",
    stateJson: JSON.stringify({ customer_message: H.CASES.state }),
    questionMode: "json",
    questionsJson: JSON.stringify(q),
    options: { simplify: false },
  }),
  node("F route", {
    ...base,
    operation: "route",
    routeInstructions: q.department.instructions,
    routes: { values: routes },
    lowConfidence: "extraOutput",
    confidenceThreshold: 0.5,
  }),
  node(
    "G choice without criteria, continue on error",
    { ...base, questionMode: "json", questionsJson: JSON.stringify(H.CASES.malformed.choice_without_criteria.questions) },
    { onError: "continueRegularOutput" },
  ),
];
const workflow = (id, name, list) => [
  {
    id,
    name,
    active: false,
    settings: {},
    nodes: [{ parameters: {}, id: "n0", name: "Manual", type: "n8n-nodes-base.manualTrigger", typeVersion: 1, position: [0, 0] }, ...list],
    connections: { Manual: { main: [list.map((n) => ({ node: n.name, type: "main", index: 0 }))] } },
  },
];
const stopNode = node("H choice without criteria, stop on error", {
  ...base,
  questionMode: "json",
  questionsJson: JSON.stringify(H.CASES.malformed.choice_without_criteria.questions),
});
const oneOption = node("I choice with one option", {
  ...base,
  questionMode: "fields",
  questions: { question: [{ ...fieldQ.choice, choiceOptions: "billing: Payment issues" }] },
});

const proxy = await H.Proxy.start(url);
const home = mkdtempSync(path.join(os.tmpdir(), "decisio-n8n-"));
let code = 1;
try {
  H.assertLocal(proxy.url);
  const nodesDir = path.join(home, ".n8n", "nodes");
  mkdirSync(nodesDir, { recursive: true });
  writeFileSync(
    path.join(nodesDir, "package.json"),
    JSON.stringify({ name: "installed-nodes", private: true, dependencies: { "n8n-nodes-jev": PINNED["n8n-nodes-jev"], "n8n-workflow": PINNED["n8n-workflow"] } }),
  );
  let r = spawnSync("npm", ["install", "--no-audit", "--no-fund", "--silent"], { cwd: nodesDir, encoding: "utf8" });
  res.check("community node installed into n8n's nodes folder", r.status === 0, r.stderr?.slice(0, 200));

  const credFile = path.join(home, "cred.json");
  writeFileSync(credFile, JSON.stringify([{ id: "cred1", name: "Decisio", type: "jevApi", data: { apiKey: H.DUMMY_KEY, baseUrl: proxy.url } }]));
  const env = {
    ...process.env,
    N8N_USER_FOLDER: home,
    N8N_DIAGNOSTICS_ENABLED: "false",
    N8N_VERSION_NOTIFICATIONS_ENABLED: "false",
    N8N_TEMPLATES_ENABLED: "false",
    N8N_PERSONALIZATION_ENABLED: "false",
    N8N_RUNNERS_ENABLED: "false",
    N8N_ENCRYPTION_KEY: "decisio-examples-test-key",
  };
  const n8n = path.join(HERE, "node_modules", ".bin", "n8n");
  const run = (args) => spawnSync(n8n, args, { env, encoding: "utf8", timeout: 600000, maxBuffer: 1 << 28 });
  r = run(["import:credentials", `--input=${credFile}`]);
  res.check("credential imported (baseUrl is the proxy)", r.status === 0 && /imported 1 credential/i.test(r.stdout + r.stderr));

  function execute(id, name, list) {
    const file = path.join(home, `${id}.json`);
    writeFileSync(file, JSON.stringify(workflow(id, name, list)));
    const imp = run(["import:workflow", `--input=${file}`]);
    if (imp.status !== 0) throw new Error(`import:workflow failed: ${imp.stdout}${imp.stderr}`);
    const out = run(["execute", `--id=${id}`]);
    const text = out.stdout;
    const start = text.search(/^\{$/m);
    const ends = [...text.matchAll(/^\}$/gm)];
    const end = ends.length ? ends[ends.length - 1].index + 1 : -1;
    const exec = start >= 0 && end > start ? JSON.parse(text.slice(start, end)) : null;
    return { exec, status: out.status, text: text + out.stderr };
  }
  const runData = (exec) => exec?.data?.resultData?.runData ?? {};
  const outputsOf = (exec, name) => runData(exec)[name]?.[0]?.data?.main ?? [];
  const order = (exec, names) => names.sort((a, b) => runData(exec)[a][0].executionIndex - runData(exec)[b][0].executionIndex);

  // ---- the main run: seven Jev nodes in one workflow
  await proxy.reset();
  const main = execute("wf1", "decisio-jev", nodes);
  const n8nVersion = run(["--version"]).stdout.trim();
  res.observe("n8n_version_reported", n8nVersion);
  res.check("n8n execute finished the workflow", main.exec?.status === "success" && main.exec?.finished === true, main.exec?.status);
  const names = order(main.exec, nodes.map((n) => n.name).filter((n) => runData(main.exec)[n]));
  const recs = await proxy.records("/v1/");
  res.check("every Jev node sent exactly one request (7 nodes, 7 requests)", names.length === 7 && recs.length === 7, `${names.length} nodes, ${recs.length} requests`);
  const rec = Object.fromEntries(names.map((n, i) => [n.split(" ")[0], recs[i]]));
  for (const [letter, label] of [["A", "noul"], ["B", "choice"], ["C", "score"], ["D", "all three, simplified"], ["E", "all three, JSON, object state"], ["F", "route"], ["G", "choice without criteria (server 422)"]]) {
    res.addRequest(`${letter}: ${label}`, rec[letter]);
  }
  const jevOut = (letter) => outputsOf(main.exec, nodes.find((n) => n.name.startsWith(letter + " ")).name);
  const sent = (letter) => H.jsonBody(rec[letter]);
  const rawFull = (letter) => JSON.parse(rec[letter].upstream_body);

  for (const l of ["A", "B", "C", "D", "E", "F", "G"]) {
    res.check(`${l}: POST /v1/systemone`, rec[l].method === "POST" && rec[l].path === "/v1/systemone", rec[l].path);
  }
  // (b) what is sent
  const h = rec.A.headers;
  res.observe("request_body_fields", Object.keys(sent("A")).sort());
  res.observe("model_sent", sent("A").model);
  res.observe("request_headers_sent", Object.fromEntries(Object.entries(h).filter(([k]) => k !== "host")));
  res.observe("auth_header", "Authorization: Bearer <apiKey> (from the credential's authenticate block); User-Agent: n8n");
  res.check("body fields are state, model, questions", same(Object.keys(sent("A")).sort(), ["model", "questions", "state"]));
  res.check("model sent is the node's model parameter", sent("A").model === "jev-latest");
  res.check("Authorization is Bearer with the credential's key", /^Bearer </.test(h.authorization ?? ""), h.authorization);
  res.check("a noul question with only a Yes criterion sends criteria {true} (no empty false)", same(sent("A").questions.urgent.criteria, { true: q.urgent.criteria.true, false: q.urgent.criteria.false }));

  // (c) round trips
  res.check("A noul: node output is the server's response, unchanged", same(jevOut("A")[0][0].json.jev, rawFull("A")));
  res.check("B choice: node output is the server's response, unchanged", same(jevOut("B")[0][0].json.jev, rawFull("B")));
  res.check("C score: node output is the server's response, unchanged", same(jevOut("C")[0][0].json.jev, rawFull("C")));
  res.check("E all three, JSON mode and object state: output unchanged", same(jevOut("E")[0][0].json.jev, rawFull("E")));
  res.check("E: object state sent as an object", typeof sent("E").state === "object" && !Array.isArray(sent("E").state));
  const d = jevOut("D")[0][0].json.jev;
  const rd = rawFull("D").answers;
  const argmax = Object.entries(rd.frustration.probabilities).sort(([, a], [, b]) => b - a)[0][0];
  res.check("D simplified: noul is the raw probability", d.urgent === rd.urgent.noul, d.urgent);
  res.check("D simplified: choice is the raw label and confidence", d.department === rd.department.choice && d.department_confidence === rd.department.confidence, d.department);
  res.check("D simplified: score is the raw value, level is the legend entry of the most probable level", d.frustration === rd.frustration.score && d.frustration_level === rd.frustration.legend[argmax] && d.frustration_confidence === rd.frustration.confidence, `${d.frustration} ${d.frustration_level}`);
  res.check("D simplified: _model is the response model", d._model === rawFull("D").model);
  res.observe("simplified_output_keys", Object.keys(d).sort());
  res.finding("With Simplify Output on (the default), the node returns one flat value per question, plus _confidence and _level, and drops the probabilities, the legend and usage. Turn Simplify Output off to get the server's full response, which is passed through unchanged (including any extra fields Decisio adds).");

  // route
  const fo = outputsOf(main.exec, "F route");
  const rawF = rawFull("F").answers.route;
  const routeIdx = routes.map((r_) => r_.name).indexOf(rawF.choice);
  const lowConf = rawF.confidence < 0.5;
  const landed = fo.findIndex((o) => o && o.length);
  const fr = fo[landed][0].json.jev;
  res.check("F route: sent as one choice question named route", same(Object.keys(sent("F").questions), ["route"]) && sent("F").questions.route.type === "choice");
  res.check("F route: output index is the route Decisio chose, or Low Confidence below the threshold", landed === (lowConf ? 3 : routeIdx), `output ${landed}, choice ${rawF.choice}, confidence ${rawF.confidence}`);
  res.check("F route: route, confidence and probabilities identical to raw", fr.route === rawF.choice && fr.confidence === rawF.confidence && same(fr.probabilities, rawF.probabilities));
  res.check("F route: lowConfidence flag matches confidence < 0.5", fr.lowConfidence === lowConf);

  // (d) errors
  const g = outputsOf(main.exec, "G choice without criteria, continue on error");
  const gOut = g.flat().find(Boolean);
  const gErr = gOut?.json?.error;
  res.check("G: the server answered 422", rec.G.upstream_status === 422);
  res.check("G: the 422 surfaces as an error on the item (continue on error), not as an answer", typeof gErr === "string" && !("jev" in (g[0]?.[0]?.json ?? {})), String(gErr).slice(0, 160));
  res.observe("422_item_error", gErr);
  res.observe("422_item_error_object", gOut?.error ? { message: gOut.error.message, description: gOut.error.description, httpCode: gOut.error.httpCode } : null);
  res.check("G: with continue on error the item's error string is generic, Decisio's field detail only in the item's error object", !/criteria/.test(String(gErr)) && /criteria/.test(JSON.stringify(gOut?.error ?? "")), JSON.stringify(gOut?.error?.description ?? ""));
  res.finding("A 422 is an error, never an answer: with the node's error handling on Stop, the execution fails with a NodeApiError (httpCode 422) whose description is Decisio's detail as `loc: msg`. With Continue on Error, the item's `error` string is the generic 'Your request is invalid or could not be processed by the service' and Decisio's field detail is only in the item's `error` object (description).");
  await proxy.reset();
  const stop = execute("wf2", "decisio-jev-422", [stopNode]);
  const stopRecs = await proxy.records("/v1/");
  res.addRequest("H: choice without criteria, stop on error (server 422)", stopRecs[0]);
  const stopErr = stop.exec?.data?.resultData?.error;
  res.check("H: stop on error: the execution fails with a node error, not success", stop.exec?.status === "error" || stop.exec?.finished === false || Boolean(stopErr), `${stop.exec?.status} ${stopErr?.message ?? ""}`.slice(0, 160));
  res.check("H: the error carries Decisio's detail naming the field", /criteria/.test(JSON.stringify(stopErr ?? gErr ?? "")), JSON.stringify(stopErr?.description ?? stopErr?.message ?? "").slice(0, 200));
  res.check("H: a 422 is not retried (one request)", stopRecs.length === 1);
  res.observe("422_stop_error", { message: stopErr?.message, description: stopErr?.description, httpCode: stopErr?.httpCode });
  await proxy.reset();
  const one = execute("wf3", "decisio-jev-oneoption", [oneOption]);
  const oneRecs = await proxy.records("/v1/");
  res.check("I: a choice with one option is refused by the node before any request", oneRecs.length === 0 && Boolean(one.exec?.data?.resultData?.error), String(one.exec?.data?.resultData?.error?.message).slice(0, 120));
  res.finding("The node validates before sending: a Choice with fewer than two options and a Score with fewer than two levels are refused in the node (n8n error, no request). Decisio itself accepts a single option, so the node is stricter than the server. The JSON question mode only checks that each question has a valid type, so a choice with no criteria goes to the server and comes back as a 422 NodeApiError.");

  // (f) abstention fields, emulated
  for (const mode of ["answered", "abstained"]) {
    await proxy.reset();
    await proxy.emulate(mode);
    const ex = execute(`wf4${mode}`, `decisio-jev-${mode}`, [
      node("S simplified", { ...base, questionMode: "fields", questions: { question: [fieldQ.choice] } }),
      node("T full", { ...base, questionMode: "fields", questions: { question: [fieldQ.choice] }, options: { simplify: false } }),
      node("U route", { ...base, operation: "route", routeInstructions: q.department.instructions, routes: { values: routes }, lowConfidence: "bestRoute" }),
    ]);
    const rs = await proxy.records("/v1/");
    res.addRequest(`emulated abstention fields (${mode}): simplified, full, route`, rs[0]);
    const s = outputsOf(ex.exec, "S simplified")[0]?.[0]?.json?.jev ?? {};
    const t = outputsOf(ex.exec, "T full")[0]?.[0]?.json?.jev ?? {};
    const u = outputsOf(ex.exec, "U route").flat().find(Boolean)?.[0]?.json?.jev ?? {};
    const text = (o) => JSON.stringify(o);
    res.check(`emulated ${mode}: simplified output and route output do not carry abstained or unknown_probability`, !/abstained|unknown_probability/.test(text(s) + text(u)), text(s).slice(0, 100));
    res.check(`emulated ${mode}: full output (Simplify off) passes abstained and unknown_probability through`, /abstained/.test(text(t)) && /unknown_probability/.test(text(t)));
  }
  await proxy.emulate(null);
  res.finding("EMULATED (the stand-in has no abstain option; the proxy adds the two documented fields to a real answer): in Simplify mode and in Route by Choice the node drops `abstained` and `unknown_probability`, so a workflow cannot tell that the server abstained; with Simplify Output off they pass through in the item.");

  // ---- the model list and the credential test, in a hand-written context
  const { JevApi } = require("n8n-nodes-jev/dist/credentials/JevApi.credentials.js");
  const { searchModels } = require("n8n-nodes-jev/dist/nodes/Jev/listSearch/searchModels.js");
  const cred = new JevApi();
  const auth = (key) => cred.authenticate.properties.headers.Authorization.replace("=Bearer {{$credentials.apiKey}}", `Bearer ${key}`);
  const ctx = {
    getCredentials: async () => ({ apiKey: H.DUMMY_KEY, baseUrl: `${proxy.url}/` }),
    getNode: () => ({ name: "Jev" }),
    helpers: {
      httpRequestWithAuthentication: async (_type, o) => {
        const resp = await fetch(o.baseURL + o.url, { method: o.method, headers: { Authorization: auth(H.DUMMY_KEY) } });
        return { statusCode: resp.status, headers: Object.fromEntries(resp.headers), body: await resp.json() };
      },
    },
  };
  await proxy.reset();
  const list = await searchModels.call(ctx);
  rec.models = await proxy.last();
  res.addRequest("model list (hand-written context, not n8n)", rec.models);
  res.check("model list: GET /v1/models, one entry parsed", rec.models.path === "/v1/models" && list.results.length === 1 && Boolean(list.results[0].name), JSON.stringify(list.results[0]));
  res.observe("credential_defaults", { baseUrl: cred.properties.find((p) => p.name === "baseUrl").default, test_request: cred.test.request });
  await proxy.reset();
  const testResp = await fetch(`${proxy.url}${cred.test.request.url}`, { headers: { Authorization: auth(H.DUMMY_KEY) } });
  res.check("credential test request (GET /v1/models with the Bearer header) answers 200", testResp.status === 200 && (await proxy.last()).path === "/v1/models");
  res.finding("Model list and credential test were exercised only in a hand-written context (the request the code makes, replayed with fetch), not inside n8n's UI. The credential's Base URL is the host WITHOUT /v1 (the node appends /v1/systemone and /v1/models itself).");
  res.finding("Model: the node's Model parameter defaults to jev-latest and is always sent; Decisio ignores it and echoes it back as `model` in the answer. The list offered by the node comes from Decisio's own GET /v1/models, whose name differs from jev-latest, so picking from the list sends Decisio's served name.");
  res.observe("timeout", "The node passes options.timeout to n8n's HTTP helper; the option (default 60000 ms in the UI) exists only when the user adds it under Options, so with no option the n8n helper's own default applies (not determined here). Retries: 429 and 529 only, 3 times with backoff (option Max Retries, 0 to 10).");
} finally {
  proxy.stop();
  rmSync(home, { recursive: true, force: true });
}
code = res.finish(path.join(HERE, "results.json"));
process.exit(code);
