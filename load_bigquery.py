"""
load_bigquery.py — Load all MallPulse CSVs into BigQuery mallpulse_core dataset.

Usage (with venv active):
    python load_bigquery.py

Requires: gcloud application-default credentials (run `gcloud auth application-default login`)
"""

import pandas as pd
from pathlib import Path
from google.cloud import bigquery

PROJECT   = "mallpulse-hackathon"
DATASET   = "mallpulse_core"
DATA      = Path("data")

# Schema overrides for columns that need explicit types
# (pandas infers bool as BOOL fine; dates need TIMESTAMP → DATE override)
TABLE_SCHEMAS = {
    "dim_date": [
        bigquery.SchemaField("date",         "DATE"),
        bigquery.SchemaField("day_of_week",  "STRING"),
        bigquery.SchemaField("is_weekend",   "BOOL"),
        bigquery.SchemaField("is_holiday",   "BOOL"),
        bigquery.SchemaField("holiday_name", "STRING"),
        bigquery.SchemaField("week_of_year", "INTEGER"),
        bigquery.SchemaField("month",        "INTEGER"),
        bigquery.SchemaField("quarter",      "INTEGER"),
        bigquery.SchemaField("year",         "INTEGER"),
    ],
    "dim_lease": [
        bigquery.SchemaField("tenant_id",          "STRING"),
        bigquery.SchemaField("lease_start_date",   "DATE"),
        bigquery.SchemaField("lease_end_date",     "DATE"),
        bigquery.SchemaField("monthly_base_rent",  "FLOAT64"),
        bigquery.SchemaField("rent_pct_of_sales",  "FLOAT64"),
    ],
    "fact_transactions": [
        bigquery.SchemaField("invoice_no",      "STRING"),
        bigquery.SchemaField("tenant_id",       "STRING"),
        bigquery.SchemaField("mall_id",         "STRING"),
        bigquery.SchemaField("customer_id",     "STRING"),
        bigquery.SchemaField("date",            "DATE"),
        bigquery.SchemaField("category",        "STRING"),
        bigquery.SchemaField("quantity",        "INTEGER"),
        bigquery.SchemaField("unit_price",      "FLOAT64"),
        bigquery.SchemaField("total_amount",    "FLOAT64"),
        bigquery.SchemaField("payment_method",  "STRING"),
    ],
    "fact_weather": [
        bigquery.SchemaField("mall_id",           "STRING"),
        bigquery.SchemaField("date",              "DATE"),
        bigquery.SchemaField("temperature_c",     "FLOAT64"),
        bigquery.SchemaField("precipitation_mm",  "FLOAT64"),
        bigquery.SchemaField("weather_code",      "INTEGER"),
    ],
    "fact_foot_traffic": [
        bigquery.SchemaField("mall_id",           "STRING"),
        bigquery.SchemaField("date",              "DATE"),
        bigquery.SchemaField("hour",              "INTEGER"),
        bigquery.SchemaField("estimated_visits",  "INTEGER"),
    ],
    "dim_customer": [
        bigquery.SchemaField("customer_id",   "STRING"),
        bigquery.SchemaField("gender",        "STRING"),
        bigquery.SchemaField("age_band",      "STRING"),
        bigquery.SchemaField("loyalty_tier",  "STRING"),
    ],
}

TABLES = [
    "dim_mall",
    "dim_tenant",
    "dim_lease",
    "dim_date",
    "dim_customer",
    "fact_transactions",
    "fact_weather",
    "fact_foot_traffic",
]

client = bigquery.Client(project=PROJECT)
dataset_ref = f"{PROJECT}.{DATASET}"

total_rows = 0
for name in TABLES:
    csv_path = DATA / f"{name}.csv"
    if not csv_path.exists():
        print(f"  SKIP {name} — CSV not found")
        continue

    table_ref = f"{dataset_ref}.{name}"
    schema    = TABLE_SCHEMAS.get(name)

    job_config = bigquery.LoadJobConfig(
        source_format        = bigquery.SourceFormat.CSV,
        skip_leading_rows    = 1,
        autodetect           = schema is None,
        schema               = schema,
        write_disposition    = bigquery.WriteDisposition.WRITE_TRUNCATE,
        null_marker          = "",
    )

    print(f"  Loading {name}...", end=" ", flush=True)
    with open(csv_path, "rb") as f:
        job = client.load_table_from_file(f, table_ref, job_config=job_config)
    job.result()  # wait

    table  = client.get_table(table_ref)
    total_rows += table.num_rows
    print(f"{table.num_rows:,} rows")

print(f"\nAll tables loaded. Total rows: {total_rows:,}")

# ── Create aggregate views ────────────────────────────────────────────────────
print("\nCreating aggregate tables...")

AGG_SQLS = {
    "agg_tenant_daily": f"""
        CREATE OR REPLACE TABLE `{dataset_ref}.agg_tenant_daily` AS
        SELECT
            t.tenant_id, t.mall_id, f.date,
            COUNT(*)                      AS transactions,
            SUM(f.total_amount)           AS revenue,
            AVG(f.total_amount)           AS avg_basket,
            COUNT(DISTINCT f.customer_id) AS unique_customers
        FROM `{dataset_ref}.fact_transactions` f
        JOIN `{dataset_ref}.dim_tenant` t USING (tenant_id)
        GROUP BY 1, 2, 3
    """,
    "agg_mall_daily": f"""
        CREATE OR REPLACE TABLE `{dataset_ref}.agg_mall_daily` AS
        SELECT
            mall_id,
            date,
            SUM(total_amount)           AS total_revenue,
            COUNT(*)                    AS total_transactions,
            COUNT(DISTINCT customer_id) AS unique_customers
        FROM `{dataset_ref}.fact_transactions`
        GROUP BY 1, 2
    """,
}

for tbl, sql in AGG_SQLS.items():
    print(f"  {tbl}...", end=" ", flush=True)
    client.query(sql).result()
    rows = client.get_table(f"{dataset_ref}.{tbl}").num_rows
    print(f"{rows:,} rows")

print("\nDone! BigQuery mallpulse_core is ready.")
