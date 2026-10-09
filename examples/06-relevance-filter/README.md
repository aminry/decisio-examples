# 06 A relevance filter in a retrieval pipeline

A retriever returns its top ten passages whether or not any of them answers the query.
Everything after it, a chat model or a person, pays to read the lot.
A relevance filter asks one yes/no question per passage and keeps only the ones that look like they answer it, and for a query that nothing answers, it can keep nothing.
This example measures what that buys, and what it costs, against the usual alternative.

## The questions

One request per query (`questions.py`).
The query is the state, and each retrieved passage is a yes/no question about it:

```python
state = {"query": "Which year did the treaty take effect?"}
questions = {
    f"p{rank}": noul(
        "Does the passage below contain the answer to the query?\n\nPassage (Title):\n<text>",
        true="The passage states the answer to the query",
        false="The passage is about something else, or is related but does not state the answer",
    )
    for rank, passage in enumerate(top10)
}
```

A passage is kept when the probability of yes is at least 0.50.
That value was fixed before any run and not tuned on the queries.

The retriever is BM25, written in the standard library (`bm25.py`), over a pool of 1,204 paragraphs.
It is a fair stand-in for the cheap first stage of most pipelines, and an easy one to beat: it is already good.

## What the report answers

- **Does the filter keep the right passage?** The share of answerable queries whose relevant paragraph survives.
- **How much does it cut?** Passages kept per query out of ten, and the share of kept passages that are the relevant one.
- **Does it ever say "nothing here"?** For queries no paragraph answers, how often it keeps zero.
- **Does its ordering beat BM25's?** The AUC of its probability for relevant against irrelevant, and how often it puts the relevant paragraph first.

## The comparison that can embarrass it

The standard tool for this job is a cross-encoder reranker.
`baseline_crossencoder.py` scores the same pairs with `cross-encoder/ms-marco-MiniLM-L-6-v2` (Apache-2.0) and keeps as many passages per query as the Decisio run did, so the two are compared at the same amount of context.
It is a fair fight on quality only: it runs on whatever CPU you have, and no latency from it is comparable with a server on a card.
It may win, and the report says so either way.

```bash
uv run examples/06-relevance-filter/baseline_crossencoder.py --match-run examples/06-relevance-filter/runs/<run>
```

## Run it

You need a Decisio server (see the [decisio README](https://github.com/aminry/decisio)).
With no flag, decisio 0.10.0 serves Gemma 4 31B, the default base (a 96 GB card; the decisio README's "Choosing a base" says when to pick another).
The example runs on whichever base the server serves.

```bash
uv sync
uv run python examples/06-relevance-filter/run.py --url http://127.0.0.1:8000
```

Add `--record --label <name>` and the machine flags to write a run record.
A run on the CPU stand-in only proves the steps work.

## The data

The development set of SQuAD 2.0, CC BY-SA 4.0: 1,204 paragraphs from 35 articles.
The sample is 200 answerable and 200 unanswerable queries, drawn with a fixed seed.
An unanswerable query is a question written to look as if its paragraph answered it, and it does not.
Another paragraph in the pool could still answer it, so "kept nothing" is a slightly harsh reading of the unanswerable queries.
Likewise, an answerable query's other passages are counted irrelevant even when a second one happens to state the answer.

Nothing from the dataset is committed.
The file is downloaded on first use and checked against a recorded sha256, and the run record keeps each request's id and sha256, not its text.

## What it measured

Recorded 2026-10-08 in Lab 2's card session (`runs/2026-10-08_gemma-4-31b/`): Gemma 4 31B, the default base of decisio 0.10.0, on one RTX PRO 6000 Blackwell Workstation Edition at 600 W and an AMD EPYC 9654.
The record is labelled decisio 0.9.0, as recorded: the server was decisio #114 at `bc74193`, before the 0.10.0 tag, serving Google's weights quantised to FP8 on load.

The measured line, from the record. A decision here is one request with ten passage questions, so the cost is per 1,000 queries, which is 10,000 passage judgements:

> 400 decisions, median 317.6 ms server time, gemma-4-31b, NVIDIA RTX PRO 6000 Blackwell Workstation Edition at 600 W, AMD EPYC 9654 96-Core Processor, decisio 0.9.0; $0.1352 per 1,000 decisions at $1.50 per card-hour (run `examples/06-relevance-filter/runs/2026-10-08_gemma-4-31b`).

At the preset (keep at 0.50), and the cross-encoder at the same amount of context (`runs/2026-10-08_baseline-crossencoder/`, `cross-encoder/ms-marco-MiniLM-L-6-v2`, with its threshold chosen to keep as many passages per query on average):

| | Decisio | Cross-encoder | BM25 alone |
| --- | ---: | ---: | ---: |
| Relevant paragraph kept (of the 188 answerable queries where BM25's top ten held it) | 182, 96.8% | 144, 76.6% | all 188 |
| Passages kept per answerable query, of ten | 1.32 | 1.10 | 10 |
| Relevant paragraph first (of those 188) | 93.1% | 92.0% | 86.7% |
| AUC, relevant against irrelevant | 0.990 | 0.966 | 0.911 |
| Unanswerable queries where nothing was kept (of 200) | 125, 62.5% | 86, 43.0% | 0 |

- BM25's top ten held the relevant paragraph for 188 of the 200 answerable queries, so 12 were out of the filter's reach.
- Decisio's median server time was 317.6 ms per query, on a 96 GB card. The cross-encoder scored all 400 queries in 5.7 seconds on a laptop CPU.
  That is a large difference in cost, and a laptop reranker is the cheaper tool where its quality is enough.

## Where it failed

- **Six relevant paragraphs were dropped** out of 188: `572f5703a23a5019007fc576` (0.41, first in BM25's order), `57281ab63acd2414000df494` (0.19) and four others below 0.06.
- **Unanswerable queries still kept passages for 75 of 200.** These are questions written to look answerable, and the filter sees the paragraph that looks like the answer.
  The README's reading of "kept nothing" is harsh, since another paragraph in the pool might answer, but the number is what it is.
- **The comparison is a snapshot.** One sample of 400 queries, a fixed seed, one small reranker. A larger reranker, or a threshold tuned on labelled data for either method, would move it.

## When not to use this

- **When the retriever's top few are already right.** Where BM25 puts the relevant paragraph first nearly every time, a filter has little to find. Look at the top-1 rate in the report before you add a stage.
- **When the passages are long.** Each question carries a whole passage. A filter over ten 4,000-character passages reads forty thousand characters per query. Measure the time before you put it in a request path.
- **When a reranker already does the job.** A small cross-encoder is cheap, and the baseline shows how it compares. Decisio's case is that it answers a question you write in words (for example "does this passage state a date?"), which a reranker trained on one notion of relevance cannot.

## Files

| File | What it is |
| --- | --- |
| `data.py` | Downloads the SQuAD 2.0 development set, checks its sha256, draws the seeded sample |
| `bm25.py` | The first-stage retriever |
| `questions.py` | One request per query: the query as state, one yes/no question per passage |
| `run.py` | Retrieves, filters, records and reports |
| `report.py` | The report's arithmetic, shared with the baseline |
| `baseline_crossencoder.py` | The cross-encoder reranker on the same pairs, at the same amount of context |
| `runs/` | The recorded runs |

Decisio is an independent project, not affiliated with or endorsed by TypeSafe.
