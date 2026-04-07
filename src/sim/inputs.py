from __future__ import annotations

import pandas as pd

from customtypes import Customer as CustomerRecord

from .constants import (
    ARRIVAL_INTERVAL_MINUTES,
    CLEAN_DIR,
    CLOSE_TIME,
    MAX_GATE_SERVICE_MINUTES,
    MAX_STATION_SERVICE_MINUTES,
    OPEN_TIME,
    STATION_ORDER,
    StationTables,
)
from .utils import parse_hhmmss


def load_customer_master_df() -> pd.DataFrame:
    cm = pd.read_csv(CLEAN_DIR / "customer_master.csv")
    # Parse through typed Customer rows, then keep cm as DataFrame for vector ops.
    cm_customers: list[CustomerRecord] = [
        CustomerRecord.from_row(row) for row in cm.to_dict(orient="records")
    ]
    return pd.DataFrame([c.to_row() for c in cm_customers])


def build_interval_arrival_rates(cm: pd.DataFrame) -> list[tuple[float, float, float]]:
    # Estimate piecewise-constant arrival intensity from queue arrivals.
    x = cm.copy()
    x["queue_arrival_min"] = x["arrival_to_outside_queue"].apply(parse_hhmmss)
    x = x[
        (x["queue_arrival_min"].notna())
        & (x["queue_arrival_min"] >= OPEN_TIME)
        & (x["queue_arrival_min"] <= CLOSE_TIME)
    ]
    n_days = max(1, x["day"].nunique())
    bins = pd.interval_range(
        start=OPEN_TIME, end=CLOSE_TIME, freq=ARRIVAL_INTERVAL_MINUTES, closed="left"
    )
    x["interval"] = pd.cut(x["queue_arrival_min"], bins=bins)
    counts = x.groupby("interval", observed=False).size().reindex(bins, fill_value=0)
    rates: list[tuple[float, float, float]] = []
    for interval, count in counts.items():
        rates.append(
            (float(interval.left), float(interval.right), float(count / n_days))
        )
    return rates


def build_arrivals_by_day(cm: pd.DataFrame) -> dict[str, list[float]]:
    x = cm.copy()
    x["queue_arrival_min"] = x["arrival_to_outside_queue"].apply(parse_hhmmss)
    x = x[
        (x["queue_arrival_min"].notna())
        & (x["queue_arrival_min"] >= OPEN_TIME)
        & (x["queue_arrival_min"] <= CLOSE_TIME)
    ]
    return {day: g["queue_arrival_min"].tolist() for day, g in x.groupby("day")}


def build_route_probs(cm: pd.DataFrame) -> dict[str, float]:
    route_series = cm["route_pattern"].fillna("")
    route_series = route_series[route_series != ""]
    return route_series.value_counts(normalize=True).to_dict()


def build_vehicle_probs(cm: pd.DataFrame) -> dict[str, float]:
    return (
        cm["vehicle_size"]
        .fillna("S")
        .replace("", "S")
        .value_counts(normalize=True)
        .to_dict()
    )


def build_gate_samples(cm: pd.DataFrame) -> list[float]:
    x = cm.copy()
    x["queue_arrival_min"] = x["arrival_to_outside_queue"].apply(parse_hhmmss)
    x["entrance_min"] = x["entrance_time"].apply(parse_hhmmss)
    x = x.sort_values(["day", "queue_arrival_min", "entrance_min"])

    gate_samples: list[float] = []
    for _, g in x.groupby("day"):
        prev_entrance = g["entrance_min"].shift(1)
        mask = (
            prev_entrance.notna()
            & g["queue_arrival_min"].notna()
            & g["entrance_min"].notna()
            & (g["queue_arrival_min"] <= prev_entrance)
        )
        gaps = g.loc[mask, "entrance_min"] - prev_entrance[mask]
        valid = gaps[(gaps > 0) & (gaps <= MAX_GATE_SERVICE_MINUTES)]
        gate_samples.extend(valid.astype(float).tolist())
    return gate_samples if gate_samples else [0.25, 0.5, 0.75]


def build_station_tables(cm: pd.DataFrame, sv: pd.DataFrame) -> StationTables:
    svx = sv.copy()
    svx["service_time_minutes"] = pd.to_numeric(
        svx["service_time_minutes"], errors="coerce"
    )
    svx = svx[
        (svx["station"].isin(STATION_ORDER))
        & (svx["service_time_minutes"] > 0)
        & (svx["service_time_minutes"] <= MAX_STATION_SERVICE_MINUTES)
    ]
    merged = svx.merge(
        cm[["day", "source_file", "car_id", "vehicle_size", "route_pattern"]],
        on=["day", "source_file", "car_id"],
        how="left",
    )
    merged["vehicle_size"] = merged["vehicle_size"].fillna("S").replace("", "S")
    merged["route_pattern"] = merged["route_pattern"].fillna("")

    station_tables: StationTables = {}
    # Build hierarchical service-time lookup tables per station.
    for st in STATION_ORDER:
        g = merged[merged["station"] == st]
        by_station = g["service_time_minutes"].tolist()
        by_vs = {
            size: gg["service_time_minutes"].tolist()
            for size, gg in g.groupby("vehicle_size")
        }
        by_vs_route = {
            (size, route): gg["service_time_minutes"].tolist()
            for (size, route), gg in g.groupby(["vehicle_size", "route_pattern"])
        }
        station_tables[st] = (by_vs_route, by_vs, by_station)
    return station_tables


def _load_common_inputs() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, float],
    dict[str, float],
    list[float],
    StationTables,
]:
    cm = load_customer_master_df()
    sv = pd.read_csv(CLEAN_DIR / "station_visits.csv")
    route_probs = build_route_probs(cm)
    vehicle_probs = build_vehicle_probs(cm)
    gate_samples = build_gate_samples(cm)
    station_tables = build_station_tables(cm, sv)
    return cm, sv, route_probs, vehicle_probs, gate_samples, station_tables


def load_inputs_interval():
    cm, _sv, route_probs, vehicle_probs, gate_samples, station_tables = (
        _load_common_inputs()
    )
    interval_rates = build_interval_arrival_rates(cm)
    return cm, interval_rates, route_probs, vehicle_probs, gate_samples, station_tables


def load_inputs_predictive():
    cm, _sv, route_probs, vehicle_probs, gate_samples, station_tables = (
        _load_common_inputs()
    )
    arrivals_by_day = build_arrivals_by_day(cm)
    return cm, arrivals_by_day, route_probs, vehicle_probs, gate_samples, station_tables
