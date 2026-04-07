from __future__ import annotations

import random

import pandas as pd

from sim.utils import parse_hhmmss, weighted_choice


def test_parse_hhmmss_none_and_empty():
    assert parse_hhmmss(None) is None
    assert parse_hhmmss(float("nan")) is None
    assert parse_hhmmss("") is None


def test_parse_hhmmss_valid():
    assert parse_hhmmss("13:30:00") == 13 * 60 + 30
    assert parse_hhmmss(" 14:05:30 ") == 14 * 60 + 5 + 0.5


def test_parse_hhmmss_invalid():
    assert parse_hhmmss("not-a-time") is None
    assert parse_hhmmss(pd.NA) is None  # type: ignore[arg-type]


def test_weighted_choice_deterministic():
    rng = random.Random(42)
    assert weighted_choice(["a", "b"], [0.0, 1.0], rng) == "b"
    rng2 = random.Random(0)
    out = weighted_choice(["x", "y", "z"], [0.2, 0.3, 0.5], rng2)
    assert out in {"x", "y", "z"}
