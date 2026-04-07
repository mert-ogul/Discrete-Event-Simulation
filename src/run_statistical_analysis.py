from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "output" / "cleaned"
TABLE_DIR = ROOT / "output" / "tables"
FIG_DIR = ROOT / "output" / "figures"
REPORT_PATH = ROOT / "output" / "report_summary.md"

STATIONS = ["ENTRANCE_GATE", "FWPM", "DCDDGPCH", "GRWCTEGS", "REST"]


def parse_hhmmss(x: Any) -> float | None:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, sec = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= sec <= 59):
        return None
    return h * 60 + m + sec / 60.0


def ensure_dirs() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)


def add_customer_types(cm: pd.DataFrame) -> pd.DataFrame:
    cm = cm.copy()
    cm["special_case_flag"] = (
        (cm["abandoned_flag"] == 1)
        | (cm["forgot_pass_flag"] == 1)
        | (cm["priority_flag"] == 1)
        | (cm["blocked_flag"] == 1)
    )
    cm["vehicle_size_clean"] = cm["vehicle_size"].replace("", "UNK")

    def classify(row: pd.Series) -> str:
        if bool(row["special_case_flag"]):
            return "SPECIAL_CASE"
        n = int(row["n_stations"]) if pd.notna(row["n_stations"]) else 0
        route = str(row["route_pattern"]) if pd.notna(row["route_pattern"]) else ""
        has_dc = "DCDDGPCH" in route
        has_gr = "GRWCTEGS" in route
        if n <= 1:
            return "SINGLE_STOP"
        if has_dc and has_gr:
            return "COMPLEX_MULTI_STOP"
        if has_dc or has_gr:
            return "MEDIUM_MULTI_STOP"
        return "OTHER_MULTI_STOP"

    cm["customer_type"] = cm.apply(classify, axis=1)
    return cm


def stations_visit(cm: pd.DataFrame):
    cm = cm.copy()
    stations = ["FWPM", "DCDDGPCH", "GRWCTEGS", "REST"]

    # Filling with indicators of boolean value if customer visited station
    for station in stations:
        cm[f"visit_{station}"] = (
            cm["stations_visited"]
            .fillna("")
            .apply(lambda x: int(station in str(x).split("|")))
        )
    # create dataframe with the going to station probability
    rows = []
    for customer_type, g in cm.groupby("customer_type"):
        n = len(g)
        for st in stations:
            rows.append(
                {
                    "customer_type": customer_type,
                    "station": st,
                    "n_customers": n,
                    "n_visiting_station": int(g[f"visit_{st}"].sum()),
                    "visit_probability": float(g[f"visit_{st}"].mean()),
                }
            )

    return pd.DataFrame(rows)


def fit_candidates(x: np.ndarray) -> list[dict[str, Any]]:
    # x must be strictly positive
    fits = []
    candidates = {
        "exponential": stats.expon,
        "gamma": stats.gamma,
        "lognormal": stats.lognorm,
        "weibull": stats.weibull_min,
    }
    n = len(x)
    for name, dist in candidates.items():
        try:
            params = dist.fit(x, floc=0)
            loglik = float(np.sum(dist.logpdf(x, *params)))
            k = len(params)
            aic = 2 * k - 2 * loglik
            bic = k * np.log(n) - 2 * loglik
            ks_stat, ks_p = stats.kstest(x, dist.cdf, args=params)
            fits.append(
                {
                    "distribution": name,
                    "n": n,
                    "params": repr(tuple(float(p) for p in params)),
                    "loglik": loglik,
                    "aic": float(aic),
                    "bic": float(bic),
                    "ks_stat": float(ks_stat),
                    "ks_pvalue": float(ks_p),
                }
            )
        except Exception:
            fits.append(
                {
                    "distribution": name,
                    "n": n,
                    "params": "",
                    "loglik": np.nan,
                    "aic": np.nan,
                    "bic": np.nan,
                    "ks_stat": np.nan,
                    "ks_pvalue": np.nan,
                }
            )
    return fits


