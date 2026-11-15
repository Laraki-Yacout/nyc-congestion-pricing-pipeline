"""Run the whole pipeline: get the data, build and test the dbt models, export the marts.

    python scripts/run_pipeline.py            # real TLC data (~3 GB download)
    python scripts/run_pipeline.py --sample   # small synthetic data, runs in a couple of minutes
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def step(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def run_python(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(ROOT / script), *args], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", action="store_true", help="use synthetic data instead of the real files")
    parser.add_argument("--start", default="2023-01", help="first month to download, YYYY-MM")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"), help="last month to download, YYYY-MM")
    parser.add_argument("--skip-download", action="store_true", help="reuse the files already on disk")
    parser.add_argument("--memory", default="4GB", help="memory limit for DuckDB, e.g. 4GB")
    args = parser.parse_args()

    data_dir = ROOT / "data" / ("sample" if args.sample else "")
    raw_dir = data_dir / "raw"
    export_dir = data_dir / "exports" if args.sample else ROOT / "exports"
    started = time.time()

    step("1/3 Data")
    if args.skip_download:
        print("Skipped, using the files already in", raw_dir)
    elif args.sample:
        run_python("scripts/make_sample_data.py", "--raw-dir", str(raw_dir))
    else:
        run_python("ingestion/download_tlc_data.py", "--start", args.start, "--end", args.end,
                   "--raw-dir", str(raw_dir))

    step("2/3 dbt build (models + tests)")
    os.environ["NYC_DUCKDB_PATH"] = str(data_dir / "warehouse.duckdb")
    os.environ["NYC_DUCKDB_MEMORY"] = args.memory
    # dbt is installed next to the Python interpreter (.venv/Scripts on Windows, .venv/bin elsewhere)
    dbt = shutil.which("dbt", path=str(Path(sys.executable).parent)) or "dbt"
    project_dir = str(ROOT / "transform")
    build = subprocess.run([
        dbt, "build",
        "--project-dir", project_dir,
        "--profiles-dir", project_dir,
        "--vars", f"{{raw_dir: '{raw_dir.as_posix()}'}}",
    ])
    if build.returncode != 0:
        raise SystemExit("dbt build failed, see the log above.")

    step("3/3 Export")
    run_python("scripts/export_marts.py", "--database", os.environ["NYC_DUCKDB_PATH"],
               "--out", str(export_dir))

    print(f"\nDone in {(time.time() - started) / 60:.1f} min. Exports are in {export_dir}")


if __name__ == "__main__":
    main()
