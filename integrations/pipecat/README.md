# Pipecat's Jev client against Decisio

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It is not affiliated with Pipecat or Daily either.
This folder checks that an existing, third-party integration runs against a Decisio server.
It never calls TypeSafe's hosted service and says nothing about it.

## What is verified

`pipecat.classifiers.jev` from `pipecat-ai` (BSD 2-Clause, `pipecat-ai/pipecat`): `JevClient`, the HTTP client, and `JevClassifier`, the typed classifier built on it.
Pinned version: `pipecat-ai[jev]==1.12.0` on Python 3.12 (`requirements.txt` pins the whole tree).
The server was a CPU stand-in with a 0.6B model, so the answers are poor and only the plumbing is checked.

Install: this runs for real, not by reading source.
`pipecat-ai`'s base install plus the `jev` extra (`httpx[http2]`) is enough, with no audio or transport extras, and `pipecat.classifiers.jev` imports without them.
The base install still pulls `numba`, `onnxruntime`, `numpy` and `openai`, so the venv is about 330 MB.

## Run it

```bash
DECISIO_URL=http://127.0.0.1:8000 ./run.sh
```

`run.sh` builds `.venv` (not committed) with `uv`, installs `requirements.txt`, runs `verify.py` and writes `results.json`.
The script exits non-zero when a check fails.
`DECISIO_URL` is required, and a URL naming a TypeSafe host is refused.
The client is pointed at a local logging proxy that forwards to `DECISIO_URL`, and the API key is a dummy.
`base_url` is always passed, because the default is the hosted service.

## Result

39 of 39 checks passed.

| Question | Answer |
| --- | --- |
| Path hit | `POST /v1/systemone`, and `connect()` does `GET /v1/models` first. The `base_url` has no `/v1`. The client asks for HTTP/2, but over plain `http://` Decisio saw HTTP/1.1. |
| Body fields sent | `model`, `state`, `questions`. `model` is always sent, default `jev-1.13.0`. Decisio ignores it. A yes/no question with only `yes` or only `no` sends the other side as an empty string. |
| Auth header | `Authorization: Bearer <api_key>` (a key is required), and `User-Agent: python-httpx/<version>`. |
| noul round trip | `YesNoResult.probability` identical to the raw `noul`. |
| choice round trip | `ChoiceResult.choice`, `probabilities` and `confidence` identical to the raw ones. |
| score round trip | `ScoreResult.score` and `confidence` identical, and each level's probability identical, in the question's order. |
| All three in one request | Identical, with an object as `state`. `JevClient.ask()` returns the raw answer dicts unchanged, and `on_metrics` fires with the token usage. |
| 422 | Raised as `ClassifierError("Jev rejected the request: HTTP 422")`, not retried. Decisio's detail is discarded (see findings). |
| Default timeout | 10 seconds (`DEFAULT_TIMEOUT`, passed to `httpx`). `max_retries` is 3 and only 429 and 529 are retried. From source and read back from the object. |
| Fields the integration drops | `unknown_probability` and `abstained` (emulated, see below) are not in the classifier's results, and `legend` is not in `ScoreResult`. `confidence` is kept, and `usage` is summed in `JevClient.usage`. |

## Findings

1. Nothing broke against Decisio.
2. A 422 loses its reason.
   The body, which in Decisio carries the field path and message, is not read: the only text is "HTTP 422".
   A caller cannot tell what was wrong with a question.
3. The default timeout is short (10 seconds).
   It was not provoked here, and it matters only for a slow server or a cold start.
4. A key is required even though Decisio ignores keys: `JevClient(api_key="")` raises `ValueError`.
5. `abstained` and `unknown_probability` are not in `JevClassifier`'s results, so a caller of the classifier cannot tell that a server abstained.
   `JevClient.ask()` returns the dicts unchanged and does show them.
   This was emulated: the proxy added the two documented fields to a real answer, because the stand-in has no abstain option.
   When `choice` is not the most probable key (the documented abstention behaviour), the classifier accepts it and does not throw.
6. A missing probability for a score level is read as 0.0 without an error (from source, not provoked).

## Not exercised

- A slow server and the 429 and 529 retry path.
- A real abstaining server (`--abstain-option`).
- Using a classifier inside a Pipecat pipeline with a transport, and `setup()` with a real task manager (the checks call `connect()` and the typed methods directly).
- HTTP/2 against a TLS server.

## Files

| File | What |
| --- | --- |
| `requirements.in`, `requirements.txt` | The pin, and the compiled pins of its tree |
| `verify.py` | The checks |
| `run.sh` | Venv, install, run |
| `results.json` | The recorded run: checks, observations, findings, and every request with its response |
