from __future__ import annotations

from pathlib import Path

# Project paths.
ROOT = (
    Path(__file__).resolve().parents[2]
    if Path(__file__).resolve().parents[1].name == "src"
    else Path(__file__).resolve().parents[1]
)
CLEAN_DIR = ROOT / "output" / "cleaned"
OUT_DIR = ROOT / "output" / "simulation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Simulation system definition.
STATION_ORDER = ["FWPM", "DCDDGPCH", "GRWCTEGS", "REST"]
STATION_CAPACITY = {"FWPM": 4, "DCDDGPCH": 4, "GRWCTEGS": 3, "REST": 2}

# Times are represented as minutes since midnight.
OPEN_TIME = 13 * 60.0
CLOSE_TIME = 17 * 60.0
MAX_GATE_SERVICE_MINUTES = 5.0
MAX_STATION_SERVICE_MINUTES = 30.0

# Experiment defaults.
N_REPLICATIONS = 30
ARRIVAL_INTERVAL_MINUTES = 30

# Lookup table aliases.
StationServiceTable = tuple[
    dict[tuple[str, str], list[float]],
    dict[str, list[float]],
    list[float],
]
StationTables = dict[str, StationServiceTable]
IntervalRate = tuple[float, float, float]
ArrivalsByDay = dict[str, list[float]]
