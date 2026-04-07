from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from customtypes import Customer

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output" / "cleaned"
REPORT_PATH = ROOT / "output" / "report_cleaning.md"

STATION_ORDER = ["QUEUE_OUTSIDE", "ENTRANCE", "FWPM", "DCDDGPCH", "GRWCTEGS", "REST"]
COMMENT_KEYWORDS = {
    "abandoned_flag": ["give up", "gave up", "left", "abandon", "abandoned"],
    "forgot_pass_flag": ["forgot city pass", "forgot pass", "city pass"],
    "priority_flag": ["bike", "foot", "priority", "mbike", "walking"],
    "blocked_flag": ["block", "blocked", "unblocked", "truck"],
}


def norm_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_sheet_name(sheet_name: str) -> str:
    raw = re.sub(r"\s+", " ", sheet_name.strip()).lower()
    if raw in {"main data sheet", "main"}:
        return "MAIN_DATA"
    if raw == "queue outside":
        return "QUEUE_OUTSIDE"
    if raw == "entrance":
        return "ENTRANCE"
    if raw.replace(" ", "") in {"fwpm1", "fwpm2"}:
        return "FWPM"
    if raw == "dcddgpch":
        return "DCDDGPCH"
    if raw == "grwctegs":
        return "GRWCTEGS"
    if raw in {"rest + exit", "rest+exit", "rest exit"}:
        return "REST"
    return re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")


def normalize_column_name(col: str) -> str:
    c = re.sub(r"\s+", " ", str(col).strip())
    c_lower = c.lower()
    mapping = {
        "car id": "car_id_raw",
        "car size": "vehicle_size_raw",
        "car size ": "vehicle_size_raw",
        "size": "vehicle_size_raw",
        "size ": "vehicle_size_raw",
        "arrival": "arrival_raw",
        "arrival ": "arrival_raw",
        "depature": "departure_raw",
        "departure": "departure_raw",
        "entrance time": "entrance_time_raw",
        "time gate is blocked": "gate_blocked_time_raw",
        "time gate is bloked": "gate_blocked_time_raw",
        "time gate is unblocked": "gate_unblocked_time_raw",
        "sojourn time": "sojourn_time_raw",
        "sojourn  time": "sojourn_time_raw",
        "service time": "service_time_raw",
        "waiting time(if customer has given up": "waiting_time_given_up_raw",
        "comments": "comments_raw",
        "ch ": "ch",
    }
    if c_lower in mapping:
        return mapping[c_lower]
    if c_lower.startswith("unnamed:"):
        return "unnamed"
    # Keep waste category columns as upper-case canonical names.
    if re.fullmatch(r"[A-Za-z]{1,3}", c):
        return c.upper()
    return re.sub(r"[^a-z0-9]+", "_", c_lower).strip("_")


def parse_time_to_minutes(value: Any) -> float | None:
    if pd.isna(value):
        return None

    # Handle native datetime/time
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return value.hour * 60 + value.minute + (getattr(value, "second", 0) / 60.0)

    s = norm_text(value)
    if not s:
        return None

    s = s.replace("::", ":")

    # HHMMSS numeric style, e.g. 130422 or "130422.0"
    if re.fullmatch(r"\d+(\.0+)?", s):
        n = s.split(".")[0]
        if len(n) == 6:
            hh, mm, ss = int(n[:2]), int(n[2:4]), int(n[4:6])
            if 0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60:
                return hh * 60 + mm + ss / 60.0
        # Excel fractional day as numeric string
        try:
            fv = float(s)
            if 0 <= fv <= 1:
                return fv * 24 * 60
        except ValueError:
            pass

    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", s):
        parts = s.split(":")
        hh, mm = int(parts[0]), int(parts[1])
        ss = int(parts[2]) if len(parts) == 3 else 0
        if 0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60:
            return hh * 60 + mm + ss / 60.0

    return None


