from __future__ import annotations

import random
from typing import Any, Callable

import pandas as pd

from .constants import N_REPLICATIONS
from .engine import RouteSampler, Sim


def run_experiment(
    arrival_data: Any,
    route_probs: dict[str, float],
    vehicle_probs: dict[str, float],
    gate_samples: list[float],
    station_tables,
    build_arrival_sampler: Callable[[int, Any], Any],
    demand_scale: float = 1.0,
    base_seed: int = 12345,
    n_replications: int = N_REPLICATIONS,
) -> pd.DataFrame:
    # Independent replications with deterministic seeds for reproducibility.
    rows: list[dict[str, Any]] = []
    for r in range(n_replications):
        seed = base_seed + r
        sim = Sim(
            seed=seed,
            route_sampler=RouteSampler(route_probs, random.Random(seed + 111)),
            arrival_sampler=build_arrival_sampler(seed + 222, arrival_data),
            gate_samples=gate_samples,
            station_tables=station_tables,
            vehicle_probs=vehicle_probs,
            demand_scale=demand_scale,
        )
        res = sim.run()
        res["replication"] = r + 1
        res["demand_scale"] = demand_scale
        rows.append(res)
    return pd.DataFrame(rows)
