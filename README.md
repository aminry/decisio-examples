# decisio-examples

Small, real prototypes built on [Decisio](https://github.com/aminry/decisio), the open-source serving layer for decisions.
Typed questions about a piece of text go in, a probability for every option comes out, from one forward pass of a frozen open checkpoint.

Decisio is built by [Tachara AI Lab](https://huggingface.co/tachara-ai).
Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It implements TypeSafe's published System One wire format, so integrations built for that format work against it.


## The examples

Each example has its own README, a recorded run and one measured line.
They ran on Gemma 4 31B, the default base of decisio 0.10.0, on an RTX PRO 6000 at 600 W, in one session on 2026-10-08, and the records are labelled decisio 0.9.0 (the server was decisio #114, before the 0.10.0 tag).
The data is synthetic or public, and the READMEs say which.

| | Example | What the record shows | Where it failed |
| --- | --- | --- | --- |
| 01 | [Support routing](examples/01-support-routing/) | 58 of 60 tickets routed at 0.80, 57 right; the rest go to a person | Paging at 0.50 sent 29 pages for 6 urgent tickets |
| 02 | [A gate in front of a chat model](examples/02-moderation-gate/) | 115 of 118 jailbreaks blocked; 19 of 255 benign prompts blocked | 17 of those 19 are role-play personas |
| 03 | [Form validator](examples/03-form-validator/) | 25 of 25 invalid values flagged, 0 of 95 valid ones | Nothing failed, because the forms are easy |
| 04 | [An agent decides whether to call a tool](examples/04-tool-decision/) | 56 of 62 next steps right; 6 of 6 risky calls held | The "ask the user" fallback never fired |
| 05 | [Escalate only when unsure](examples/05-escalate-when-unsure/) | 98.5% right among the 1,145 kept of 1,172, ECE 0.022 | 17 of 31 errors were confident and kept |
| 06 | [A relevance filter](examples/06-relevance-filter/) | Kept the relevant paragraph for 182 of 188 queries, against 144 for a small cross-encoder | The cross-encoder is far cheaper: 5.7 s for all 400 queries on a laptop CPU |

## Integrations

[`integrations/`](integrations/) checks that five existing integrations, each written and maintained by someone else, run against a Decisio server: `langchain-typesafe`, the Vercel AI SDK's TypeSafe provider, an n8n community node, TanStack AI's adapter and Pipecat's client.
All five passed their plumbing checks on 2026-10-07 (and again on the card server on 2026-10-08), and the summary lists what you would trip over: the base URL form differs, a key is always required, and some drop fields.

## What is here

| Folder | What it is |
| --- | --- |
| `common/` | A small client for `POST /v1/systemone`, the run recorder every example writes, and the measured line |
| `examples/` | One folder per prototype, each with its README, its code and a recorded run |
| `integrations/` | Checks that existing integrations run against a Decisio server |
| `lab/` | The script that recorded the examples on a card |
| `tests/` | Tests for `common/` and the examples |

## How an example is built

- Every example is a real run. Its record (`runs/<date>_<label>/`) holds every request as sent and every answer in full.
- Every clip is rendered from a record. Nothing in a clip is re-run, edited or invented.
- Inputs are public data with the licence recorded, or synthetic data labelled as synthetic.
- The one measured line in each README (latency and cost) comes from a card session, with the machine named.
  A run on the CPU stand-in or through Ollama proves the steps work and carries no measurement.
- Every README shows one recorded failure and says when not to use the pattern.

## Run the tests

```bash
uv sync
uv run pytest
uv run ruff check .
```

## Licence

Apache-2.0 (`LICENSE`).
Commits carry a DCO sign-off (`git commit -s`).
