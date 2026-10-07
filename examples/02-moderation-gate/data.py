# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The labelled prompts: the test split of jackhhao/jailbreak-classification, at a pinned revision.

Licence: Apache-2.0, as the dataset card states (checked 2026-10-07). The card says nothing about where its jailbreak
prompts came from, so this example redistributes none of them: the file is downloaded on first use into data/ (not
committed), its sha256 is checked against the one recorded here, and a run's record holds each prompt it sent, which the
card's Apache-2.0 licence allows. Attribution: Jack Hhao, https://huggingface.co/datasets/jackhhao/jailbreak-classification.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import httpx

REVISION = "2f2ceeb39658696fd3f462403562b6eea5306287"
URL = f"https://huggingface.co/datasets/jackhhao/jailbreak-classification/resolve/{REVISION}/default/jailbreak_dataset_test.csv"
SHA256 = "a546ce540973d8f5ef87ce3be4bd21ee5923154b9dda86eba5a12c7fa00829da"
# Chosen before any run: a prompt longer than this is left out, and the report says how many that was.
MAX_CHARS = 4000
CACHE = Path(__file__).resolve().parent / "data" / "jailbreak_dataset_test.csv"


def fetch() -> Path:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(URL, follow_redirects=True, timeout=60)
        r.raise_for_status()
        CACHE.write_bytes(r.content)
    got = hashlib.sha256(CACHE.read_bytes()).hexdigest()
    if got != SHA256:
        raise RuntimeError(f"{CACHE} has sha256 {got}, expected {SHA256}; delete it to download again")
    return CACHE


def load() -> tuple[list[dict], int]:
    """The prompts as {id, text, jailbreak}, in file order, and how many were left out for length."""
    rows = list(csv.DictReader(open(fetch(), newline="", encoding="utf-8")))
    kept, dropped = [], 0
    for i, r in enumerate(rows):
        if len(r["prompt"]) > MAX_CHARS:
            dropped += 1
            continue
        kept.append({"id": f"jb-test-{i:03d}", "text": r["prompt"], "jailbreak": r["type"] == "jailbreak"})
    return kept, dropped