def fit_needed_splits(
    station_data: pd.DataFrame, split_df: pd.DataFrame, min_fit_n: int = 25
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    # if there is nothing to split
    if split_df.empty:
        return pd.DataFrame(rows)

    # loop over row in split_df
    for _, split_row in split_df.iterrows():
        # skip if split not recommended
        if not split_row["split_recommended"]:
            continue

        station = split_row["station"]
        split_variable = split_row["split_variable"]
        base = station_data[station_data["station"] == station].copy()

        # data split into groups based on chosen split variable
        for subgroup, g in base.groupby(split_variable):
            x = g["service_time_minutes"].dropna().values

            if len(x) < min_fit_n:
                # since there's too little observations emphirical sampling is recommended
                rows.append(
                    {
                        "station": station,
                        "split_variable": split_variable,
                        "subgroup": subgroup,
                        "n": len(x),
                        "recommended_model": "empirical",
                        "reason": "sample_size_too_small",
                        "best_aic": np.nan,
                        "best_ks_pvalue": np.nan,
                        "params": "",
                    }
                )
                continue

            fits = pd.DataFrame(fit_candidates(x))
            # drop fitting fails
            fits = fits.dropna(subset=["aic"])

            # no fits were applicable
            if fits.empty:
                rows.append(
                    {
                        "station": station,
                        "split_variable": split_variable,
                        "subgroup": subgroup,
                        "n": len(x),
                        "recommended_model": "empirical",
                        "reason": "fit_failed",
                        "best_aic": np.nan,
                        "best_ks_pvalue": np.nan,
                        "params": "",
                    }
                )
                continue

            best = fits.sort_values("aic").iloc[0]

            if best["ks_pvalue"] < 0.01:
                model = "empirical"
                reason = "best_fit_rejected_by_ks"
            else:
                model = best["distribution"]
                reason = "best_aic_and_not_rejected"

            rows.append(
                {
                    "station": station,
                    "split_variable": split_variable,
                    "subgroup": subgroup,
                    "n": len(x),
                    "recommended_model": model,
                    "reason": reason,
                    "best_aic": float(best["aic"]),
                    "best_ks_pvalue": float(best["ks_pvalue"]),
                    "params": best["params"],
                }
            )

    return pd.DataFrame(rows)


def draw_fit_plots(station: str, x: np.ndarray, fits_df: pd.DataFrame) -> None:
    if len(x) < 5:
        return
    x_grid = np.linspace(np.min(x), np.quantile(x, 0.99), 300)
    plt.figure(figsize=(10, 6))
    sns.histplot(x, bins=25, stat="density", alpha=0.35, color="steelblue")
    for _, row in fits_df.iterrows():
        if pd.isna(row["aic"]):
            continue
        dist_name = row["distribution"]
        params = eval(row["params"])
        dist = {
            "exponential": stats.expon,
            "gamma": stats.gamma,
            "lognormal": stats.lognorm,
            "weibull": stats.weibull_min,
        }[dist_name]
        y = dist.pdf(x_grid, *params)
        plt.plot(x_grid, y, label=dist_name)
    plt.title(f"{station}: service-time histogram and fitted PDFs")
    plt.xlabel("Service time (minutes)")
    plt.ylabel("Density")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / f"service_fit_{station.lower()}.png", dpi=140)
    plt.close()

    # QQ plot vs best by AIC
    best = fits_df.dropna(subset=["aic"]).sort_values("aic").head(1)
    if best.empty:
        return
    best = best.iloc[0]
    params = eval(best["params"])
    dist = {
        "exponential": stats.expon,
        "gamma": stats.gamma,
        "lognormal": stats.lognorm,
        "weibull": stats.weibull_min,
    }[best["distribution"]]
    probs = (np.arange(1, len(x) + 1) - 0.5) / len(x)
    theo = dist.ppf(probs, *params)
    obs = np.sort(x)
    plt.figure(figsize=(6, 6))
    plt.scatter(theo, obs, s=14, alpha=0.7)
    low, high = min(theo.min(), obs.min()), max(theo.max(), obs.max())
    plt.plot([low, high], [low, high], "r--", linewidth=1)
    plt.title(f"{station}: QQ plot vs {best['distribution']}")
    plt.xlabel("Theoretical quantiles")
    plt.ylabel("Observed quantiles")
    plt.tight_layout()
    plt.savefig(FIG_DIR / f"qq_{station.lower()}.png", dpi=140)
    plt.close()


