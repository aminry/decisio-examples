# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""Check every README in the repository, and (with --public) refuse one that is not ready to be public.

Always: no em dash or en dash, none of the words the author bans, and every example README has its required sections.
With --public: no PENDING marker is left, so no README still says "Not run yet".
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED = [
    "leverage", "synergy", "circle back", "delve", "it's important to note", "navigate the landscape", "tapestry",
    "testament to", "realm", "foster", "embark", "unlock", "elevate", "seamless", "it's worth noting",
    "that being said",
]  # fmt: skip
DASHES = (chr(0x2014), chr(0x2013))
SECTIONS = ("## When not to use this", "## Where it failed", "## What it measured")
NONAFFILIATION = "not affiliated with or endorsed by TypeSafe"
BUILT_BY = "Decisio is built by [Tachara AI Lab](https://huggingface.co/tachara-ai)."


def check(public: bool) -> list[str]:
    problems: list[str] = []
    for md in sorted(ROOT.rglob("*.md")):
        rel = md.relative_to(ROOT)
        if any(part in {".venv", "node_modules", ".git", "runs"} for part in rel.parts):
            continue
        text = md.read_text()
        for ch in DASHES:
            if ch in text:
                problems.append(f"{rel}: contains a dash character U+{ord(ch):04X}")
        low = text.lower()
        for word in BANNED:
            if re.search(rf"\b{re.escape(word)}", low):
                problems.append(f"{rel}: contains the banned word '{word}'")
        if rel.parts[0] == "examples" and len(rel.parts) == 3 and rel.name == "README.md":
            for s in SECTIONS:
                if s not in text:
                    problems.append(f"{rel}: missing the section '{s}'")
            if NONAFFILIATION not in text:
                problems.append(f"{rel}: missing the non-affiliation line")
            if BUILT_BY not in text:
                problems.append(f"{rel}: missing the line that says who builds Decisio")
        if str(rel) == "README.md" and BUILT_BY not in text:
            problems.append(f"{rel}: missing the line that says who builds Decisio")
        if public and "PENDING" in text:
            problems.append(f"{rel}: still holds a PENDING marker")
    return problems


if __name__ == "__main__":
    found = check("--public" in sys.argv)
    print("\n".join(found) if found else "readmes ok")
    raise SystemExit(1 if found else 0)
