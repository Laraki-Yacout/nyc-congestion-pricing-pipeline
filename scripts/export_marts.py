"""Export the dbt marts to CSV (read by Power BI) and write the headline numbers to summary.json."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

TABLES = [
    "fct_trips_hourly",
    "fct_zone_monthly",
    "dim_zones",
    "dim_date",
    "mart_toll_effect",
    "mart_toll_effect_monthly",
    "mart_speed_by_hour",
    "mart_data_quality",
]


def export_table(con: duckdb.DuckDBPyConnection, table: str, out_dir: Path) -> int:
    # Round decimals so the CSV files stay small and readable.
    columns = con.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_name = ? order by ordinal_position", [table]
    ).fetchall()
    select = ", ".join(
        f"round({name}, 4) as {name}" if dtype == "DOUBLE" else name for name, dtype in columns
    )
    order = ", ".join(str(i + 1) for i in range(min(3, len(columns))))
    path = out_dir / f"{table}.csv"
    con.execute(f"copy (select {select} from {table} order by {order}) to '{path.as_posix()}' (header)")
    return con.execute(f"select count(*) from {table}").fetchone()[0]


def one(con: duckdb.DuckDBPyConnection, sql: str):
    row = con.execute(sql).fetchone()
    return row[0] if row else None


def effect(con: duckdb.DuckDBPyConnection, comparison: str, scope: str,
           segment: str = "within_zone", control: str | None = None):
    # control=None means the main control group (is_main_estimate)
    row = con.execute(
        "select speed_effect_pct, ci95_low_pct, ci95_high_pct, months_compared, is_significant "
        "from mart_toll_effect where comparison = ? and scope = ? and segment = ? "
        "and (control_group = ? or (cast(? as varchar) is null and is_main_estimate))",
        [comparison, scope, segment, control, control],
    ).fetchone()
    if row is None:
        return None
    return {
        "speed_effect_pct": round(row[0], 4),
        "ci95": [round(row[1], 4), round(row[2], 4)],
        "months_compared": row[3],
        "significant": row[4],
    }


def build_summary(con: duckdb.DuckDBPyConnection) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "first_month": str(one(con, "select min(file_month) from mart_data_quality"))[:7],
        "last_month": str(one(con, "select max(file_month) from mart_data_quality"))[:7],
        "raw_trips": one(con, "select sum(trips) from mart_data_quality"),
        "kept_trips": one(con, "select sum(trips) from mart_data_quality where status = 'kept'"),
        "crz_zones": one(con, "select count(*) from dim_zones where is_crz"),
        "cbd_fees_collected_usd": round(one(con, "select sum(cbd_fee) from fct_trips_hourly") or 0, 2),
        "speed_mph_within_zone": {
            str(year): round(speed, 2)
            for year, speed in con.execute(
                "select year(pickup_date), sum(distance_mi) / (sum(duration_min) / 60) "
                "from fct_trips_hourly where segment = 'within_zone' group by 1 order by 1"
            ).fetchall()
        },
        "main_control_group": one(con, "select any_value(control_group) from mart_toll_effect where is_main_estimate"),
        "effect_within_zone": {
            comparison: {scope: effect(con, comparison, scope)
                         for scope in ("all hours", "peak hours", "overnight hours")}
            for comparison in ("placebo: 2024 vs 2023", "2025 vs 2024", "2026 vs 2024",
                               "2025 vs 2024, trend-adjusted", "2026 vs 2024, trend-adjusted")
        },
        "effect_into_zone_2025": effect(con, "2025 vs 2024", "all hours", "into_zone"),
        "effect_out_of_zone_2025": effect(con, "2025 vs 2024", "all hours", "out_of_zone"),
        "robustness_within_zone_all_hours": {
            control: {comparison: effect(con, comparison, "all hours", "within_zone", control)
                      for comparison in ("placebo: 2024 vs 2023", "2025 vs 2024", "2026 vs 2024",
                                         "2025 vs 2024, trend-adjusted")}
            for (control,) in con.execute(
                "select distinct control_group from mart_toll_effect order by 1").fetchall()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(args.database), read_only=True)
    for table in TABLES:
        rows = export_table(con, table, args.out)
        print(f"  {table}.csv: {rows:,} rows")

    summary = build_summary(con)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("  summary.json")


if __name__ == "__main__":
    main()
