from __future__ import annotations

import random

import numpy as np

from .constants import CLOSE_TIME, OPEN_TIME


class IntervalArrivalSampler:
    """
    Preserve empirical arrival density by interval:
    Poisson count per interval + uniform placement within interval.
    """

    def __init__(
        self, interval_rates: list[tuple[float, float, float]], rng: random.Random
    ):
        self.interval_rates = interval_rates
        self.rng = rng

    def sample_day(self, demand_scale: float = 1.0) -> list[float]:
        arrivals: list[float] = []
        for start_min, end_min, mean_count in self.interval_rates:
            lam = max(0.0, mean_count * demand_scale)
            n = np.random.poisson(lam)
            for _ in range(n):
                arrivals.append(self.rng.uniform(start_min, end_min))
        arrivals.sort()
        return arrivals


class ArrivalSampler:
    """
    Predictive mode:
    pick a historical day, draw Poisson volume around that day size, and jitter times.
    """

    def __init__(self, arrivals_by_day: dict[str, list[float]], rng: random.Random):
        self.arrivals_by_day = {k: sorted(v) for k, v in arrivals_by_day.items() if v}
        self.days = list(self.arrivals_by_day.keys())
        self.rng = rng

    def sample_day(self, demand_scale: float = 1.0) -> list[float]:
        if not self.days:
            return []
        day = self.rng.choice(self.days)
        base = self.arrivals_by_day[day]
        n = np.random.poisson(max(1e-9, len(base) * demand_scale))
        arrivals: list[float] = []
        for _ in range(n):
            t = self.rng.choice(base) + self.rng.uniform(-0.2, 0.2)
            arrivals.append(min(max(t, OPEN_TIME), CLOSE_TIME))
        arrivals.sort()
        return arrivals
