# 07 Teach it your question

A frozen model reads your option names and answers from what it already knows.
It does not know what your labels mean in your data.
Decisio can learn one recurring question from a handful of labelled examples, without training the model, and apply that to every later question with the same options.
This example teaches a 77-option banking-intent question from ten labelled messages per intent, and measures what it changes on messages the server has never seen.

## What "teaching" is

A task is one question you ask again and again with the same options in the same order.
`POST /v1/tasks` takes the question and a list of labelled examples and fits two things, each kept only if cross-validation on your own examples shows a gain:

- a **calibration**, one correction per option on the model's probabilities;
- an **intent head**, for questions with ten or more options: a small linear layer on the model's hidden state that learns what your labels mean.

The model is not changed.
The server tells you, in words, what it kept and why (`applied` and `reason` in the response), and a question that matches the task is marked with an `x-decisio-tasks` response header.
The decisio guide, `docs/tasks.md`, has the rules.

## The question

One `choice` with 77 options, the intents, the same keys in the same order every time (`questions.py`):

```python
choice("Which intent does this message from a bank's customer express?", {intent: None for intent in intents})
```

Each registered example is an ordinary one-question request plus the answer wanted.

## What the run does

1. Ask the question of a fixed sample of held-out test messages, untaught.
2. Teach it: draw ten labelled messages per intent from the training split (770 in all) and `POST /v1/tasks`, timing it.
3. Ask the same test messages again.
4. Repeat steps 2 and 3 with two more independent draws of examples, then delete the task.
5. Report accuracy before and after, the change with a paired bootstrap interval over the test messages, how many messages each draw fixed and broke, the registration time, and what the server said it kept.

The draws are fixed by a seed, so the same run is the same examples.
The test messages are never among the registered ones.

## Run it

You need a Decisio server (see the [decisio README](https://github.com/aminry/decisio)).
With no flag, decisio 0.10.0 serves Gemma 4 31B, the default base (a 96 GB card; the decisio README's "Choosing a base" says when to pick another).
The example runs on whichever base the server serves.

```bash
uv sync
uv run python examples/07-teach-it-your-question/run.py --url http://127.0.0.1:8000
```

Add `--record --label <name>` and the machine flags to write a run record.
`--draws`, `--per-intent` and `--test-size` shrink it.
A run on the CPU stand-in only proves the steps work.
Registration is held in the server's memory, and this run deletes its task at the end.

## The data

BANKING77 (PolyAI), CC BY 4.0: 10,003 training and 3,080 test messages, 77 intents.
Read at a pinned commit of `PolyAI-LDN/task-specific-datasets` and checked by sha256.
The messages are recorded in the run record, which the licence allows with this attribution: Casanueva et al., "Efficient Intent Detection with Dual Sentence Encoders", 2020.
The test sample is 1,000 of the 3,080 messages, drawn with a fixed seed.

Decisio's own measurements already include BANKING77 (`EVAL_CARD.md`), and its temperatures were fitted on a private suite that contains all 150 of the suite's BANKING77 items, which are also questions in the Decision Index's public pools.
This example's test messages come from the benchmark's test split, which is public.
Read its numbers as what teaching does on a public benchmark, not on your data.

## What it measured

<!-- PENDING: card session B. The recorded run, its report and the measured line replace this block. -->
Not run yet.

## Where it failed

<!-- PENDING: card session B. What the record shows: a draw that broke messages, a correction the server declined, or what the head cost in time. -->
Not run yet.

## When not to use this

- **When your options change with every input.** Exam-style questions whose answers differ each time have no fixed list to learn, and registration refuses them.
- **When you have fewer than ten options.** The head needs ten or more options and five examples of each. Below that only the calibration is fitted, and it may well be declined.
- **When your labels disagree with each other.** Two people labelling the same kind of message differently look like noise, and the server declines to fit.
- **When you cannot keep the server's memory.** Registration lives in one server instance. A restart forgets it unless you export the task and start with `--tasks-file`.
- **When the order or the wording of the options changes.** A renamed, added or reordered option is a different task, and the head is bound to the option order it was fitted on.

## Files

| File | What it is |
| --- | --- |
| `data.py` | Fetches BANKING77 at a pinned commit, checks its sha256, draws the test sample and the examples |
| `questions.py` | The question and the body of the registration request |
| `run.py` | Asks before, teaches, asks after, three times, and writes the report |
| `runs/` | The recorded runs |

Decisio is built by [Tachara AI Lab](https://huggingface.co/tachara-ai).
Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
