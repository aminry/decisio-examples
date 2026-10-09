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
With no flag, decisio 0.10.0 serves Gemma 4 31B, the default base (a 96 GB card; the decisio README's "Choosing a base" says when to pick another).
The example runs on whichever base the server serves.

```bash
git clone https://github.com/aminry/decisio-examples
cd decisio-examples
uv sync
uv run python examples/01-support-routing/run.py --url http://127.0.0.1:8000
```

Add `--record --label <name>` and the machine flags (`--card`, `--power-limit`, `--cpu`, `--decisio-version`) to write a run record under `runs/`.
Without `--record` it is a plumbing check and writes nothing.
On the CPU stand-in it proves the steps work and nothing more.
On the laptop path, Ollama serves its Gemma 4 12B listing, because that is the one that fits a 16 GB machine: pass `--model aminroudaki/decisio-gemma`.
Ollama builds its own prompt and applies no calibration, so its probabilities are not the ones measured here.

## The tickets

`tickets.jsonl` holds 60 tickets, 10 per queue, **written for this example and labelled by hand: they are synthetic**.
Ten tickets have a second acceptable queue, because a real ticket sometimes belongs to two (a failed payment that locks an account).
Six are urgent.
Six urgent tickets is a small number, so read the urgent line as an illustration, not a measurement.

## What it measured

Recorded 2026-10-08 in Lab 2's card session (`runs/2026-10-08_gemma-4-31b/`): Gemma 4 31B, the default base of decisio 0.10.0, on one RTX PRO 6000 Blackwell Workstation Edition at 600 W and an AMD EPYC 9654.
The record is labelled decisio 0.9.0, as recorded: the server was decisio #114 at `bc74193`, before the 0.10.0 tag, serving Google's weights quantised to FP8 on load.

The measured line, from the record:

> 60 decisions, median 77.6 ms server time, gemma-4-31b, NVIDIA RTX PRO 6000 Blackwell Workstation Edition at 600 W, AMD EPYC 9654 96-Core Processor, decisio 0.9.0; $0.0324 per 1,000 decisions at $1.50 per card-hour (run `examples/01-support-routing/runs/2026-10-08_gemma-4-31b`).

- At the preset, 58 of 60 tickets were routed and 57 were right: 98.3% (95% interval 90.9% to 99.7%).
- The two that went to a person were `c7` (a cancellation with a refund demand, routed to billing at 0.58) and `o8` (a security-whitepaper request, `other` at 0.70, under the threshold).
- Raising the threshold to 0.90 routed 57 tickets and all 57 were right. At 0.95 it routed 49, also all right.
- Sixty synthetic tickets, ten per queue, are easy: read the intervals, not the point values.

## Where it failed

- **The paging threshold was wrong.** Fixed before the run at 0.50, it paged 29 of the 60 tickets. Only 6 are urgent, so 23 pages were false.
  All six urgent tickets scored 0.98 or higher, but so did one ticket that is not urgent, so no threshold on this probability separates them.
  The model reads "within the hour" generously: a password reset (`a2`, 0.85), an expired invite link (`a9`, 0.96) and an empty CSV export (`g1`, 0.96) all scored as urgent.
  The fix is in the question, not the threshold: say what "urgent" means in your desk's terms, and measure it on your own tickets.
- **The one confident routing error** was `f4`, "We need single-sign-on with Azure AD. Is it on the roadmap and when?", labelled `feature` and routed to `access` at 0.85.
  Single sign-on is a login feature, so the label is arguable. It is the kind of error a threshold does not catch.

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

Decisio is built by [Tachara AI Lab](https://huggingface.co/tachara-ai).
Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
