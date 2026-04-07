from __future__ import annotations

import heapq
import random
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .constants import CLOSE_TIME, OPEN_TIME, STATION_CAPACITY, STATION_ORDER
from .utils import weighted_choice


@dataclass(order=True)
class Event:
    # Future Event Set item, ordered by (time, priority).
    time: float
    priority: int
    event_type: str = field(compare=False)
    customer_id: int = field(compare=False)


@dataclass
class SimCustomer:
    # Simulation-state record for one generated customer.
    cid: int
    arrival_queue_time: float
    vehicle_size: str
    spots_needed: int
    route: list[str]
    route_pattern: str
    gate_service_start: float | None = None
    entrance_time: float | None = None
    exit_time: float | None = None
    current_station_idx: int = -1
    current_station: str | None = None


class FES:
    # Thin heap wrapper to make event-scheduling intent explicit.
    def __init__(self):
        self.heap: list[Event] = []

    def add(self, event: Event):
        heapq.heappush(self.heap, event)

    def pop(self) -> Event:
        return heapq.heappop(self.heap)

    def __len__(self):
        return len(self.heap)


class RouteSampler:
    # Draw full station route patterns from empirical route frequencies.
    def __init__(self, route_probs: dict[str, float], rng: random.Random):
        self.routes = list(route_probs.keys())
        self.probs = list(route_probs.values())
        self.rng = rng

    def sample(self) -> list[str]:
        s = weighted_choice(self.routes, self.probs, self.rng)
        route = [x for x in str(s).split("->") if x in STATION_ORDER]
        return route if route else ["FWPM"]


