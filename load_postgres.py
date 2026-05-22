"""
load_postgres.py — Load all MallPulse CSVs into Cloud SQL Postgres.

Usage (with venv active):
    export PG_PWD="your_password_here"
    export PG_HOST="your_cloud_sql_public_ip"
    python load_postgres.py

Requires PG_PWD and PG_HOST env vars. Optionally set:
    PG_USER  (default: postgres)
    PG_PORT  (default: 5432)
    PG_DB    (default: mallpulse)
"""

import os
import sys
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()  # reads .env if present; env vars override

# ── Config ───────────────────────────────────────────────────────────────────
PG_HOST = os.environ.get('PG_HOST')
PG_PWD  = os.environ.get('PG_PWD')
PG_USER = os.environ.get('PG_USER', 'postgres')
PG_PORT = os.environ.get('PG_PORT', '5432')
PG_DB   = os.environ.get('PG_DB',   'mallpulse')

if not PG_HOST or not PG_PWD:
    print("ERROR: Set PG_HOST and PG_PWD environment variables before running.")
    print("  export PG_HOST=<Cloud SQL public IP>")
    print("  export PG_PWD=<your postgres password>")
    sys.exit(1)

DATA = Path('data')

# Load order: dimensions first, then facts (foreign key safety)
TABLES = [
    'dim_mall',
    'dim_tenant',
    'dim_lease',
    'dim_date',
    'dim_customer',
    'fact_transactions',
    'fact_weather',
    'fact_foot_traffic',
]

# Columns to parse as dates per table
DATE_COLS = {
    'dim_lease':         ['lease_start_date', 'lease_end_date'],
    'dim_date':          ['date'],
    'fact_transactions': ['date'],
    'fact_weather':      ['date'],
    'fact_foot_traffic': ['date'],
}

# ── Connect ──────────────────────────────────────────────────────────────────
url = f"postgresql+psycopg2://{PG_USER}:{PG_PWD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
print(f"Connecting to {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB} ...")
engine = create_engine(url, connect_args={'connect_timeout': 15})

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("  Connected OK.\n")
except Exception as e:
    print(f"  Connection failed: {e}")
    print("  Check PG_HOST, PG_PWD, and that your IP is whitelisted in Cloud SQL.")
    sys.exit(1)

# ── Load ─────────────────────────────────────────────────────────────────────
total_rows = 0
for name in TABLES:
    csv_path = DATA / f'{name}.csv'
    if not csv_path.exists():
        print(f"  SKIP {name}.csv — file not found")
        continue

    parse_dates = DATE_COLS.get(name, [])
    df = pd.read_csv(csv_path, parse_dates=parse_dates)

    print(f"  Loading {name} ({len(df):,} rows)...", end=' ', flush=True)
    df.to_sql(name, engine, if_exists='replace', index=False, chunksize=5000, method='multi')
    total_rows += len(df)
    print("done")

print(f"\nAll tables loaded. Total rows: {total_rows:,}")

# ── Verify ───────────────────────────────────────────────────────────────────
print("\nVerification:")
with engine.connect() as conn:
    for name in TABLES:
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {name}"))
            count = result.scalar()
            print(f"  {name:<25} {count:>10,} rows")
        except Exception as e:
            print(f"  {name:<25} ERROR: {e}")
