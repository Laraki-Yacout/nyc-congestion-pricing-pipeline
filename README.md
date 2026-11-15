# Did Manhattan's congestion toll speed up traffic? Using NYC taxis as traffic sensors

On 5 January 2025, New York became the first US city to charge drivers for entering its centre
(Manhattan south of 60th Street, $9 for most cars at peak time). The goal was simple: fewer cars, faster streets.

Yellow taxis only pay $0.75 per trip, so they kept driving through the zone. That makes them a great
natural sensor: if traffic really got lighter, taxis inside the zone should have become faster
**compared with taxis elsewhere in the city**. This project measures exactly that, on every yellow taxi
trip since 2023 (well over 100 million rows), with a pipeline that refreshes itself every month.

> Full results and the Power BI dashboard are added after the first complete run of the pipeline.

## How it works

```
NYC TLC monthly Parquet files ──> Python ingestion ──> DuckDB ──> dbt (clean, model, test) ──> CSV exports ──> Power BI
                                      └──────────── GitHub Actions, every month ────────────┘
```

- **Ingestion** (`ingestion/`): downloads the monthly files, skips what is already there, never leaves a half-written file.
- **Transformation** (`transform/`, dbt + DuckDB): DuckDB reads the Parquet files in place, dbt cleans the trips,
  tags each one by its relation to the toll zone, builds the marts and runs the data tests.
- **Automation** (`.github/workflows/pipeline.yml`): a smoke test on synthetic data on every push,
  and a full refresh on the real data on the 20th of each month, which commits the new exports.

## Method in short

- **Which zones are inside the toll area?** The TLC does not publish it, so I infer it from the data:
  since January 2025 every trip starting or ending in the zone pays the `cbd_congestion_fee`.
- **Difference-in-differences:** daily speed of trips within the zone divided by the speed of trips outside it,
  compared with the same calendar months of 2024. Anything that hits the whole city (weather, a general traffic trend) cancels out.
- **Placebo test:** the same comparison for 2024 vs 2023, when there was no toll, should give about 0.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (source .venv/bin/activate on Mac/Linux)
pip install -r requirements.txt
python scripts/run_pipeline.py --sample   # synthetic data, about a minute
python scripts/run_pipeline.py            # real data, ~3 GB download
```

## Data and licence

Trip records: [NYC Taxi & Limousine Commission](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page),
published as NYC Open Data, which can be used without restriction. This is a personal portfolio project, not affiliated with the TLC or the MTA.
