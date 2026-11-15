"""Generate a small synthetic dataset that mimics the TLC files (same file names,
same column names, same schema changes over the years).

It lets me run the whole pipeline in a couple of minutes without downloading
the real data (~3 GB), and it is what the CI smoke test runs on.
The synthetic data contains a known effect (taxis inside the zone get faster
after 5 January 2025), so the analysis can be checked against a known answer.
"""

import argparse
from pathlib import Path

import duckdb

N_ZONES = 263
CRZ_ZONES = 40  # zones 1..40 play the role of the Congestion Relief Zone


def month_range(start: str, end: str) -> list[str]:
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    months = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def write_zones(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    con.execute(f"""
        copy (
            select
                i as LocationID,
                case
                    when i <= 69 then 'Manhattan'
                    when i <= 140 then 'Brooklyn'
                    when i <= 200 then 'Queens'
                    when i <= 240 then 'Bronx'
                    when i <= {N_ZONES} then 'Staten Island'
                    when i = 264 then 'Unknown'
                    else 'N/A'
                end as Borough,
                case when i <= {N_ZONES} then 'Sample zone ' || i
                     when i = 264 then 'N/A' else 'Outside of NYC' end as Zone,
                case when i <= 69 then 'Yellow Zone' when i <= {N_ZONES} then 'Boro Zone'
                     else 'N/A' end as service_zone
            from range(1, 266) t(i)
        ) to '{path.as_posix()}' (header, delimiter ',')
    """)


def write_month(con: duckdb.DuckDBPyConnection, month: str, trips: int, path: Path) -> None:
    year = int(month[:4])
    # The real files changed over time: 'airport_fee' became 'Airport_fee' in 2024,
    # and 'cbd_congestion_fee' only exists from 2025 on.
    airport_col = "airport_fee" if year <= 2023 else "Airport_fee"
    cbd_col = ", cbd_fee::double as cbd_congestion_fee" if year >= 2025 else ""

    con.execute(f"""
        copy (
            with trips as (
                select
                    timestamp '{month}-01' + to_seconds(cast(
                        random() * date_diff('second', date '{month}-01',
                                             date '{month}-01' + interval 1 month) as bigint)
                    ) as pickup_at,
                    case when random() < 0.6 then 1 + cast(floor(random() * {CRZ_ZONES}) as int)
                         else {CRZ_ZONES} + 1 + cast(floor(random() * ({N_ZONES} - {CRZ_ZONES})) as int)
                    end as pu,
                    random() as r_do, random() as r_zone, random() as r_dist,
                    random() as r_noise, random() as r_tip, random() as r_bad
                from range({trips})
            ),
            located as (
                select *,
                    case when pu <= {CRZ_ZONES} and r_do < 0.65
                            then 1 + cast(floor(r_zone * {CRZ_ZONES}) as int)
                         else 1 + cast(floor(r_zone * {N_ZONES}) as int)
                    end as do_zone
                from trips
            ),
            shaped as (
                select *,
                    pu <= {CRZ_ZONES} as pu_crz,
                    do_zone <= {CRZ_ZONES} as do_crz,
                    ((isodow(pickup_at) <= 5 and hour(pickup_at) between 5 and 20)
                      or (isodow(pickup_at) >= 6 and hour(pickup_at) between 9 and 20)) as peak,
                    pickup_at >= timestamp '2025-01-05' as post
                from located
            ),
            moving as (
                select *,
                    case when pu_crz and do_crz then 0.5 + r_dist * 2.5 else 1 + r_dist * 11 end as dist,
                    -- base speed (mph) by trip type, faster at night, slight common trend
                    (case when pu_crz and do_crz then 6.5 when pu_crz or do_crz then 9 else 13 end)
                    * (case when peak then 1 else 1.4 end)
                    * (1 - 0.01 * ({year} - 2023))
                    -- the planted effect: faster inside the zone after the toll starts
                    * (case when not post then 1
                            when pu_crz and do_crz then (case when peak then 1.10 else 1.04 end)
                            when pu_crz or do_crz then 1.05
                            else 1 end) as speed
                from shaped
            ),
            priced as (
                select *,
                    dist / speed * 60 * (0.85 + 0.3 * r_noise) as minutes,
                    case when post and (pu_crz or do_crz) then 0.75 else 0 end as cbd_fee
                from moving
            )
            select
                cast(1 + (r_noise > 0.5)::int as int) as VendorID,
                case when r_bad < 0.003 then pickup_at - interval 15 year else pickup_at end
                    as tpep_pickup_datetime,
                pickup_at + to_seconds(cast(minutes * 60 as bigint)) as tpep_dropoff_datetime,
                cast(1 + floor(r_tip * 3) as bigint) as passenger_count,
                case when r_bad between 0.003 and 0.013 then 0 else round(dist, 2) end
                    as trip_distance,
                cast(1 as bigint) as RatecodeID,
                'N' as store_and_fwd_flag,
                case when r_bad between 0.013 and 0.018 then 264 else pu end as PULocationID,
                do_zone as DOLocationID,
                cast(1 + (r_tip < 0.3)::int as bigint) as payment_type,
                case when r_bad between 0.018 and 0.023 then -5.0
                     else round(3 + 2.8 * dist + 0.7 * minutes, 2) end as fare_amount,
                1.0::double as extra, 0.5::double as mta_tax,
                round(r_tip * 4, 2) as tip_amount, 0.0::double as tolls_amount,
                1.0::double as improvement_surcharge,
                round(3 + 2.8 * dist + 0.7 * minutes + 2.5 + r_tip * 4 + cbd_fee, 2) as total_amount,
                2.5::double as congestion_surcharge,
                0.0::double as {airport_col}
                {cbd_col}
            from priced
        ) to '{path.as_posix()}' (format parquet)
    """)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--start", default="2023-01")
    parser.add_argument("--end", default="2026-03")
    parser.add_argument("--trips-per-month", type=int, default=20_000)
    args = parser.parse_args()

    (args.raw_dir / "yellow").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("select setseed(0.42)")

    write_zones(con, args.raw_dir / "taxi_zone_lookup.csv")
    months = month_range(args.start, args.end)
    for month in months:
        write_month(con, month, args.trips_per_month,
                    args.raw_dir / "yellow" / f"yellow_tripdata_{month}.parquet")
    print(f"Synthetic data: {len(months)} months x {args.trips_per_month} trips in {args.raw_dir}")


if __name__ == "__main__":
    main()
