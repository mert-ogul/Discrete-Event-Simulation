from __future__ import annotations

from sim.experiment import run_experiment

from sim_minimal import FixedArrivals, minimal_station_tables


def test_run_experiment_two_replications_returns_two_rows():
    df = run_experiment(
        arrival_data={},
        route_probs={"FWPM->REST": 1.0},
        vehicle_probs={"S": 1.0},
        gate_samples=[1.0, 1.5, 2.0],
        station_tables=minimal_station_tables(),
        build_arrival_sampler=lambda _seed, _data: FixedArrivals(),
        demand_scale=1.0,
        base_seed=10_000,
        n_replications=2,
    )
    assert len(df) == 2
    assert df["replication"].tolist() == [1, 2]
    assert (df["demand_scale"] == 1.0).all()
    assert "n_completed" in df.columns
    assert "mean_queue_wait" in df.columns
