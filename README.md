# decisio-examples

Small, real prototypes built on [Decisio](https://github.com/aminry/decisio), the open-source serving layer for decisions.
Typed questions about a piece of text go in, a probability for every option comes out, from one forward pass of a frozen open checkpoint.

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
It implements TypeSafe's published System One wire format, so integrations built for that format work against it.

This repository is being built and is not public yet.

## What is here

| Folder | What it is |
| --- | --- |
| `common/` | A small client for `POST /v1/systemone`, the run recorder every example writes, and the measured line |
| `examples/` | One folder per prototype, each with its README, its code and a recorded run |
| `integrations/` | Checks that existing integrations run against a Decisio server |
| `tests/` | Tests for `common/` |

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
