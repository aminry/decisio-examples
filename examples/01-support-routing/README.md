# 01 Support routing

Route a support ticket to a queue, page a person when it is urgent, and send it to a human when the model is not sure.
One request per ticket, three questions, one forward pass each, no text generated and nothing to parse.

## The question

Each ticket is the state.
Three questions are asked about it in one request (`questions.py`):

| Question | Type | What comes back |
| --- | --- | --- |
| `urgent` | yes/no | the probability that the ticket needs a response within the hour |
| `queue` | choice, 6 options | a probability for each of `billing`, `access`, `bug`, `feature`, `cancellation`, `other` |
| `impact` | score, 4 levels | the probability-weighted impact level, from "no function impaired" to "data loss or legal exposure" |

The routing rule is nine lines (`route` in `questions.py`):

```python
queue, p = answer.top("queue")
lane = queue if p >= 0.80 else "human-review"
page = answer.p_yes("urgent") >= 0.50
```

Both thresholds were fixed before the first run and not tuned on the tickets.
The sweep table below shows what other values would have done, so you can pick your own.

## Run it

You need a Decisio server.
The README of [decisio](https://github.com/aminry/decisio) has the GPU, Docker, Mac and Ollama paths.
This example was written against decisio 0.9.0.

```bash
git clone https://github.com/aminry/decisio-examples
cd decisio-examples
uv sync
uv run python examples/01-support-routing/run.py --url http://127.0.0.1:8000
```

Add `--record --label <name>` and the machine flags (`--card`, `--power-limit`, `--cpu`, `--decisio-version`) to write a run record under `runs/`.
Without `--record` it is a plumbing check and writes nothing.
On the CPU stand-in it proves the steps work and nothing more.
On Ollama pass `--model aminroudaki/decisio-gemma`; Ollama builds its own prompt and applies no calibration, so its probabilities are not the ones measured here.

## The tickets

`tickets.jsonl` holds 60 tickets, 10 per queue, **written for this example and labelled by hand: they are synthetic**.
Ten tickets have a second acceptable queue, because a real ticket sometimes belongs to two (a failed payment that locks an account).
Six are urgent.
Six urgent tickets is a small number, so read the urgent line as an illustration, not a measurement.

## What it measured

<!-- PENDING: card session A. The recorded run, its report and the measured line replace this block. -->
Not run yet.

## Where it failed

<!-- PENDING: card session A. The most confident wrong answer of the recorded run, quoted from its record. -->
Not run yet.

## When not to use this

- **When the answer is not in the text.** A ticket that says "it is broken again" has no queue in it. The right behaviour is the human lane, and the threshold is what sends it there.
- **When a wrong route is expensive and there is no human lane.** Probabilities let you build the lane. Without one you are accepting the error rate.
- **When your tickets do not look like these.** Sixty synthetic tickets say the steps work. They do not say how it behaves on your queues. Label a few hundred of your own, or register the question from labelled examples so the server calibrates to them (example 07).

## Files

| File | What it is |
| --- | --- |
| `tickets.jsonl` | The 60 synthetic tickets, with their queue, an optional second acceptable queue, and whether they are urgent |
| `questions.py` | The three questions, the two thresholds and `route` |
| `run.py` | Asks every ticket, records the run, writes `report.md` and `report.json` |
| `runs/` | The recorded runs: every request as sent and every answer in full |

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