def minutes_to_hhmmss(minutes: float | None) -> str:
    if minutes is None or pd.isna(minutes):
        return ""
    total_seconds = int(round(minutes * 60))
    hh = (total_seconds // 3600) % 24
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def normalize_car_id(value: Any) -> str:
    car_id = norm_text(value).upper()
    car_id = re.sub(r"\s+", "", car_id)
    return car_id


def is_valid_car_id(car_id: str) -> bool:
    if not car_id:
        return False
    if car_id in {"CARID", "CAR", "NAN"}:
        return False
    return bool(re.search(r"[A-Z0-9]", car_id))


def collect_comment_flags(text: str) -> dict[str, int]:
    low = text.lower()
    out: dict[str, int] = {}
    for flag, words in COMMENT_KEYWORDS.items():
        out[flag] = int(any(w in low for w in words))
    return out


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    workbook_sheet_map_rows: list[dict[str, Any]] = []
    column_dict_rows: list[dict[str, Any]] = []
    station_visit_rows: list[dict[str, Any]] = []

    # Aggregators by customer key.
    customer: dict[tuple[str, str, str], dict[str, Any]] = {}
    quality_issues: list[dict[str, Any]] = []

    xlsx_files = sorted(DATA_DIR.glob("*.xlsx"))
    if not xlsx_files:
        raise FileNotFoundError(f"No .xlsx files found in {DATA_DIR}")

    for wb_path in xlsx_files:
        source_file = wb_path.name
        day = source_file[:8]
        xls = pd.ExcelFile(wb_path)
        for sheet in xls.sheet_names:
            logical_sheet = normalize_sheet_name(sheet)
            df = pd.read_excel(wb_path, sheet_name=sheet)
            raw_cols = list(df.columns)

            norm_cols = [normalize_column_name(c) for c in raw_cols]
            df.columns = norm_cols
            workbook_sheet_map_rows.append(
                {
                    "source_file": source_file,
                    "day": day,
                    "sheet_name_raw": sheet,
                    "sheet_name_normalized": logical_sheet,
                    "n_rows_raw": len(df),
                    "n_cols_raw": len(raw_cols),
                }
            )
            for raw_col, norm_col in zip(raw_cols, norm_cols):
                column_dict_rows.append(
                    {
                        "source_file": source_file,
                        "sheet_name_raw": sheet,
                        "column_name_raw": raw_col,
                        "column_name_standardized": norm_col,
                    }
                )

            car_col = "car_id_raw" if "car_id_raw" in df.columns else None
            if not car_col:
                continue

            for _, row in df.iterrows():
                car_id = normalize_car_id(row.get("car_id_raw"))
                if not is_valid_car_id(car_id):
                    continue

                key = (day, source_file, car_id)
                if key not in customer:
                    customer[key] = {
                        "day": day,
                        "source_file": source_file,
                        "car_id": car_id,
                        "vehicle_size": "",
                        "arrival_to_outside_queue": None,
                        "entrance_time": None,
                        "departure_from_wrp": None,
                        "route_pattern": "",
                        "stations_visited": set(),
                        "n_stations": 0,
                        "abandoned_flag": 0,
                        "forgot_pass_flag": 0,
                        "priority_flag": 0,
                        "blocked_flag": 0,
                        "notes_comments_merged": [],
                    }

                c = customer[key]
                vehicle_size = norm_text(row.get("vehicle_size_raw"))
                if vehicle_size and not c["vehicle_size"]:
                    c["vehicle_size"] = vehicle_size.upper()

                comments = norm_text(row.get("comments_raw"))
                if comments:
                    c["notes_comments_merged"].append(f"{logical_sheet}: {comments}")
                    flags = collect_comment_flags(comments)
                    for flag, value in flags.items():
                        c[flag] = max(c[flag], value)

                # Extract event times from specific logical sheets.
                if logical_sheet == "QUEUE_OUTSIDE":
                    t = parse_time_to_minutes(row.get("arrival_raw"))
                    if c["arrival_to_outside_queue"] is None and t is not None:
                        c["arrival_to_outside_queue"] = t
                    dep = parse_time_to_minutes(row.get("departure_raw"))
                    if dep is not None and comments:
                        c["abandoned_flag"] = 1

                elif logical_sheet == "ENTRANCE":
                    t = parse_time_to_minutes(row.get("entrance_time_raw"))
                    if c["entrance_time"] is None and t is not None:
                        c["entrance_time"] = t
                    gate_blocked = norm_text(row.get("gate_blocked_time_raw"))
                    gate_unblocked = norm_text(row.get("gate_unblocked_time_raw"))
                    gate_note = " ".join(x for x in [gate_blocked, gate_unblocked] if x)
                    if gate_note:
                        flags = collect_comment_flags(gate_note)
                        for flag, value in flags.items():
                            c[flag] = max(c[flag], value)

                elif logical_sheet == "MAIN_DATA":
                    arr = parse_time_to_minutes(row.get("arrival_raw"))
                    dep = parse_time_to_minutes(row.get("departure_raw"))
                    if c["entrance_time"] is None and arr is not None:
                        c["entrance_time"] = arr
                    if c["departure_from_wrp"] is None and dep is not None:
                        c["departure_from_wrp"] = dep

                # Station-level rows (exclude queue/main/entrance from visits table).
                if logical_sheet in {"FWPM", "DCDDGPCH", "GRWCTEGS", "REST"}:
                    arr = parse_time_to_minutes(row.get("arrival_raw"))
                    dep = parse_time_to_minutes(row.get("departure_raw"))
                    waste_cols = [
                        cc
                        for cc in df.columns
                        if re.fullmatch(r"[A-Z]{1,3}", str(cc))
                        and cc not in {"CAR", "ID"}
                    ]
                    active_waste = []
                    for wc in waste_cols:
                        val = row.get(wc)
                        if pd.isna(val):
                            continue
                        sval = norm_text(val).upper()
                        if sval in {"1", "X"}:
                            active_waste.append(wc)
                        elif wc == sval:
                            # Some files place letter-codes; preserve this as evidence.
                            active_waste.append(wc)
                        elif isinstance(val, (int, float)) and float(val) > 0:
                            active_waste.append(wc)

                    row_quality_issues = []
                    if arr is None:
                        row_quality_issues.append("missing_arrival")
                    if dep is None:
                        row_quality_issues.append("missing_departure")
                    if arr is not None and dep is not None and dep < arr:
                        row_quality_issues.append("departure_before_arrival")

                    station_visit_rows.append(
                        {
                            "day": day,
                            "source_file": source_file,
                            "car_id": car_id,
                            "station": logical_sheet,
                            "arrival_time": minutes_to_hhmmss(arr),
                            "departure_time": minutes_to_hhmmss(dep),
                            "service_time_minutes": (
                                round(dep - arr, 3)
                                if arr is not None and dep is not None
                                else None
                            ),
                            "waste_types": "|".join(sorted(set(active_waste))),
                            "comments": comments,
                            "row_quality_flag": (
                                "|".join(row_quality_issues)
                                if row_quality_issues
                                else "ok"
                            ),
                            "arrival_minutes": arr,
                            "departure_minutes": dep,
                        }
                    )
                    c["stations_visited"].add(logical_sheet)

    # Finalize customer records.
    customer_rows: list[Customer] = []
    station_df = pd.DataFrame(station_visit_rows)
    for key, c in customer.items():
        day, source_file, car_id = key
        visited_ordered = [s for s in STATION_ORDER if s in c["stations_visited"]]
        c["n_stations"] = len(visited_ordered)
        c["stations_visited"] = "|".join(visited_ordered)
        c["route_pattern"] = "->".join(visited_ordered) if visited_ordered else ""
        c["notes_comments_merged"] = " || ".join(c["notes_comments_merged"])

        # Missing critical fields.
        if c["arrival_to_outside_queue"] is None:
            quality_issues.append(
                {
                    "issue_type": "missing_queue_arrival",
                    "severity": "high",
                    "day": day,
                    "source_file": source_file,
                    "car_id": car_id,
                    "station": "QUEUE_OUTSIDE",
                    "details": "No queue-outside arrival timestamp found",
                }
            )
        if c["entrance_time"] is None:
            quality_issues.append(
                {
                    "issue_type": "missing_entrance_time",
                    "severity": "high",
                    "day": day,
                    "source_file": source_file,
                    "car_id": car_id,
                    "station": "ENTRANCE",
                    "details": "No entrance timestamp found",
                }
            )
        if c["departure_from_wrp"] is None:
            quality_issues.append(
                {
                    "issue_type": "missing_exit_departure",
                    "severity": "high",
                    "day": day,
                    "source_file": source_file,
                    "car_id": car_id,
                    "station": "REST/MAIN_DATA",
                    "details": "No WRP departure timestamp found",
                }
            )

        # Routing order and timestamp consistency checks using station visits.
        cust_visits = station_df[
            (station_df["day"] == day)
            & (station_df["source_file"] == source_file)
            & (station_df["car_id"] == car_id)
        ].copy()
        if not cust_visits.empty:
            first_arrivals = {}
            for st in ["FWPM", "DCDDGPCH", "GRWCTEGS", "REST"]:
                st_rows = cust_visits[cust_visits["station"] == st]
                vals = [v for v in st_rows["arrival_minutes"].tolist() if pd.notna(v)]
                first_arrivals[st] = min(vals) if vals else None

            seq = [
                st
                for st in ["FWPM", "DCDDGPCH", "GRWCTEGS", "REST"]
                if first_arrivals[st] is not None
            ]
            for i in range(1, len(seq)):
                prev_st, curr_st = seq[i - 1], seq[i]
                prev_val = first_arrivals[prev_st]
                curr_val = first_arrivals[curr_st]
                if prev_val is None or curr_val is None:
                    continue
                if curr_val < prev_val:
                    quality_issues.append(
                        {
                            "issue_type": "impossible_routing_order",
                            "severity": "high",
                            "day": day,
                            "source_file": source_file,
                            "car_id": car_id,
                            "station": f"{prev_st}->{curr_st}",
                            "details": "Observed station arrival order violates expected process flow",
                        }
                    )
                    break

            bad_rows = cust_visits[
                (cust_visits["arrival_minutes"].notna())
                & (cust_visits["departure_minutes"].notna())
                & (cust_visits["departure_minutes"] < cust_visits["arrival_minutes"])
            ]
            if not bad_rows.empty:
                quality_issues.append(
                    {
                        "issue_type": "inconsistent_timestamps",
                        "severity": "high",
                        "day": day,
                        "source_file": source_file,
                        "car_id": car_id,
                        "station": "station_visits",
                        "details": f"{len(bad_rows)} visit rows have departure earlier than arrival",
                    }
                )

        # Comment-based flags as quality issues.
        for flag_name in [
            "abandoned_flag",
            "forgot_pass_flag",
            "priority_flag",
            "blocked_flag",
        ]:
            if c.get(flag_name, 0) == 1:
                quality_issues.append(
                    {
                        "issue_type": flag_name.replace("_flag", "_comment_flag"),
                        "severity": "medium",
                        "day": day,
                        "source_file": source_file,
                        "car_id": car_id,
                        "station": "comments",
                        "details": "Keyword-based flag triggered from comments/gate notes",
                    }
                )

        customer_rows.append(
            Customer(
                day=day,
                source_file=source_file,
                car_id=car_id,
                vehicle_size=c["vehicle_size"],
                arrival_to_outside_queue=minutes_to_hhmmss(
                    c["arrival_to_outside_queue"]
                ),
                entrance_time=minutes_to_hhmmss(c["entrance_time"]),
                departure_from_WRP=minutes_to_hhmmss(c["departure_from_wrp"]),
                route_pattern=c["route_pattern"],
                stations_visited=c["stations_visited"],
                n_stations=c["n_stations"],
                abandoned_flag=c["abandoned_flag"],
                forgot_pass_flag=c["forgot_pass_flag"],
                priority_flag=c["priority_flag"],
                blocked_flag=c["blocked_flag"],
                notes_comments_merged=c["notes_comments_merged"],
            )
        )

    # Write outputs.
    workbook_sheet_df = pd.DataFrame(workbook_sheet_map_rows).sort_values(
        ["source_file", "sheet_name_raw"]
    )
    customer_df = pd.DataFrame([c.to_row() for c in customer_rows]).sort_values(
        ["day", "car_id"]
    )
    station_out_df = pd.DataFrame(station_visit_rows).drop(
        columns=["arrival_minutes", "departure_minutes"]
    )
    station_out_df = station_out_df.sort_values(
        ["day", "car_id", "station", "arrival_time"]
    )
    quality_df = pd.DataFrame(quality_issues).sort_values(
        ["severity", "day", "car_id", "issue_type"]
    )
    column_dict_df = (
        pd.DataFrame(column_dict_rows)
        .drop_duplicates()
        .sort_values(["source_file", "sheet_name_raw", "column_name_raw"])
    )

    workbook_sheet_df.to_csv(OUTPUT_DIR / "workbook_sheet_map.csv", index=False)
    customer_df.to_csv(OUTPUT_DIR / "customer_master.csv", index=False)
    station_out_df.to_csv(OUTPUT_DIR / "station_visits.csv", index=False)
    quality_df.to_csv(OUTPUT_DIR / "data_quality_issues.csv", index=False)
    column_dict_df.to_csv(OUTPUT_DIR / "column_dictionary.csv", index=False)

    # Report file.
    top_issues = (
        quality_df.groupby("issue_type", dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    report_lines = [
        "# Data Cleaning Report",
        "",
        "## Scope",
        "- Processed all `.xlsx` files in `data/`.",
        "- Constructed customer-level and station-visit-level master tables.",
        "- Preserved comments and created keyword-based event flags.",
        "",
        "## Inferred Schema",
        "",
        "### customer_master.csv",
        ", ".join(customer_df.columns.tolist()),
        "",
        "### station_visits.csv",
        ", ".join(station_out_df.columns.tolist()),
        "",
        "### data_quality_issues.csv",
        ", ".join(
            quality_df.columns.tolist()
            if not quality_df.empty
            else [
                "issue_type",
                "severity",
                "day",
                "source_file",
                "car_id",
                "station",
                "details",
            ]
        ),
        "",
        "## Top Data-Quality Issues",
    ]
    if top_issues.empty:
        report_lines.append("- No issues detected by current rules.")
    else:
        for _, r in top_issues.head(10).iterrows():
            report_lines.append(f"- {r['issue_type']}: {int(r['count'])}")

    report_lines += [
        "",
        "## Assumptions",
        "- `FWPM1` and `FWPM2` (and spacing variants) are merged to logical station `FWPM`.",
        "- Time parsing accepts Excel time objects, `HH:MM[:SS]`, `HHMMSS`, and fixes `::` typo in times.",
        "- First valid timestamp per customer-field is kept when duplicates exist.",
        "- Station rows with missing/invalid arrivals or departures are retained and marked in `row_quality_flag`.",
        "- Waste type columns are interpreted as active if value is `1`, `X`, same letter code, or positive numeric.",
        "- Queue/entrance/main rows can populate customer-level milestones even when station sheets are incomplete.",
        "- Comment flags are keyword-based and intentionally sensitive to avoid dropping potential anomalies.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
