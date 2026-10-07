# Integrations

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It implements TypeSafe's published System One wire format, so integrations written for that format can be pointed at a Decisio server.
This folder checks five such integrations, each written and maintained by someone else, against a Decisio server.
It never calls TypeSafe's hosted service and makes no claim about it.

What a check proves: the plumbing.
For each integration it records the request path, the body fields and the auth header it sends, whether one question of each type (noul, choice, score) round-trips with the integration's parsed result equal to the server's raw JSON, whether a 422 surfaces as an error, the default timeout, and which of Decisio's response fields the integration drops.
It does not measure accuracy: the recorded run used a CPU stand-in with a 0.6B model, so its answers are poor.

## Summary

Recorded 2026-10-07 against the CPU stand-in (Qwen3-0.6B-Base, `hf_letters`, not for measurement).

| Integration | Version | Maintained by | Result | Caveats |
| --- | --- | --- | --- | --- |
| [LangChain](langchain/) | `langchain-typesafe` 0.0.1a3 | LangChain (`langchain-ai/langchain`) | 42 of 42 checks pass | Needs a (dummy) API key. Validates questions before sending, so a malformed choice never reaches the server. Drops `abstained` and `unknown_probability` (emulated). Default timeout 30 s. |
| [Vercel AI SDK](ai-sdk/) | `ai` 7.0.131, `@ai-sdk/typesafe-ai` 3.0.15 | Vercel (`vercel/ai`) | 42 of 42 checks pass | `baseURL` must include `/v1`, or the call 404s. Exports `experimental_decide` (`experimental_evaluate` is a deprecated alias). Needs a (dummy) API key. **Likely to throw on an abstained answer** whose `choice` is not the most probable key (emulated, not seen on a real abstaining server). No timeout in the provider. |
| [n8n](n8n/) | `n8n-nodes-jev` 0.2.3, run in `n8n` 2.35.7 | Brains of Bots (third party, not made by TypeSafe) | 44 of 44 checks pass | Credential Base URL has no `/v1` and defaults to the hosted host. Simplify Output (default) drops probabilities, legend and usage. Continue on Error hides the 422 detail in the item's error string. Model list and credential test were not run inside n8n. |
| [TanStack AI](tanstack/) | `@tanstack/ai-typesafe` 0.1.8, `@tanstack/ai` 0.65.1 | TanStack (`TanStack/ai`) | 39 of 39 checks pass | `baseURL` has no `/v1` (the opposite of the AI SDK). `typesafeDecider()` needs `TYPESAFE_API_KEY`. `choice()` does not validate its options. No timeout, plain `fetch`. |
| [Pipecat](pipecat/) | `pipecat-ai` 1.12.0 (`jev` extra) | Pipecat (`pipecat-ai/pipecat`) | 39 of 39 checks pass | A 422 is reported as "HTTP 422" with Decisio's detail discarded. Default timeout 10 s. Needs a key. Installs without audio extras but is about 330 MB. |

Every "emulated" above means the same thing: the stand-in server has no abstain option, so a proxy adds the two fields Decisio documents for `--abstain-option` (`unknown_probability`, `abstained`) to a real answer.
Run the checks against a server started with an abstain option to replace the emulation with a real result.

## Run

```bash
DECISIO_URL=http://127.0.0.1:8000 ./run_all.sh            # all five
DECISIO_URL=http://127.0.0.1:8000 ./run_all.sh pipecat n8n  # some
```

`DECISIO_URL` defaults to `http://127.0.0.1:18000` in `run_all.sh`, and is required by every other script.
A URL that names a TypeSafe host is refused everywhere, and every API key is a dummy, so no check can reach the hosted service.

Needs `uv` (Python 3.12 venvs), Node 22 or newer with `npm`, `python3` (the logging proxy), `curl`, and network access to PyPI and npm for the first install.
The n8n check installs n8n itself, about 2,000 packages.
Each check writes `results.json` next to its README and exits non-zero when a check fails.
`run_all.sh` prints a summary table at the end and exits non-zero if any integration failed.

## How a check works

Each check starts `_shared/logproxy.py`, a standard-library reverse proxy on a free local port, in front of `DECISIO_URL`.
The integration is given the proxy's URL, so the proxy sees every request exactly as sent and the server's raw reply before the integration parses it.
The proxy records method, path, headers (credentials redacted), body, status and reply, and the check compares them with what the integration returned.
It is stopped by its own process id when the check ends.

| File | What |
| --- | --- |
| `_shared/logproxy.py` | The logging proxy, with an optional mode that adds the abstention fields to answers |
| `_shared/harness.py`, `_shared/harness.mjs` | The URL guard, the proxy handle and the results file, for Python and for Node |
| `_shared/cases.json` | The state, one question of each type, and the malformed requests every check uses |
| `run_all.sh` | Runs the checks and prints the table |

## Reading a `results.json`

| Key | Meaning |
| --- | --- |
| `checks` | Assertions. Any failed one fails the script. |
| `observations` | Facts recorded, such as the fields and headers sent, the default timeout and the error messages |
| `findings` | The prose findings, the same as in the integration's README |
| `requests` | Every request sent through the proxy, with the reply and a flag when the reply was rewritten by the emulation |
