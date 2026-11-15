"""Download NYC yellow taxi trip records (one Parquet file per month) and the
taxi zone lookup table published by the NYC Taxi & Limousine Commission (TLC).

Files that are already on disk are skipped, so the script can be re-run safely.
Months that the TLC has not published yet are reported and skipped.
"""

import argparse
import time
from datetime import date
from pathlib import Path

import requests

BASE_URL = "https://d37ci6vzurychx.cloudfront.net"
DEFAULT_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
HEADERS = {"User-Agent": "nyc-congestion-pricing-pipeline/1.0"}


def month_range(start: str, end: str) -> list[str]:
    """Return every month between start and end (inclusive), formatted YYYY-MM."""
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    months = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def download(url: str, target: Path, attempts: int = 3) -> bool:
    """Download url to target. Return False if the file is not published (403/404)."""
    if target.exists():
        print(f"  already there: {target.name}")
        return True

    partial = target.with_name(target.name + ".part")
    for attempt in range(1, attempts + 1):
        try:
            with requests.get(url, headers=HEADERS, stream=True, timeout=120) as response:
                if response.status_code in (403, 404):
                    return False
                response.raise_for_status()
                with open(partial, "wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        file.write(chunk)
            break
        except requests.RequestException as error:
            if attempt == attempts:
                raise
            print(f"  attempt {attempt} failed ({error}), retrying...")
            time.sleep(10 * attempt)

    # Rename only once the download is complete, so a half-written file never
    # looks like a valid one.
    partial.replace(target)
    print(f"  downloaded: {target.name} ({target.stat().st_size / 1e6:.0f} MB)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2023-01", help="first month, YYYY-MM")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"), help="last month, YYYY-MM")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args()

    (args.raw_dir / "yellow").mkdir(parents=True, exist_ok=True)

    print("Taxi zone lookup")
    if not download(f"{BASE_URL}/misc/taxi_zone_lookup.csv", args.raw_dir / "taxi_zone_lookup.csv"):
        raise SystemExit("Error: the taxi zone lookup could not be found.")

    print(f"Yellow taxi trips, {args.start} to {args.end}")
    missing = []
    for month in month_range(args.start, args.end):
        name = f"yellow_tripdata_{month}.parquet"
        if not download(f"{BASE_URL}/trip-data/{name}", args.raw_dir / "yellow" / name):
            missing.append(month)

    if missing:
        print(f"Not published yet: {', '.join(missing)}")


if __name__ == "__main__":
    main()
