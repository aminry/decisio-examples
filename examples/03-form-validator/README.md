# 03 Form validator

Check what people type into a form, as they type it, with a probability instead of a regular expression.
A job title field that holds `asdf`, a company called `test test`, a message that says `hello`: none of these breaks a format rule, and all of them are junk.
Each field gets one yes/no question, and a low probability shows a soft warning beside the field.
The warning never blocks the form.

## The questions

One yes/no question per field (`questions.py`), for example:

```python
noul(
    "Is the job_title field a plausible job title?",
    true="A real job title or role, in any industry",
    false="A placeholder, random characters, a joke, or something that is not a role",
)
```

A field is flagged when the probability that it is fine falls below 0.30.
That value was fixed before any run and not tuned on the forms.

The page asks in two ways, and both are in the record:
- **As you type.** One field, 600 ms after you stop, one question.
- **On Send.** The whole form is the state and every filled field is a question, so the form is read once and the fields are answered together.

## Run it

You need a Decisio server (see the [decisio README](https://github.com/aminry/decisio)).
With no flag, decisio 0.10.0 serves Gemma 4 31B, the default base (a 96 GB card; the decisio README's "Choosing a base" says when to pick another).
The example runs on whichever base the server serves.
A Decisio server sends no CORS headers, so a page cannot call it from another origin.
`serve.py` is a small same-origin server: it serves the page and passes `POST /ask` on to the server's `/v1/systemone`, adding nothing and changing nothing.

```bash
uv sync
uv run python examples/03-form-validator/serve.py --url http://127.0.0.1:8000
# open http://127.0.0.1:18080/
```

Add `--record --label <name>` and the machine flags to write every forwarded request and answer to a run record.
Stop it with Ctrl-C, or a SIGTERM to its PID, and the record is closed on the way out.

To measure the questions without a browser, replay 40 forms through the same questions:

```bash
uv run python examples/03-form-validator/run.py --url http://127.0.0.1:8000
```

## The forms

`forms.jsonl` holds 40 forms, **written for this example and labelled by hand: they are synthetic**.
Twenty are fully valid.
Twenty have one or two invalid fields, 25 invalid values in all (8 job titles, 9 company names, 8 messages).
Eight to nine invalid values per field is small, so read every rate below as an illustration with a wide interval, and the intervals are printed.

## What it measured

Recorded 2026-10-08 in Lab 2's card session (`runs/2026-10-08_gemma-4-31b/`): Gemma 4 31B, the default base of decisio 0.10.0, on one RTX PRO 6000 Blackwell Workstation Edition at 600 W and an AMD EPYC 9654.
The record is labelled decisio 0.9.0, as recorded: the server was decisio #114 at `bc74193`, before the 0.10.0 tag, serving Google's weights quantised to FP8 on load.

The measured line, from the record:

> 40 decisions, median 73.8 ms server time, gemma-4-31b, NVIDIA RTX PRO 6000 Blackwell Workstation Edition at 600 W, AMD EPYC 9654 96-Core Processor, decisio 0.9.0; $0.0312 per 1,000 decisions at $1.50 per card-hour (run `examples/03-form-validator/runs/2026-10-08_gemma-4-31b`).

- The replay asks all three fields of a form in one request, as the page does on Send. The page's per-field requests while typing are not in this record.
- Invalid values flagged: 8 of 8 job titles, 9 of 9 company names and 8 of 8 messages.
- Valid values flagged: 0 of 32 job titles, 0 of 31 company names and 0 of 32 messages (the 95% intervals reach 10.7% to 11.0%).

## Where it failed

Nothing failed on these forms, and that is a fact about the forms.
The 25 invalid values are blatant (`asdf`, `test test`, `hello`), and every one was caught, with no false warning among 95 valid fields.
With 8 or 9 invalid values per field the data cannot say the false-warning rate is below about one in ten.
A real form has unusual but real job titles and half-typed messages, and this record says nothing about them.
Try it on a few hundred of your own submissions before you trust the 0.30 threshold.

## The clip

A screen recording of a real session at the page, made while `serve.py --record` writes its record.
The record and the clip are checked against each other: the number of requests on screen equals the record's.

## When not to use this

- **When a rule is enough.** A format check (an email address, a postcode) is cheaper and exact. Use the model for what a rule cannot say: whether the words make sense.
- **When a warning can cost a customer.** A false warning on a real but unusual job title is irritating, and the false-warning rate in the table is the price. Keep the warning soft, as here.
- **As the only guard against abuse.** Someone who wants to send junk will type plausible junk.

## Files

| File | What it is |
| --- | --- |
| `questions.py` | The three questions and the threshold |
| `index.html` | The page: three fields, a status line beside each, and Send |
| `serve.py` | The same-origin server that passes the page's questions on and records them |
| `forms.jsonl` | The 40 synthetic forms, with a label for each field |
| `run.py` | Replays the forms through the questions and writes the report |
| `runs/` | The recorded runs |

Decisio is built by [Tachara AI Lab](https://huggingface.co/tachara-ai).
Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
