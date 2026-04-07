from __future__ import annotations

import random

import pandas as pd

from sim.arrivals import ArrivalSampler
from sim.constants import OUT_DIR
from sim.experiment import run_experiment
from sim.inputs import load_inputs_predictive
from sim.reporting import observed_validation, summarize


def main():
    cm, arrivals_by_day, route_probs, vehicle_probs, gate_samples, station_tables = (
        load_inputs_predictive()
    )

    baseline = run_experiment(
        arrival_data=arrivals_by_day,
        route_probs=route_probs,
        vehicle_probs=vehicle_probs,
        gate_samples=gate_samples,
        station_tables=station_tables,
        build_arrival_sampler=lambda seed, data: ArrivalSampler(
            data, random.Random(seed)
        ),
        demand_scale=1.0,
        base_seed=1000,
    )
    plus20 = run_experiment(
        arrival_data=arrivals_by_day,
        route_probs=route_probs,
        vehicle_probs=vehicle_probs,
        gate_samples=gate_samples,
        station_tables=station_tables,
        build_arrival_sampler=lambda seed, data: ArrivalSampler(
            data, random.Random(seed)
        ),
        demand_scale=1.2,
        base_seed=2000,
    )

    baseline.to_csv(OUT_DIR / "baseline_replications.csv", index=False)
    plus20.to_csv(OUT_DIR / "plus20_replications.csv", index=False)
    pd.concat([baseline, plus20], ignore_index=True).to_csv(
        OUT_DIR / "all_replications.csv", index=False
    )
    summarize(baseline).to_csv(OUT_DIR / "baseline_summary.csv", index=False)
    summarize(plus20).to_csv(OUT_DIR / "plus20_summary.csv", index=False)
    observed_validation(cm).to_csv(
        OUT_DIR / "observed_validation_summary.csv", index=False
    )

    print("Saved predictive outputs to", OUT_DIR)


if __name__ == "__main__":
    main()
