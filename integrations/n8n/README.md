# n8n-nodes-jev against Decisio

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It is not affiliated with n8n or with the node's maintainer either.
This folder checks that an existing, third-party integration runs against a Decisio server.
It never calls TypeSafe's hosted service and says nothing about it.

## What is verified

`n8n-nodes-jev` is a community node for n8n, maintained by Brains of Bots (`vibe-with-me-tools/n8n-nodes-jev`, MIT).
Its own README says it is not made or supported by TypeSafe.
Pinned versions: `n8n-nodes-jev@0.2.3`, run inside a real `n8n@2.35.7` with `n8n-workflow@2.35.3` (`package-lock.json` pins the whole tree).
n8n's `latest` tag is 2.42.4, which needs Node 24 or newer, so 2.35.7 is the newest release that runs on the Node 22 used here.
The server was a CPU stand-in with a 0.6B model, so the answers are poor and only the plumbing is checked.

What was run, and how:

- **In a real n8n.**
  `verify.mjs` installs the node into a throwaway n8n user folder, imports a credential and a workflow with `n8n import:credentials` and `n8n import:workflow`, and runs it with `n8n execute`.
  This is n8n's own execution engine, credential store, request helper and node loader, started from the command line.
  No web server is started, no port is opened and nothing is killed.
- **In a hand-written context.**
  The model list (`searchModels`, called with a stub context) and the credential's test request (replayed with `fetch` from the credential definition) are not run inside n8n, because they are triggered from the web UI.

## Run it

```bash
DECISIO_URL=http://127.0.0.1:8000 ./run.sh
```

`run.sh` runs `npm ci` (about 2,000 packages, because it installs n8n), then `node verify.mjs`, which writes `results.json` and exits non-zero when a check fails.
It needs `python3` on the path for the logging proxy.
`DECISIO_URL` is required, and a URL naming a TypeSafe host is refused.
The credential's Base URL is a local logging proxy that forwards to `DECISIO_URL`, and the API key is a dummy.

## Result

44 of 44 checks passed.

| Question | Answer |
| --- | --- |
| Path hit | `POST /v1/systemone` from seven Jev nodes in one workflow, one request each. The credential's Base URL is the host with no `/v1`. The model list is `GET /v1/models`. |
| Body fields sent | `state`, `model`, `questions`. `model` is the node's Model parameter, default `jev-latest`, always sent. Decisio echoes it back. |
| Auth header | `Authorization: Bearer <apiKey>` from the credential's `authenticate` block, and `User-Agent: n8n`. |
| noul round trip | With Simplify Output off, the node's output is the server's response unchanged. With it on, `urgent` is the raw probability. |
| choice round trip | Unchanged with Simplify off. With it on, the label and `_confidence` are the raw ones. |
| score round trip | Unchanged with Simplify off. With it on, the score and `_confidence` are the raw ones, and `_level` is the legend entry of the most probable level. |
| All three in one request | Identical, using JSON question mode and an object as `state`. |
| Route by Choice | Sent as one choice question named `route`. The item came out on the output of the route Decisio chose, or on the extra Low Confidence output when its confidence was under the threshold (with this 0.6B model it was). `route`, `confidence` and `probabilities` are identical to the raw ones. |
| 422 | A choice with no criteria (JSON question mode) is a 422 from the server. With error handling on Stop, the execution fails with a `NodeApiError` (httpCode 422) whose description is Decisio's detail as `loc: msg`. With Continue on Error, the item's `error` string is generic and the detail is in the item's error object. Not retried. |
| Default timeout | The Timeout option (60000 ms shown in the UI) exists only if the user adds it under Options. Without it the node passes no timeout and n8n's helper default applies, which was not determined here. Retries: 429 and 529 only, 3 times with backoff. All from source. |
| Fields the integration drops | Simplify Output (on by default) returns one flat value per question plus `_confidence` and `_level`, and drops `probabilities`, `legend` and `usage`. With it off the response passes through whole. `abstained` and `unknown_probability` (emulated) are dropped in Simplify mode and in Route by Choice, and pass through with Simplify off. |

## Findings

1. Nothing broke against Decisio, and the credential's Base URL must not end in `/v1`.
   The credential's default is `https://api.typesafe.ai`, so a Decisio user has to change it.
2. The node is stricter than the server: a choice with fewer than two options and a score with fewer than two levels are refused inside the node, with no request.
   Decisio itself accepts a single option.
   The JSON question mode only checks each question's `type`, so malformed questions there reach the server.
3. Continue on Error hides Decisio's detail in the item's `error` string: it reads "Your request is invalid or could not be processed by the service".
   The field path is only in the item's error object.
4. The Model dropdown lists Decisio's `GET /v1/models`, whose name (for example `decisio-qwen3.6-35b-a3b-letters`) differs from the default `jev-latest`.
   Both are accepted, because Decisio ignores the `model` field, and the answer names whatever was sent.
5. A workflow cannot see that a server abstained when Simplify Output is on or when it uses Route by Choice.
   This was emulated: the proxy added the two documented fields to a real answer, because the stand-in has no abstain option.

## Not exercised

- The web UI: the Test button on the credential, the Model dropdown, building the workflow by hand.
- Webhook or scheduled triggers, activated workflows, queue mode, and expressions in parameters.
- A slow server and the 429 and 529 retry path.
- A real abstaining server (`--abstain-option`).
- n8n 2.42 and later (they need Node 24).

## Files

| File | What |
| --- | --- |
| `package.json`, `package-lock.json` | The pins, and the locked tree (n8n included) |
| `verify.mjs` | The checks |
| `run.sh` | Install and run |
| `results.json` | The recorded run: checks, observations, findings, and every request with its response |
