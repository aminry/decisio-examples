# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Okapi BM25 over a small pool, in the standard library: the retriever in front of the filter."""

from __future__ import annotations

import math
import re
from collections import Counter

STOP = frozenset(
    "the a an of in on at to for and or is are was were be by with as from that this it its which who what when where "
    "how why did does do has have had into than then".split()
)


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokens(d) for d in documents]
        self.avg = sum(map(len, self.docs)) / len(self.docs)
        n = len(self.docs)
        df = Counter(w for d in self.docs for w in set(d))
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for i, tf in enumerate(self.tf):
            norm = self.k1 * (1 - self.b + self.b * len(self.docs[i]) / self.avg)
            out.append(
                sum(self.idf[w] * tf[w] * (self.k1 + 1) / (tf[w] + norm) for w in q if tf.get(w) and w in self.idf)
            )
        return out

    def top(self, query: str, k: int) -> list[tuple[int, float]]:
        s = self.scores(query)
        order = sorted(range(len(s)), key=lambda i: (-s[i], i))[:k]
        return [(i, s[i]) for i in order]
