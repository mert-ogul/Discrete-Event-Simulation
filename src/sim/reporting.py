from __future__ import annotations

import pandas as pd

from .utils import parse_hhmmss


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df.columns if c != "replication"]
    out = df[cols].agg(["mean", "std"]).T.reset_index()
    out.columns = ["metric", "mean", "std"]
    return out


def observed_validation(cm: pd.DataFrame) -> pd.DataFrame:
    x = cm.copy()
    x["q"] = x["arrival_to_outside_queue"].apply(parse_hhmmss)
    x["e"] = x["entrance_time"].apply(parse_hhmmss)
    x["d"] = x["departure_from_WRP"].apply(parse_hhmmss)
    x["obs_total_time"] = x["d"] - x["q"]
    x["obs_internal_time"] = x["d"] - x["e"]
    obs_total = x[
        (x["obs_total_time"].notna())
        & (x["obs_total_time"] >= 0)
        & (x["obs_total_time"] <= 240)
    ]["obs_total_time"]
    obs_internal = x[
        (x["obs_internal_time"].notna())
        & (x["obs_internal_time"] >= 0)
        & (x["obs_internal_time"] <= 240)
    ]["obs_internal_time"]
    return pd.DataFrame(
        [
            {
                "metric": "observed_total_time",
                "mean": float(obs_total.mean()),
                "std": float(obs_total.std(ddof=1)),
            },
            {
                "metric": "observed_internal_time",
                "mean": float(obs_internal.mean()),
                "std": float(obs_internal.std(ddof=1)),
            },
        ]
    )
