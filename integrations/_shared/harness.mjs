// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
// What every Node integration check shares: the URL guard, the logging proxy, and the results file.
//
// Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
// These checks never call TypeSafe's hosted service: the URL is refused if it names a TypeSafe host, the integration
// is pointed at a local logging proxy (logproxy.py, needs python3 on PATH), and the API key is a dummy.

import { spawn } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath } from "node:url";

export const SHARED = path.dirname(fileURLToPath(import.meta.url));
export const DUMMY_KEY = "dummy-key-not-a-real-credential";
export const CASES = JSON.parse(readFileSync(path.join(SHARED, "cases.json"), "utf8"));

export function decisioUrl() {
  const url = (process.env.DECISIO_URL ?? "").replace(/\/+$/, "");
  if (!url) {
    console.error("DECISIO_URL is not set: point it at a Decisio server, for example DECISIO_URL=http://127.0.0.1:8000");
    process.exit(2);
  }
  const host = new URL(url).hostname.toLowerCase();
  if (!host || host.includes("typesafe")) {
    console.error(`refusing DECISIO_URL=${url}: these checks run against a Decisio server, never TypeSafe's hosted service`);
    process.exit(2);
  }
  for (const v of ["TYPESAFE_AI_BASE_URL", "TYPESAFE_API_KEY", "TYPESAFE_AI_API_KEY", "TYPESAFE_BASE_URL", "JEV_API_KEY", "JEV_BASE_URL"]) {
    delete process.env[v];
  }
  process.env.NO_PROXY = process.env.no_proxy = "127.0.0.1,localhost";
  return url;
}

export function assertLocal(url) {
  const host = new URL(url).hostname;
  if (host !== "127.0.0.1") throw new Error(`integration pointed at ${url}, not at the local proxy`);
}

export async function httpJson(method, url, body) {
  const r = await fetch(url, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await r.text();
  try {
    return [r.status, JSON.parse(text)];
  } catch {
    return [r.status, text];
  }
}

export class Proxy {
  static async start(upstream) {
    const proc = spawn("python3", [path.join(SHARED, "logproxy.py"), "--upstream", upstream], {
      stdio: ["ignore", "pipe", "inherit"],
    });
    const rl = readline.createInterface({ input: proc.stdout });
    const line = await new Promise((resolve, reject) => {
      proc.once("error", reject);
      proc.once("exit", () => resolve(""));
      rl.once("line", resolve);
    });
    if (!line.startsWith("LISTENING ")) {
      proc.kill();
      throw new Error(`the logging proxy did not start: ${JSON.stringify(line)}`);
    }
    const p = new Proxy();
    p.proc = proc;
    p.url = `http://127.0.0.1:${line.split(" ")[1]}`;
    return p;
  }

  async records(prefix = "") {
    const [, recs] = await httpJson("GET", `${this.url}/__proxy/log`);
    return recs.filter((r) => r.path.startsWith(prefix));
  }

  async reset() {
    await httpJson("POST", `${this.url}/__proxy/reset`, {});
  }

  async emulate(mode) {
    await httpJson("POST", `${this.url}/__proxy/mode`, { emulate_abstention: mode });
  }

  async last() {
    const recs = await this.records();
    if (!recs.length) throw new Error("the proxy saw no request");
    return recs[recs.length - 1];
  }

  stop() {
    if (this.proc.exitCode === null) this.proc.kill("SIGTERM");
  }
}

export function jsonBody(rec) {
  return JSON.parse(rec.body);
}

// The answers object of the server's own reply, as the proxy recorded it before any emulation.
export function rawAnswers(rec) {
  return JSON.parse(rec.upstream_body).answers;
}

function maybeJson(text) {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
}

export class Results {
  constructor(name, versions, url) {
    this.doc = {
      integration: name,
      versions,
      date: new Date().toISOString().slice(0, 10),
      client_node: process.version,
      client_host: `${os.type()} ${os.release()} ${os.arch()}`,
      decisio_url_given: url,
      server_health: null,
      checks: [],
      observations: {},
      findings: [],
      requests: [],
    };
    this.url = url;
  }

  async init() {
    let status, health;
    try {
      [status, health] = await httpJson("GET", `${this.url}/health`);
    } catch (e) {
      console.error(`cannot reach ${this.url}/health: ${e.cause?.message ?? e.message}`);
      process.exit(2);
    }
    if (status !== 200 || typeof health !== "object") {
      console.error(`${this.url}/health answered ${status}: is the server up?`);
      process.exit(2);
    }
    this.doc.server_health = Object.fromEntries(["ok", "engine", "model", "base"].map((k) => [k, health[k] ?? null]));
    return this;
  }

  check(id, ok, detail = "") {
    this.doc.checks.push({ id, passed: Boolean(ok), detail: String(detail) });
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${id}  ${detail}`.trimEnd());
    return Boolean(ok);
  }

  observe(key, value) {
    this.doc.observations[key] = value;
  }

  finding(text) {
    this.doc.findings.push(text);
  }

  addRequest(label, rec) {
    const { host, "content-length": _len, ...headers } = rec.headers;
    this.doc.requests.push({
      label,
      method: rec.method,
      path: rec.path,
      headers,
      body: maybeJson(rec.body),
      status: rec.upstream_status ?? null,
      response: maybeJson(rec.returned_body || rec.upstream_body),
      emulated_abstention: rec.emulated ?? null,
    });
  }

  finish(out) {
    const passed = this.doc.checks.filter((c) => c.passed).length;
    const total = this.doc.checks.length;
    this.doc.summary = { passed, failed: total - passed, result: passed === total ? "pass" : "fail" };
    // a library's em dash in a quoted message is written as a hyphen
    writeFileSync(out, (JSON.stringify(this.doc, null, 2) + "\n").replaceAll("\u2014", "-"));
    console.log(`${this.doc.integration}: ${passed}/${total} checks passed, wrote ${out}`);
    return passed === total ? 0 : 1;
  }
}