@dataclass
class ArrivalModelSummary:
    model_name: str
    loglik: float
    aic: float
    bic: float
    notes: str


def main() -> None:
    ensure_dirs()
    cm = pd.read_csv(CLEAN_DIR / "customer_master.csv")
    sv = pd.read_csv(CLEAN_DIR / "station_visits.csv")

    cm = add_customer_types(cm)

    # Customer type summary.
    csum = (
        cm.groupby("customer_type")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    csum["proportion"] = csum["count"] / csum["count"].sum()
    csum.to_csv(TABLE_DIR / "customer_type_summary.csv", index=False)

    # Probability of visiting each station by customer type
    visit_prob_df = stations_visit(cm)
    visit_prob_df.to_csv(
        TABLE_DIR / "station_visit_probabilities_by_type.csv", index=False
    )

    # Graph - Probability of visiting each station by customer type
    plt.figure(figsize=(10, 5))
    sns.barplot(
        data=visit_prob_df, x="station", y="visit_probability", hue="customer_type"
    )
    plt.title("Probability of visiting each station by customer type")
    plt.xlabel("Station")
    plt.ylabel("Conditional probability")
    plt.ylim(0, 1)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "station_visit_probabilities_by_type.png", dpi=140)
    plt.close()

    # route pattern in the WRP
    route_summary = (
        cm.groupby("route_pattern")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    route_summary["proportion"] = route_summary["count"] / route_summary["count"].sum()
    route_summary.to_csv(TABLE_DIR / "route_pattern_summary.csv", index=False)

    # Data for the cases of abandonment/forgetting pass/priority/blocked entrance
    special_cases_summary = pd.DataFrame(
        {
            "metric": [
                "abandonment_rate",
                "forgot_pass_rate",
                "priority_rate",
                "blocked_rate",
                "special_case_rate",
            ],
            "value": [
                cm["abandoned_flag"].mean(),
                cm["forgot_pass_flag"].mean(),
                cm["priority_flag"].mean(),
                cm["blocked_flag"].mean(),
                cm["special_case_flag"].mean(),
            ],
        }
    )
    special_cases_summary.to_csv(TABLE_DIR / "special_case_summary.csv", index=False)

    # Build gate/entrance inferred service times from queue-arrival to entrance.
    cm["queue_arrival_min"] = cm["arrival_to_outside_queue"].apply(parse_hhmmss)
    cm["entrance_min"] = cm["entrance_time"].apply(parse_hhmmss)
    cm["gate_service_minutes"] = cm["entrance_min"] - cm["queue_arrival_min"]
    gate = cm[
        cm["gate_service_minutes"].notna()
        & (cm["gate_service_minutes"] > 0)
        & (cm["gate_service_minutes"] <= 180)
    ].copy()
    gate["station"] = "ENTRANCE_GATE"
    gate["service_time_minutes"] = gate["gate_service_minutes"]
    gate = gate[
        ["station", "service_time_minutes", "vehicle_size_clean", "customer_type"]
    ]

    # Internal stations.
    svi = sv.copy()
    svi = svi[svi["station"].isin(["FWPM", "DCDDGPCH", "GRWCTEGS", "REST"])]
    svi = svi[svi["service_time_minutes"].notna()]
    svi = svi[(svi["service_time_minutes"] > 0) & (svi["service_time_minutes"] <= 180)]
    svi = svi.merge(
        cm[["day", "source_file", "car_id", "vehicle_size_clean", "customer_type"]],
        on=["day", "source_file", "car_id"],
        how="left",
    )
    svi = svi[
        ["station", "service_time_minutes", "vehicle_size_clean", "customer_type"]
    ]
    station_data = pd.concat([gate, svi], ignore_index=True)

    # Service descriptive summary.
    ssum = (
        station_data.groupby("station")["service_time_minutes"]
        .agg(["count", "mean", "std", "median", "min", "max"])
        .reset_index()
        .rename(columns={"std": "sd"})
    )
    ssum.to_csv(TABLE_DIR / "service_time_summary.csv", index=False)

    # Fit comparison.
    fit_rows = []
    recommendation_rows = []
    for station in STATIONS:
        x = (
            station_data.loc[station_data["station"] == station, "service_time_minutes"]
            .dropna()
            .values
        )
        if len(x) < 15:
            recommendation_rows.append(
                {
                    "station": station,
                    "recommended_model": "empirical",
                    "reason": "sample_size_too_small",
                    "n": len(x),
                }
            )
            continue
        fits = pd.DataFrame(fit_candidates(x))
        fits["station"] = station
        fit_rows.append(fits)
        draw_fit_plots(station, x, fits)

        best = fits.dropna(subset=["aic"]).sort_values("aic").head(1).iloc[0]
        # If best KS p-value is very poor, recommend empirical fallback.
        if best["ks_pvalue"] < 0.05:
            model = "empirical"
            reason = "all_parametric_fits_rejected_by_ks_5pct"
        else:
            model = best["distribution"]
            reason = "best_aic_and_not_rejected_by_ks"
        recommendation_rows.append(
            {
                "station": station,
                "recommended_model": model,
                "reason": reason,
                "n": int(best["n"]),
                "best_aic": float(best["aic"]),
                "best_ks_pvalue": float(best["ks_pvalue"]),
            }
        )

    fit_df = pd.concat(fit_rows, ignore_index=True) if fit_rows else pd.DataFrame()
    fit_df.to_csv(TABLE_DIR / "distribution_fit_comparison.csv", index=False)

    rec_df = pd.DataFrame(recommendation_rows)
    rec_df.to_csv(TABLE_DIR / "recommended_service_models.csv", index=False)

    # Split checks by vehicle size and customer type.
    split_rows = []
    for station in STATIONS:
        base = station_data[station_data["station"] == station]
        if len(base) < 60:
            continue
        for split_col in ["vehicle_size_clean", "customer_type"]:
            grp = base.groupby(split_col)["service_time_minutes"]
            levels = grp.size()
            if levels.min() < 20 or len(levels) < 2:
                continue
            values = [g.values for _, g in grp]
            try:
                h_stat, pval = stats.kruskal(*values)
            except ValueError:
                continue
            split_rows.append(
                {
                    "station": station,
                    "split_variable": split_col,
                    "n_groups": len(levels),
                    "min_group_n": int(levels.min()),
                    "kruskal_pvalue": float(pval),
                    "split_recommended": bool(pval < 0.01),
                }
            )
    split_df = pd.DataFrame(split_rows)
    split_df.to_csv(TABLE_DIR / "service_time_split_evidence.csv", index=False)

    split_fit_df = fit_needed_splits(station_data, split_df)
    split_fit_df.to_csv(TABLE_DIR / "service_time_split_fits.csv", index=False)

    # Arrival process.
    arr = cm[["day", "arrival_to_outside_queue"]].copy()
    arr["arrival_min"] = arr["arrival_to_outside_queue"].apply(parse_hhmmss)
    arr = arr[arr["arrival_min"].notna()].copy()
    arr = arr.sort_values(["day", "arrival_min"])

    arr["interarrival_min"] = arr.groupby("day")["arrival_min"].diff()
    inter = arr["interarrival_min"].dropna()
    inter = inter[inter >= 0]

    # Homogeneous Poisson rate using pooled exposure over each day range.
    day_span = (
        arr.groupby("day")["arrival_min"].agg(["min", "max", "count"]).reset_index()
    )
    day_span["span_hours"] = (day_span["max"] - day_span["min"]) / 60.0
    total_exposure = day_span["span_hours"].sum()
    total_arrivals = len(arr)
    lambda_h = total_arrivals / total_exposure if total_exposure > 0 else np.nan

    # NHPP with 30-min intervals.
    interval = 30
    t0 = int(np.floor(arr["arrival_min"].min() / interval) * interval)
    t1 = int(np.ceil(arr["arrival_min"].max() / interval) * interval)
    bins = np.arange(t0, t1 + interval, interval)
    labels = [
        f"{int(b//60):02d}:{int(b%60):02d}-{int((b+interval)//60):02d}:{int((b+interval)%60):02d}"
        for b in bins[:-1]
    ]
    arr["interval"] = pd.cut(arr["arrival_min"], bins=bins, right=False, labels=labels)
    by_int = arr.groupby("interval", observed=False).size().reset_index(name="arrivals")
    n_days = arr["day"].nunique()
    by_int["interval_minutes"] = interval
    by_int["exposure_hours"] = n_days * interval / 60.0
    by_int["lambda_per_hour"] = by_int["arrivals"] / by_int["exposure_hours"]
    by_int.to_csv(TABLE_DIR / "arrival_rate_by_interval.csv", index=False)

    # Compare homogeneous vs NHPP via interval-count likelihood.
    counts = by_int["arrivals"].values.astype(float)
    exp_h = np.repeat(counts.mean(), len(counts))
    exp_nhpp = counts.copy()  # saturated by-interval MLE
    # Poisson log-likelihood sum (ignoring constants ln(k!))
    ll_h = float(np.sum(counts * np.log(np.clip(exp_h, 1e-12, None)) - exp_h))
    ll_n = float(np.sum(counts * np.log(np.clip(exp_nhpp, 1e-12, None)) - exp_nhpp))
    k_h, k_n = 1, len(counts)
    n_obs = len(counts)
    aic_h, bic_h = 2 * k_h - 2 * ll_h, k_h * np.log(n_obs) - 2 * ll_h
    aic_n, bic_n = 2 * k_n - 2 * ll_n, k_n * np.log(n_obs) - 2 * ll_n

    arr_model_rows = [
        ArrivalModelSummary(
            model_name="homogeneous_poisson",
            loglik=ll_h,
            aic=aic_h,
            bic=bic_h,
            notes=f"lambda={lambda_h:.3f} per hour",
        ).__dict__,
        ArrivalModelSummary(
            model_name="piecewise_constant_nhpp_30min",
            loglik=ll_n,
            aic=aic_n,
            bic=bic_n,
            notes="30-minute piecewise-constant interval rates",
        ).__dict__,
    ]
    arr_model_df = pd.DataFrame(arr_model_rows)
    arr_model_df.to_csv(TABLE_DIR / "arrival_process_summary.csv", index=False)

    # Figures for arrivals.
    plt.figure(figsize=(8, 5))
    sns.histplot(inter, bins=30, kde=True)
    plt.title("Interarrival times (queue arrivals only)")
    plt.xlabel("Interarrival (minutes)")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "arrival_interarrival_hist.png", dpi=140)
    plt.close()

    plt.figure(figsize=(9, 5))
    for day, g in arr.groupby("day"):
        g = g.sort_values("arrival_min")
        y = np.arange(1, len(g) + 1)
        plt.step(g["arrival_min"], y, where="post", label=day)
    plt.title("Cumulative arrivals by day")
    plt.xlabel("Minute of day")
    plt.ylabel("Cumulative arrivals")
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIG_DIR / "arrival_cumulative_by_day.png", dpi=140)
    plt.close()

    plt.figure(figsize=(10, 5))
    plt.plot(np.arange(len(by_int)), by_int["lambda_per_hour"], marker="o")
    plt.xticks(np.arange(len(labels)), labels, rotation=45, ha="right")
    plt.title("Estimated NHPP intensity by 30-min interval")
    plt.xlabel("Interval")
    plt.ylabel("Lambda per hour")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "arrival_lambda_piecewise.png", dpi=140)
    plt.close()

    # Consolidated report table
    recommended_arrival = (
        "piecewise_constant_nhpp_30min"
        if aic_n < aic_h and bic_n < bic_h
        else "homogeneous_poisson"
    )

    report_lines = [
        "# Statistical Summary for Queueing Parameterization",
        "",
        "## What Was Analyzed",
        "- Customer segmentation from vehicle size, route pattern, number of visited stations, and special-case flags.",
        "- Service-time distributions for entrance/gate (inferred) and internal stations (`FWPM`, `DCDDGPCH`, `GRWCTEGS`, `REST`).",
        "- Arrival process using queue-arrival times only (not entrance times).",
        "- Conditional station-visit probabilities for each customer type.",
        "- Route-pattern frequencies across customers.",
        "- Frequencies of special cases such as: abandonment, forgetting pass, priority, blocked entrance.",
        "- Where statistically justified, subgroup-specific service-time distributions were fitted by vehicle size or customer type.",
        "",
        "## What Was Chosen",
        f"- Customer types: `{', '.join(csum['customer_type'].tolist())}`.",
        "- Service models by station are listed in `output/tables/service_time_summary.csv` and `output/tables/distribution_fit_comparison.csv`.",
        f"- Arrival-process recommendation: `{recommended_arrival}`.",
        "",
        "## Why It Was Chosen",
        "- Segmentation is intentionally coarse to avoid sparse classes and to remain simulation-tractable.",
        "- Parametric service fits are selected by AIC with KS sanity checks; empirical fallback is used where fits are weak.",
        "- NHPP is preferred when time-of-day rate variation is large enough to improve both AIC and BIC versus homogeneous Poisson.",
        "",
        "## Uncertainty / Limitations",
        "- Gate service time is inferred as `entrance_time - queue_arrival`; this mixes true gate service with queue waiting and blocking effects.",
        "- Raw timestamp issues (missing arrivals/departures, impossible ordering, negative service durations) reduce fit confidence.",
        "- Some stations include repeated rows per customer; the analysis keeps valid positive durations rather than forcing deduplication.",
        "- With only a few observed days, arrival-rate seasonality/day-of-week effects are not identifiable.",
        "",
        "## Simulation-Ready Inputs",
        "- `output/tables/customer_type_summary.csv`: class probabilities for customer-type generation.",
        "- `output/tables/service_time_summary.csv`: descriptive station timing priors.",
        "- `output/tables/distribution_fit_comparison.csv`: candidate fit parameters and GOF metrics for each station.",
        "- `output/tables/arrival_rate_by_interval.csv`: piecewise NHPP rate table (lambda per hour by interval).",
        "- `output/tables/arrival_process_summary.csv`: model-level comparison and recommended arrival process.",
        "- `output/tables/service_time_split_fits.csv`: subgroup-specific fitted service models for stations where split evidence supports separate modelling.",
        "",
        "## Split-Fit Evidence",
    ]
    if split_df.empty:
        report_lines.append(
            "- No statistically meaningful split by vehicle size or customer type met both significance and minimum sample criteria."
        )
    else:
        for _, r in split_df.iterrows():
            report_lines.append(
                f"- {r['station']} split by {r['split_variable']}: p={r['kruskal_pvalue']:.4g}, min group n={r['min_group_n']}, split_recommended={bool(r['split_recommended'])}"
            )

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