class Sim:
    def __init__(
        self,
        seed: int,
        route_sampler: RouteSampler,
        arrival_sampler,
        gate_samples: list[float],
        station_tables,
        vehicle_probs: dict[str, float],
        demand_scale: float = 1.0,
    ):
        self.rng = random.Random(seed)
        np.random.seed(seed)
        self.route_sampler = route_sampler
        self.arrival_sampler = arrival_sampler
        self.gate_samples = gate_samples
        self.station_tables = station_tables
        self.vehicle_items = list(vehicle_probs.keys())
        self.vehicle_weights = list(vehicle_probs.values())
        self.demand_scale = demand_scale

        # Core simulation state.
        self.fes = FES()
        self.time = OPEN_TIME
        self.last_t = OPEN_TIME

        # Resource state.
        self.gate_queue: deque[int] = deque()
        self.gate_busy = False
        self.used_spots = {st: 0 for st in STATION_ORDER}

        # Entity state.
        self.customers: dict[int, SimCustomer] = {}
        self.completed: list[SimCustomer] = []
        self.next_cid = 1

        # Time-integrated performance counters.
        self.queue_length_area = 0.0
        self.queue_gt3_time = 0.0
        self.station_busy_spot_area = {st: 0.0 for st in STATION_ORDER}
        self.blocking_events = 0

    def schedule(self, t: float, p: int, event_type: str, cid: int):
        self.fes.add(Event(t, p, event_type, cid))

    def update_stats(self, new_t: float):
        # Integrate queue length and occupied spots over the elapsed interval.
        dt = new_t - self.last_t
        qlen = len(self.gate_queue)
        self.queue_length_area += qlen * dt
        if qlen > 3:
            self.queue_gt3_time += dt
        for st in STATION_ORDER:
            self.station_busy_spot_area[st] += self.used_spots[st] * dt
        self.last_t = new_t

    def sample_vehicle_size(self) -> str:
        return weighted_choice(self.vehicle_items, self.vehicle_weights, self.rng)

    def create_customer(self, arrival_t: float):
        vehicle_size = self.sample_vehicle_size()
        spots_needed = 2 if vehicle_size == "B" else 1
        route = self.route_sampler.sample()
        route_pattern = "->".join(route)
        c = SimCustomer(
            cid=self.next_cid,
            arrival_queue_time=arrival_t,
            vehicle_size=vehicle_size,
            spots_needed=spots_needed,
            route=route,
            route_pattern=route_pattern,
        )
        self.customers[c.cid] = c
        self.next_cid += 1
        return c

    def sample_gate_service(self) -> float:
        return self.rng.choice(self.gate_samples)

    def sample_station_service(
        self, station: str, vehicle_size: str, route_pattern: str
    ) -> float:
        by_vs_route, by_vs, by_station = self.station_tables[station]
        vals = by_vs_route.get((vehicle_size, route_pattern), [])
        if len(vals) >= 5:
            return self.rng.choice(vals)
        vals = by_vs.get(vehicle_size, [])
        if len(vals) >= 5:
            return self.rng.choice(vals)
        return self.rng.choice(by_station)

    def full_route_feasible(self, c: SimCustomer) -> bool:
        return all(
            STATION_CAPACITY[st] - self.used_spots[st] >= c.spots_needed
            for st in c.route
        )

    def try_start_gate(self):
        if self.gate_busy or not self.gate_queue:
            return
        c = self.customers[self.gate_queue[0]]
        # Assignment rule: admit only if the full downstream route has capacity.
        if not self.full_route_feasible(c):
            return
        cid = self.gate_queue.popleft()
        c = self.customers[cid]
        c.gate_service_start = self.time
        self.gate_busy = True
        self.schedule(self.time + self.sample_gate_service(), 1, "END_GATE", cid)

    def handle_arrival(self, cid: int):
        self.gate_queue.append(cid)
        self.try_start_gate()

    def handle_end_gate(self, cid: int):
        c = self.customers[cid]
        self.gate_busy = False

        first = c.route[0]
        if STATION_CAPACITY[first] - self.used_spots[first] < c.spots_needed:
            self.schedule(self.time + 0.1, 1, "END_GATE", cid)
            return

        c.entrance_time = self.time
        c.current_station_idx = 0
        c.current_station = first
        self.used_spots[first] += c.spots_needed
        self.schedule(
            self.time
            + self.sample_station_service(first, c.vehicle_size, c.route_pattern),
            2,
            "END_STATION",
            cid,
        )
        self.try_start_gate()

    def handle_end_station(self, cid: int):
        c = self.customers[cid]
        current = c.current_station
        if current is None:
            return
        next_idx = c.current_station_idx + 1
        if next_idx >= len(c.route):
            self.used_spots[current] -= c.spots_needed
            c.current_station = None
            c.exit_time = self.time
            self.completed.append(c)
            self.try_start_gate()
            return

        next_station = c.route[next_idx]
        if (
            STATION_CAPACITY[next_station] - self.used_spots[next_station]
            >= c.spots_needed
        ):
            self.used_spots[current] -= c.spots_needed
            c.current_station_idx = next_idx
            c.current_station = next_station
            self.used_spots[next_station] += c.spots_needed
            self.schedule(
                self.time
                + self.sample_station_service(
                    next_station, c.vehicle_size, c.route_pattern
                ),
                2,
                "END_STATION",
                cid,
            )
            self.try_start_gate()
        else:
            # Vehicle keeps occupying current station until downstream capacity opens.
            self.blocking_events += 1
            self.schedule(self.time + 0.1, 3, "RETRY_MOVE", cid)

    def handle_retry_move(self, cid: int):
        c = self.customers[cid]
        current = c.current_station
        if current is None:
            return
        next_station = c.route[c.current_station_idx + 1]
        if (
            STATION_CAPACITY[next_station] - self.used_spots[next_station]
            >= c.spots_needed
        ):
            self.used_spots[current] -= c.spots_needed
            c.current_station_idx += 1
            c.current_station = next_station
            self.used_spots[next_station] += c.spots_needed
            self.schedule(
                self.time
                + self.sample_station_service(
                    next_station, c.vehicle_size, c.route_pattern
                ),
                2,
                "END_STATION",
                cid,
            )
            self.try_start_gate()
        else:
            self.schedule(self.time + 0.1, 3, "RETRY_MOVE", cid)

    def initialize(self):
        for at in self.arrival_sampler.sample_day(self.demand_scale):
            c = self.create_customer(at)
            self.schedule(at, 0, "ARRIVAL", c.cid)

    def run(self):
        self.initialize()
        # Standard event-loop execution until the FES is empty.
        while len(self.fes):
            ev = self.fes.pop()
            self.update_stats(ev.time)
            self.time = ev.time
            if ev.event_type == "ARRIVAL":
                self.handle_arrival(ev.customer_id)
            elif ev.event_type == "END_GATE":
                self.handle_end_gate(ev.customer_id)
            elif ev.event_type == "END_STATION":
                self.handle_end_station(ev.customer_id)
            elif ev.event_type == "RETRY_MOVE":
                self.handle_retry_move(ev.customer_id)
            else:
                raise ValueError(ev.event_type)
        self.update_stats(max(self.time, CLOSE_TIME))
        return self.collect_results()

    def collect_results(self) -> dict:
        # Convert per-customer traces and integrated counters into KPIs.
        horizon = max(self.last_t - OPEN_TIME, 1e-9)
        queue_waits: list[float] = []
        total_times: list[float] = []
        internal_times: list[float] = []
        for c in self.completed:
            if c.gate_service_start is not None:
                queue_waits.append(c.gate_service_start - c.arrival_queue_time)
            if c.exit_time is not None:
                total_times.append(c.exit_time - c.arrival_queue_time)
            if c.entrance_time is not None and c.exit_time is not None:
                internal_times.append(c.exit_time - c.entrance_time)
        out = {
            "n_completed": len(self.completed),
            "mean_queue_wait": float(np.mean(queue_waits)) if queue_waits else np.nan,
            "mean_total_time": float(np.mean(total_times)) if total_times else np.nan,
            "mean_internal_time": (
                float(np.mean(internal_times)) if internal_times else np.nan
            ),
            "mean_queue_length": self.queue_length_area / horizon,
            "frac_time_queue_gt3": self.queue_gt3_time / horizon,
            "blocking_events": self.blocking_events,
        }
        for st in STATION_ORDER:
            avg_busy = self.station_busy_spot_area[st] / horizon
            out[f"avg_busy_spots_{st.lower()}"] = avg_busy
            out[f"util_spots_{st.lower()}"] = avg_busy / STATION_CAPACITY[st]
        return out
