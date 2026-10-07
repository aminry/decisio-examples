# Vercel AI SDK TypeSafe provider against Decisio

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It is not affiliated with Vercel either.
This folder checks that an existing, third-party integration runs against a Decisio server.
It never calls TypeSafe's hosted service and says nothing about it.

## What is verified

`@ai-sdk/typesafe-ai` (Apache-2.0, published by Vercel's release bot from `vercel/ai`) used through `ai`'s decision function.
Pinned versions: `ai@7.0.131`, `@ai-sdk/typesafe-ai@3.0.15`, `zod@4.6.5`, on Node 22 (`package-lock.json` pins the whole tree).
7.0.131 is the `latest` tag on npm today.
The server was a CPU stand-in with a 0.6B model, so the answers are poor and only the plumbing is checked.

Which name this version exports: `ai@7.0.131` exports **`experimental_decide`**.
`experimental_evaluate` is still exported, marked `@deprecated`, and is the same function object (`experimental_evaluate === experimental_decide`).
The provider's `decisionModel()` is the current method, and `evaluationModel` is kept as an alias of it.

## Run it

```bash
DECISIO_URL=http://127.0.0.1:8000 ./run.sh
```

`run.sh` runs `npm ci`, then `node verify.mjs`, which writes `results.json` and exits non-zero when a check fails.
The proxy needs `python3` on the path.
`DECISIO_URL` is required, and a URL naming a TypeSafe host is refused.
The provider is pointed at a local logging proxy that forwards to `DECISIO_URL`, and the API key is a dummy.

## Result

42 of 42 checks passed.

| Question | Answer |
| --- | --- |
| Path hit | `POST {baseURL}/systemone`, so `baseURL` must be `http://host:port/v1` to reach Decisio's `/v1/systemone`. A trailing slash is stripped. `TYPESAFE_AI_BASE_URL` is read when the provider is created. |
| Body fields sent | `model` (the id given to `decisionModel`, for example `jev-latest`), `state`, `questions`. A `boolean` question is sent as type `noul`. Decisio echoes `model` back. |
| Auth header | `Authorization: Bearer <key>`. The key comes from `apiKey` or `TYPESAFE_AI_API_KEY`, read at call time. The `User-Agent` is `ai/<version> ai-sdk-provider-utils/<version> node.js/<major>`. |
| noul round trip | `boolean` answer with `probability` identical to the raw `noul`. |
| choice round trip | Label and probabilities identical. `confidence` moves to `result.providerMetadata.typesafe.confidence`. |
| score round trip | Score and probabilities identical. `confidence` moves to provider metadata. |
| All three in one request | Identical to the raw answers, with an object as `state`. |
| 422 | A server 422 (a choice with empty criteria sent through the model's `doDecide`) is an `APICallError` with `statusCode` 422, not retryable, one request seen, and the message is Decisio's `detail` as JSON. |
| Default timeout | None in the provider or in the decision function (only `abortSignal`). Node's `fetch` applies undici's defaults of 300 seconds to headers and between body chunks. `maxRetries` defaults to 2 for retryable failures. |
| Fields the integration drops | `legend` (score), and `unknown_probability` and `abstained` (emulated, see below). `confidence` is kept in provider metadata and `usage` becomes `inputTokens`, `outputTokens` and `totalTokens`. The raw body and the `x-decisio-*` response headers are on `result.response`. |

## Findings

1. The one real incompatibility, by design: `baseURL` must include `/v1`.
   Written the way the other integrations take it (no `/v1`), the provider posts to `/systemone`, Decisio does not serve that path, and the call fails with a 404 `APICallError`.
   It fails loudly.
2. A key is required even though Decisio ignores keys.
   With no `apiKey` and no `TYPESAFE_AI_API_KEY` the call throws `LoadAPIKeyError` before any request.
3. The decision function validates answers, which can reject an answer Decisio documents.
   It requires the selected option to have the highest probability, and throws `InvalidResponseDataError` otherwise.
   Decisio's `docs/api.md` says a server run with `--abstain-option` answers "the best of the other options" while reporting the probabilities unchanged, so on an abstained answer `choice` need not be the most probable key.
   This was **emulated**, not seen: the stand-in has no abstain option, so the proxy rewrote a real answer to put the second most probable key in `choice`, and the SDK threw.
   Treat it as a likely failure on a real abstaining server, to be confirmed on one.
4. `experimental_decide` checks the input before sending: a choice with no criteria is an `InvalidArgumentError` and no request is made.
   Calling the model's `doDecide` directly with a choice that has no `criteria` throws a bare `TypeError` instead (`Object.keys(undefined)`), which only direct callers of `doDecide` see.
5. The call's `User-Agent` loses the provider's own `ai-sdk-typesafe-ai/<version>` suffix, because the decision function's headers replace it.
   This is cosmetic.
6. `rounding` is declared as 2 decimals for probabilities and scores, but only as a tolerance for validation.
   The values are not rounded, so they are identical to the server's.

## Not exercised

- A slow server and the retry path (5xx, 429): stated from source.
- A real abstaining server (`--abstain-option`).
- Telemetry, `providerOptions` warnings, the model registry and `globalThis.AI_SDK_DEFAULT_PROVIDER`.
- Browsers and edge runtimes.

## Files

| File | What |
| --- | --- |
| `package.json`, `package-lock.json` | The pins, and the locked tree |
| `verify.mjs` | The checks |
| `run.sh` | Install and run |
| `results.json` | The recorded run: checks, observations, findings, and every request with its response |
