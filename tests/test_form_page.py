# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the decisio-examples project
"""The form page's colours meet WCAG 2.2 AA (4.5 to 1 for text) in the light and the dark theme."""

import re
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "examples" / "03-form-validator" / "index.html"


def _hex(h: str) -> str:
    return "#" + "".join(c * 2 for c in h[1:]) if len(h) == 4 else h


def _vars(block: str) -> dict[str, str]:
    return {k: _hex(v) for k, v in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{3,6})\b", block)}


def _luminance(h: str) -> float:
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def themes() -> dict[str, dict[str, str]]:
    root, dark = re.findall(r":root \{([^}]*)\}", PAGE.read_text())[:2]
    light = _vars(root)
    return {"light": light, "dark": {**light, **_vars(dark)}}


# (text colour, the background it sits on, what it is)
PAIRS = [
    ("on-accent", "accent", "the Send button's text on the button"),
    ("ink", "card", "text in the form"),
    ("ink", "bg", "the heading"),
    ("muted", "bg", "the lede"),
    ("muted", "card", "the status line"),
    ("warn", "warn-bg", "a warning on its chip"),
    ("warn", "card", "the warning's meter and text"),
]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg", "what"), PAIRS)
def test_text_contrast_is_at_least_4_5(theme, fg, bg, what):
    t = themes()[theme]
    assert ratio(t[fg], t[bg]) >= 4.5, f"{what} in the {theme} theme: {ratio(t[fg], t[bg]):.2f}"


def test_the_button_text_is_not_white_on_the_pale_dark_blue():
    dark = themes()["dark"]
    assert dark["on-accent"] != "#ffffff"
    assert ratio("#ffffff", dark["accent"]) < 4.5  # the case the first version got wrong
