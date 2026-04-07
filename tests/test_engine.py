from __future__ import annotations

import random

from sim.engine import RouteSampler, Sim

from sim_minimal import FixedArrivals, minimal_station_tables


def test_sim_run_completes_with_minimal_inputs():
    route_sampler = RouteSampler({"FWPM->REST": 1.0}, random.Random(1))
    gate_samples = [1.0, 1.5, 2.0]
    vehicle_probs = {"S": 1.0}
    sim = Sim(
        seed=123,
        route_sampler=route_sampler,
        arrival_sampler=FixedArrivals(),
        gate_samples=gate_samples,
        station_tables=minimal_station_tables(),
        vehicle_probs=vehicle_probs,
        demand_scale=1.0,
    )
    out = sim.run()
    assert out["n_completed"] == 1
    assert out["mean_queue_wait"] >= 0.0
    assert "mean_total_time" in out
