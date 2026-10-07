# TanStack AI TypeSafe adapter against Decisio

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It is not affiliated with TanStack either.
This folder checks that an existing, third-party integration runs against a Decisio server.
It never calls TypeSafe's hosted service and says nothing about it.

## What is verified

`@tanstack/ai-typesafe` (MIT, TanStack's `TanStack/ai` repository) used through `decide()` from `@tanstack/ai`.
Pinned versions: `@tanstack/ai-typesafe@0.1.8` and `@tanstack/ai@0.65.1` (its peer range is `^0.65.0`), on Node 22 (`package-lock.json` pins the whole tree).
The server was a CPU stand-in with a 0.6B model, so the answers are poor and only the plumbing is checked.

## Run it

```bash
DECISIO_URL=http://127.0.0.1:8000 ./run.sh
```

`run.sh` runs `npm ci`, then `node verify.mjs`, which writes `results.json` and exits non-zero when a check fails.
The proxy needs `python3` on the path.
`DECISIO_URL` is required, and a URL naming a TypeSafe host is refused.
The adapter is pointed at a local logging proxy that forwards to `DECISIO_URL`, and the API key is a dummy.

## Result

39 of 39 checks passed.

| Question | Answer |
| --- | --- |
| Path hit | `POST {baseURL}/v1/systemone`, so `baseURL` has no `/v1`. The option is `baseURL` (alias `baseUrl`), and a trailing slash is stripped. There is no environment variable for the base URL. |
| Body fields sent | `model` (the adapter's model, for example `jev-latest`), `state`, `questions`. `choice({ options })` and `score({ levels })` go out as `criteria`, and `boolean` goes out as `noul`. Decisio echoes `model` back. |
| Auth header | `Authorization: Bearer <key>` and `Content-Type: application/json`. No `User-Agent` of its own (Node's `fetch` default). Extra headers can be passed with `headers`. |
| noul round trip | `probability` identical to the raw `noul`, and `value` is `noul >= 0.5`. |
| choice round trip | `value` is the raw label, and `probability` is that label's raw probability. `probabilities` and `confidence` are identical. |
| score round trip | `score`, `probabilities`, `legend` and `confidence` identical. `value` is the nearest level label (rounded score, clamped), and `probability` is that level's. |
| All three in one request | Identical to the raw answers, with an object as `state`. |
| 422 | A choice with no `options` is sent without `criteria` and Decisio answers 422. `decide()` throws an `Error` whose message is `TypeSafe evaluate request failed: 422 Unprocessable Entity` followed by the response body, so the field detail is there. One request, no retry. |
| Default timeout | None: plain `fetch`, only the `abortSignal` option, no retries. Node's `fetch` applies undici's defaults (300 seconds to response headers). |
| Fields the integration drops | `unknown_probability` and `abstained` (emulated, see below), and the `x-decisio-*` response headers. `confidence`, `legend` and `probabilities` are kept, and `usage` is mapped to `promptTokens`, `completionTokens` and `totalTokens` under `result.meta`. |

## Findings

1. Nothing broke against Decisio.
2. `baseURL` must not end in `/v1`: it posts to `{baseURL}/v1/systemone`.
   This is the opposite of `@ai-sdk/typesafe-ai`, which wants `/v1` in its base URL.
   A base URL ending in `/v1` posts to `/v1/v1/systemone` and fails with a 404 error.
3. `typesafeDecider()` requires `TYPESAFE_API_KEY` even for a server that ignores keys.
   `createTypesafeDecider(model, 'any-string', { baseURL })` takes the key directly.
4. `choice()` does not check that `options` is present or non-empty, so a malformed choice reaches the server and comes back as a 422 `Error` (client-side checks exist only for `score()` with fewer than two levels, empty `questions`, and the reserved key `meta`).
5. By default the library logs errors to the console, which is noisy for an expected 422.
   The script passes `debug: false`.
6. `abstained` and `unknown_probability` are dropped, so a caller cannot tell that a server abstained.
   This was emulated: the proxy added the two documented fields to a real answer, because the stand-in has no abstain option.
   When `choice` is not the most probable key (the documented abstention behaviour), the adapter reports it as `value` together with that key's own probability and does not throw, unlike `@ai-sdk/typesafe-ai`.
7. The adapter's response check requires `usage.input_tokens` and `usage.output_tokens` to be numbers and `model` to be a string.
   Decisio always sends them.

## Not exercised

- A slow server: the timeout is stated from source, not provoked.
- A real abstaining server (`--abstain-option`).
- `decide()` middleware, the `modelOptions` argument (not used by this adapter), the BYOK helper, and the devtools event client.
- Browsers: `getTypesafeApiKeyFromEnv` also reads `window.env`.

## Files

| File | What |
| --- | --- |
| `package.json`, `package-lock.json` | The pins, and the locked tree |
| `verify.mjs` | The checks |
| `run.sh` | Install and run |
| `results.json` | The recorded run: checks, observations, findings, and every request with its response |
