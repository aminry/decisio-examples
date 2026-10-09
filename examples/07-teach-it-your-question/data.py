# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""BANKING77: 13,083 customer messages to an online bank, each with one of 77 intents (PolyAI).

Licence: CC BY 4.0. Casanueva et al., "Efficient Intent Detection with Dual Sentence Encoders", 2020.
https://github.com/PolyAI-LDN/task-specific-datasets, read at a pinned commit and checked by sha256.
The messages are recorded in the run records, which the licence allows with this attribution.
"""

from __future__ import annotations

import csv
import hashlib
import random
from pathlib import Path

import httpx

COMMIT = "9d081458ff52e53cf7e848f414e6e9344e4e6696"
BASE = f"https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/{COMMIT}/banking_data/"
SHA256 = {
    "train.csv": "b06e26ac675513959a63135f11b94ea7786ed02da65db93a5650d8838cbc664b",
    "test.csv": "d12d6e3bc4c3103966ae786dc435913c0c563dfa328f5a3646d0e62cfeeb474d",
}
CACHE = Path(__file__).resolve().parent / "data"
SEED = 20261009


def _file(name: str) -> Path:
    path = CACHE / name
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        r = httpx.get(BASE + name, follow_redirects=True, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != SHA256[name]:
        raise RuntimeError(f"{path} has sha256 {got}, expected {SHA256[name]}; delete it to download again")
    return path


def _rows(name: str) -> list[dict]:
    with open(_file(name), newline="", encoding="utf-8") as f:
        return [
            {"id": f"{name[:-4]}-{i:05d}", "text": r["text"], "label": r["category"]}
            for i, r in enumerate(csv.DictReader(f))
        ]


def load() -> tuple[list[dict], list[dict], list[str]]:
    """(train rows, test rows, the 77 intents in alphabetical order)."""
    train, test = _rows("train.csv"), _rows("test.csv")
    return train, test, sorted({r["label"] for r in train})


def test_sample(test: list[dict], size: int) -> list[dict]:
    """A fixed random sample of the test split; the same on every run."""
    return random.Random(SEED).sample(test, min(size, len(test)))


def draw(train: list[dict], intents: list[str], per_intent: int, draw_no: int) -> list[dict]:
    """`per_intent` training messages for each intent, drawn with a seed that depends on the draw number."""
    rng = random.Random(SEED + 1 + draw_no)
    by = {i: [r for r in train if r["label"] == i] for i in intents}
    picked = [r for i in intents for r in rng.sample(by[i], per_intent)]
    rng.shuffle(picked)
    return picked
