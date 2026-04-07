from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    s = str(value)
    return default if s.lower() == "nan" else s


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Customer:
    # Keys used to identify one customer across source files.
    day: str
    source_file: str
    car_id: str

    # Customer-level fields in output/cleaned/customer_master.csv.
    vehicle_size: str = ""
    arrival_to_outside_queue: str = ""
    entrance_time: str = ""
    departure_from_WRP: str = ""
    route_pattern: str = ""
    stations_visited: str = ""
    n_stations: int = 0
    abandoned_flag: int = 0
    forgot_pass_flag: int = 0
    priority_flag: int = 0
    blocked_flag: int = 0
    notes_comments_merged: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.day, self.source_file, self.car_id)

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Customer:
        """
        Build a Customer from a customer_master row-like mapping.
        Accepts both `notes/comments_merged` (csv column) and
        `notes_comments_merged` (python-friendly key).
        """
        return cls(
            day=_as_str(row.get("day")),
            source_file=_as_str(row.get("source_file")),
            car_id=_as_str(row.get("car_id")),
            vehicle_size=_as_str(row.get("vehicle_size")),
            arrival_to_outside_queue=_as_str(row.get("arrival_to_outside_queue")),
            entrance_time=_as_str(row.get("entrance_time")),
            departure_from_WRP=_as_str(row.get("departure_from_WRP")),
            route_pattern=_as_str(row.get("route_pattern")),
            stations_visited=_as_str(row.get("stations_visited")),
            n_stations=_as_int(row.get("n_stations"), 0),
            abandoned_flag=_as_int(row.get("abandoned_flag"), 0),
            forgot_pass_flag=_as_int(row.get("forgot_pass_flag"), 0),
            priority_flag=_as_int(row.get("priority_flag"), 0),
            blocked_flag=_as_int(row.get("blocked_flag"), 0),
            notes_comments_merged=_as_str(
                row.get("notes/comments_merged", row.get("notes_comments_merged", ""))
            ),
        )

    def to_row(self) -> dict[str, Any]:
        """
        Return a row dict with the exact customer_master output column names.
        """
        return {
            "day": self.day,
            "source_file": self.source_file,
            "car_id": self.car_id,
            "vehicle_size": self.vehicle_size,
            "arrival_to_outside_queue": self.arrival_to_outside_queue,
            "entrance_time": self.entrance_time,
            "departure_from_WRP": self.departure_from_WRP,
            "route_pattern": self.route_pattern,
            "stations_visited": self.stations_visited,
            "n_stations": self.n_stations,
            "abandoned_flag": self.abandoned_flag,
            "forgot_pass_flag": self.forgot_pass_flag,
            "priority_flag": self.priority_flag,
            "blocked_flag": self.blocked_flag,
            "notes/comments_merged": self.notes_comments_merged,
        }
