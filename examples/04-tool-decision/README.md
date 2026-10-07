# 04 An agent decides whether to call a tool

Before an agent calls a tool, two small decisions come first: what should it do next, and does the call it is about to make need a person.
Decisio answers both with a probability, in a request of its own, so the loop does not wait for a chat model to think out loud.
A chat model still writes what the step needs (an answer, an expression, the arguments of a call), and it runs on your machine.
This example is a plain Python loop with no framework.

## The two questions

**What next.** A choice among five steps (`questions.py`):

| Step | When |
| --- | --- |
| `answer` | reply from general knowledge, no tool needed |
| `search` | look up company documents or policies first |
| `calculate` | do arithmetic, or a unit or date calculation |
| `ask_user` | the request is missing something, so ask |
| `act` | take an action that changes something: send, create, move, refund, delete, close, reset |

The step is taken when the model puts at least 0.60 on it.
Below that the assistant asks the user, which is always safe.
The threshold was fixed before any run and not tuned on the requests.

**Does the call need a person.** A yes/no question about the proposed call, asked after the chat model has written it:

```python
noul(
    "Would this call be hard to undo, send something outside the team, move money, or delete data?",
    true="Yes: a person should approve it first",
    false="No: it is easy to undo and stays inside the team",
)
```

A call is held for approval at 0.50 or more.
Also fixed before the run.

## Run it

You need a Decisio server (see the [decisio README](https://github.com/aminry/decisio)) and, for the loop, a local chat model through Ollama.

```bash
uv sync
ollama pull qwen3:0.6b
uv run python examples/04-tool-decision/agent.py --url http://127.0.0.1:8000 "What is 17.5% of 2,340?"
```

`agent.py` runs the loop: the calculator takes arithmetic and nothing else (it parses, never `eval`s), the search is plain word overlap over `corpus.md`, and calls are a dry run that print what they would do.
`qwen3:0.6b` is small enough for any laptop and weak at writing JSON, so pass a larger `--chat-model` for cleaner calls.
To score the two decisions without the chat model, replay the labelled requests:

```bash
uv run python examples/04-tool-decision/run.py --url http://127.0.0.1:8000
```

Add `--record --label <name>` and the machine flags to write a run record.
A run on the CPU stand-in only proves the steps work.

## The requests

`requests.jsonl` holds 62 requests, **written for this example and labelled by hand: they are synthetic**.
Twelve each for `answer`, `search`, `calculate` and `ask_user`, and 14 for `act`.
Each `act` request carries the call the model would be asked to approve (also written by hand, so the risk gate is scored on the same calls whatever chat model you use), and a label for whether it needs a person: 6 of 14 do.
Fourteen calls, six of them risky, is a small sample.
The report prints its intervals, and they are wide.

## What it measured

<!-- PENDING: card session A. The recorded run, its report and the measured line replace this block. -->
Not run yet.

## Where it failed

<!-- PENDING: card session A. A step taken wrongly, or a risky call not held, quoted from the record. -->
Not run yet.

## When not to use this

- **When the decision needs the tool's result.** Whether to refund depends on the order, and the order is behind a lookup. The model sees only what is in the request.
- **When a missed risky call is unacceptable.** The risk gate is one cheap layer. Keep the permissions of the tools themselves narrow, and treat the gate as the second lock.
- **For arguments.** Decisio picks among options. It does not write the email or the amount. That is the chat model's job here, and its mistakes are not Decisio's to catch.

## Files

| File | What it is |
| --- | --- |
| `questions.py` | The two questions, the two thresholds and `next_step` |
| `agent.py` | The loop, with a local chat model, a safe calculator, a word-overlap search and dry-run calls |
| `run.py` | Scores both decisions on the labelled requests and writes the report |
| `requests.jsonl` | The 62 synthetic requests, with the labelled step and, for actions, the call and its risk |
| `corpus.md` | Eight fictional handbook lines the search runs over |
| `runs/` | The recorded runs |

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
