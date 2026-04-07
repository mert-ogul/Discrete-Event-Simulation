from __future__ import annotations

from typing import Any

from sim.constants import STATION_ORDER


class FixedArrivals:
    """Minimal arrival process: one customer at gate opening."""

    def sample_day(self, demand_scale: float = 1.0) -> list[float]:
        _ = demand_scale
        return [13 * 60.0]


def minimal_station_tables() -> dict[str, Any]:
    # Service times always drawn from by_station fallback.
    samples = [2.0, 2.0, 2.0, 2.0, 2.0]
    empty_pairs: dict[tuple[str, str], list[float]] = {}
    empty_vs: dict[str, list[float]] = {}
    block = (empty_pairs, empty_vs, samples)
    return {st: block for st in STATION_ORDER}
