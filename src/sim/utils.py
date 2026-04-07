from __future__ import annotations

from typing import Any, Sequence, TypeVar

import pandas as pd

T = TypeVar("T")


def parse_hhmmss(x: Any) -> float | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        h, m, sec = map(int, s.split(":"))
    except Exception:
        return None
    return h * 60 + m + sec / 60.0


def weighted_choice(items: Sequence[T], probs: Sequence[float], rng) -> T:
    u = rng.random()
    c = 0.0
    for item, p in zip(items, probs):
        c += p
        if u <= c:
            return item
    return items[-1]
