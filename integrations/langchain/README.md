# langchain-typesafe against Decisio

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It is not affiliated with LangChain either.
This folder checks that an existing, third-party integration runs against a Decisio server.
It never calls TypeSafe's hosted service and says nothing about it.

## What is verified

`TypeSafeClassifier` from `langchain-typesafe`, which LangChain's monorepo publishes (MIT).
Pinned version: `langchain-typesafe==0.0.1a3` on Python 3.12 (`requirements.txt` pins the whole tree, including `langchain-core 1.6.7` and `httpx2 2.13.1`).
The server was a CPU stand-in with a 0.6B model, so the answers are poor and only the plumbing is checked: paths, fields, parsing, errors.

## Run it

```bash
DECISIO_URL=http://127.0.0.1:8000 ./run.sh
```

`run.sh` builds `.venv` (not committed) with `uv`, installs `requirements.txt`, runs `verify.py` and writes `results.json`.
The script exits non-zero when a check fails.
`DECISIO_URL` is required, and a URL naming a TypeSafe host is refused.
The classifier is pointed at a local logging proxy that forwards to `DECISIO_URL` and records each request, and the API key is a dummy.

## Result

42 of 42 checks passed.

| Question | Answer |
| --- | --- |
| Path hit | `POST /v1/systemone`. `base_url` argument and `TYPESAFE_BASE_URL` both work, and the base URL has no `/v1` (the class appends it). A trailing slash is stripped. `ainvoke` uses the same path. |
| Body fields sent | `state`, `model`, `questions`. `model` is sent, default `jev-latest`. Decisio ignores it and echoes it back as the response `model`. |
| Auth header | `Authorization: Bearer <key>`, plus `Content-Type` and `User-Agent: langchain-typesafe/0.0.1a3`. A key is required at construction (see findings). |
| noul round trip | Probability identical to the raw server JSON. |
| choice round trip | Label, probabilities and confidence identical. |
| score round trip | Score, confidence, probabilities (int keys here, string keys on the wire) and legend identical. |
| All three in one request | Identical to the raw answers. LangChain messages as `state` are sent as a role and content list and accepted. |
| 422 | Raised as `TypeSafeUnprocessableEntityError` (status 422), with Decisio's `detail` on `.body`. Not retried. `str(error)` deliberately omits the body. |
| Default timeout | 30 seconds (`timeout=30.0`, applied to the sync and async `httpx2` clients), from source and read back from the object. No retries. |
| Fields the integration drops | `unknown_probability` and `abstained` (emulated, see below). The `x-decisio-*` response headers are not surfaced and `request_id` is `None`. `confidence`, `legend` and `usage` are parsed and kept. |

## Findings

1. Nothing broke against Decisio.
2. The classes validate before sending.
   A `Choice` with empty criteria and a `Score` with one level raise a pydantic `ValidationError` in the client and never reach the server.
   The 422 check therefore uses a request the classes do not validate: an empty `questions` mapping, and a `Choice` built with `model_construct` so that it has no criteria.
3. A key is required even though Decisio ignores keys.
   `TypeSafeClassifier(base_url=...)` with no `api_key` and no `TYPESAFE_API_KEY` raises `ValueError`, so a self-hosted setup passes a dummy key.
4. `abstained` and `unknown_probability` are dropped, so a caller cannot tell that a server abstained.
   The stand-in has no abstain option, so this is emulated: the proxy adds the two documented fields to a real answer.
   It shows the answer models ignore unknown fields (no crash), and nothing more.
5. A `Noul` with only `true` set sends only `true` in `criteria`, and Decisio accepts it.
6. The class is marked beta and logs a `LangChainBetaWarning` on construction.

## Not exercised

- A slow server: the 30 second timeout is stated from source, not provoked.
- A real abstaining server (`--abstain-option`).
- LangSmith tracing (disabled in the script) and the `experimental` middleware.
- Streaming, batching beyond one call, and serialization of the classifier.

## Files

| File | What |
| --- | --- |
| `requirements.in`, `requirements.txt` | The pin, and the compiled pins of its tree |
| `verify.py` | The checks |
| `run.sh` | Venv, install, run |
| `results.json` | The recorded run: checks, observations, findings, and every request with its response |
