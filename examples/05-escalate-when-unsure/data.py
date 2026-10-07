# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The questions: the test split of ARC-Challenge (allenai/ai2_arc), 1,172 multiple-choice science questions.

Licence: CC BY-SA 4.0, as the dataset card states (checked 2026-10-07). Nothing from it is committed, and a run's record
holds each request's id and sha256, not its text (`Run(redact=True)`), so no adaptation of the questions is published.
The file is downloaded on first use from Hugging Face's datasets server and checked against the sha256 of its canonical
form recorded here, so a change upstream stops the run instead of changing it.

Attribution: Clark et al., "Think you have Solved Question Answering? Try ARC, the AI2 Reasoning Challenge", 2018.
https://huggingface.co/datasets/allenai/ai2_arc
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

SERVER = "https://datasets-server.huggingface.co/rows"
TOTAL = 1172
SHA256 = "061b8650f90f841fe4b3da58e118770c26e856e61f33154bc90242c0fbb9cea0"
CACHE = Path(__file__).resolve().parent / "data" / "arc_challenge_test.json"


def _fetch() -> list[dict]:
    items = []
    with httpx.Client(timeout=60) as c:
        for offset in range(0, TOTAL, 100):
            r = c.get(
                SERVER,
                params={
                    "dataset": "allenai/ai2_arc",
                    "config": "ARC-Challenge",
                    "split": "test",
                    "offset": offset,
                    "length": 100,
                },
            )
            r.raise_for_status()
            for row in r.json()["rows"]:
                x = row["row"]
                items.append(
                    {
                        "id": x["id"],
                        "question": x["question"],
                        "labels": x["choices"]["label"],
                        "texts": x["choices"]["text"],
                        "answer": x["answerKey"],
                    }
                )
    return items


def _canon(items: list[dict]) -> str:
    return json.dumps(items, sort_keys=True, ensure_ascii=False)


def load() -> list[dict]:
    """The 1,172 items as {id, question, labels, texts, answer}, in the dataset's order."""
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(_canon(_fetch()), encoding="utf-8")
    text = CACHE.read_text(encoding="utf-8")
    got = hashlib.sha256(text.encode()).hexdigest()
    if got != SHA256:
        raise RuntimeError(f"{CACHE} has sha256 {got}, expected {SHA256}; delete it to download again")
    return json.loads(text)
