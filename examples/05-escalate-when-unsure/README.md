# 05 Escalate only when unsure

A cheap, fast model answers every question, and the ones it is unsure about go somewhere better: a larger model, a reasoning model, a person.
That only works if "unsure" is a number you can trust.
Decisio returns a probability for every option, so the top probability is the number: keep the answer at or above a threshold, escalate below it.
The example measures how well that number does the job, on 1,172 public multiple-choice questions.

## The question

Each question is one request (`questions.py`): the question is the state, and the options are a `choice`.

```python
state, questions = (
    question_text,
    {"answer": choice("Which option answers the question correctly?", {"A": ..., "B": ..., "C": ..., "D": ...})},
)
answer = decisio.ask(state, questions)
option, p = answer.top("answer")
lane = "keep" if p >= 0.80 else "escalate"
```

The threshold of 0.80 was fixed before any run and not tuned on the questions.
The report's sweep shows what every other value would have done.

## What the report answers

- **Of the questions kept, how many are right?** Accuracy among the answers above the threshold, with its interval.
- **Of the wrong answers, how many were escalated?** That is the number that matters: an error you escalate is an error you can fix.
- **What does escalation cost?** The share of questions sent up, which is what you pay the second step for.
- **Is the probability calibrated?** A reliability table, and the ECE over 10 equal-mass bins as EVAL_CARD defines it.

The comparison that keeps it honest is in the sweep: escalating the same share of questions at random would leave the kept answers exactly as accurate as the whole set.
Anything above that is what the probability buys.

## Run it

You need a Decisio server (see the [decisio README](https://github.com/aminry/decisio)).

```bash
uv sync
uv run python examples/05-escalate-when-unsure/run.py --url http://127.0.0.1:8000
```

`demo.py` answers a seeded sample live and shows the key after each answer.
Add `--escalate-model <name>` to hand the escalated ones to a local Ollama chat model and see whether the second step got them right.
That is a demonstration of the wiring, and a small local model is usually not stronger than the first step, so its number says nothing about what a real second step would do.

Add `--record --label <name>` and the machine flags to write a run record.
A run on the CPU stand-in only proves the steps work.

## The data

The test split of ARC-Challenge (allenai/ai2_arc), 1,172 science questions, CC BY-SA 4.0 on its dataset card.
Nothing from it is committed.
The file is downloaded on first use and checked against a recorded sha256, and the run record keeps each request's id and sha256, not its text.
It is a public benchmark, and a model may have seen it in training.
The temperatures Decisio serves were fitted on a private suite that does not contain ARC (`EVAL_CARD.md` section 4), so the questions are not ones the server was calibrated on.

## What it measured

<!-- PENDING: card session A. The recorded run, its report and the measured line replace this block. -->
Not run yet.

## Where it failed

<!-- PENDING: card session A. The most confident wrong answer of the recorded run, quoted by id from the record. -->
Not run yet.

## When not to use this

- **When the questions are not like these.** Science exam questions with four options are an easy case for a probability. Your questions may be vaguer, or the options may overlap, and then the top probability separates right from wrong less well. Measure it on your own labelled items before you set a threshold.
- **When the second step is no better.** Escalating to a model that is no stronger than the first buys nothing. The probability tells you where the first step is weak, not that the second is good.
- **When a confident error is the expensive one.** The most confident wrong answers are listed in the report. If one of those would hurt, escalate on the question and not on the probability.

## Files

| File | What it is |
| --- | --- |
| `data.py` | Downloads ARC-Challenge's test split, checks its sha256 |
| `questions.py` | One request per question, the threshold and the lane |
| `run.py` | Answers every question and writes the report: coverage, accuracy among kept, errors escalated, reliability, ECE |
| `demo.py` | A seeded live sample, with an optional local second step |
| `runs/` | The recorded runs |

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
