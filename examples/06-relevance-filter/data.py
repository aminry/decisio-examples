# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The corpus and the queries: the development set of SQuAD 2.0 (1,204 paragraphs, 11,873 questions).

Licence: CC BY-SA 4.0 (Rajpurkar et al., "Know What You Don't Know: Unanswerable Questions for SQuAD", ACL 2018;
https://rajpurkar.github.io/SQuAD-explorer/). Nothing from it is committed: the file is downloaded on first use and
checked against the sha256 recorded here, and a run's record keeps each request's id and sha256, not its text.

A query is answerable when its paragraph holds the answer, and unanswerable when the question was written to look as if
the paragraph did and it does not. For an unanswerable query nothing in the pool is marked relevant. Another paragraph
in the pool could still answer it, which makes the "keep nothing" count a slightly harsh reading.
The README says so.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import httpx

URL = "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json"
SHA256 = "80a5225e94905956a6446d296ca1093975c4d3b3260f1d6c8f68bc2ab77182d8"
CACHE = Path(__file__).resolve().parent / "data" / "squad-dev-v2.0.json"
SEED = 20261007
ANSWERABLE = 200
UNANSWERABLE = 200


def _raw() -> dict:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(URL, follow_redirects=True, timeout=120)
        r.raise_for_status()
        CACHE.write_bytes(r.content)
    blob = CACHE.read_bytes()
    got = hashlib.sha256(blob).hexdigest()
    if got != SHA256:
        raise RuntimeError(f"{CACHE} has sha256 {got}, expected {SHA256}; delete it to download again")
    return json.loads(blob)


def load(answerable: int = ANSWERABLE, unanswerable: int = UNANSWERABLE) -> tuple[list[dict], list[dict]]:
    """(paragraphs, queries): every paragraph as {pid, title, text}, and a seeded sample of queries as
    {qid, query, pid, answerable}, answerable ones first, in the order sampled."""
    paragraphs: list[dict] = []
    queries: list[dict] = []
    for article in _raw()["data"]:
        for p in article["paragraphs"]:
            pid = len(paragraphs)
            paragraphs.append({"pid": pid, "title": article["title"], "text": p["context"]})
            for qa in p["qas"]:
                queries.append(
                    {"qid": qa["id"], "query": qa["question"], "pid": pid, "answerable": not qa["is_impossible"]}
                )
    rng = random.Random(SEED)
    yes = rng.sample([q for q in queries if q["answerable"]], answerable)
    no = rng.sample([q for q in queries if not q["answerable"]], unanswerable)
    return paragraphs, yes + no
