#!/usr/bin/env bash
# daily_refresh.sh — Incrementally extend the synthetic warehouse to yesterday.
# Triggered daily by Cloud Scheduler → Cloud Run Job.
# Run manually: bash daily_refresh.sh
#
# Incremental design (avoids the Cloud Run task timeout that the old full-regen
# hit): only the missing days of facts are generated and APPENDed. Dimensions
# are still regenerated in full (cheap). See simulate_data.py / load_bigquery.py.

set -euo pipefail

echo "=== GoldenGate daily data refresh ==="
echo "Date: $(date -u '+%Y-%m-%d %H:%M UTC')"

echo ""
echo "0/4 Determining incremental window from BigQuery..."
REFRESH_VARS=$(python3 - << 'PYEOF'
from datetime import date, timedelta
from google.cloud import bigquery

client = bigquery.Client(project="mallpulse-hackathon")
row = list(client.query(
    """
    SELECT MAX(date) AS last_date,
           MAX(CAST(SUBSTR(invoice_no, 4) AS INT64)) AS max_inv
    FROM `mallpulse-hackathon.goldengate_core.fact_transactions`
    """
).result())[0]

last_date = row["last_date"]
max_inv   = row["max_inv"] or 1_000_000
yesterday = date.today() - timedelta(days=1)

if last_date is None or last_date >= yesterday:
    print("UPTODATE")
else:
    print(f"FACT_START_DATE={last_date + timedelta(days=1)}")
    print(f"INVOICE_START={max_inv + 1}")
PYEOF
)

echo "$REFRESH_VARS"
if echo "$REFRESH_VARS" | grep -q "UPTODATE"; then
    echo "Warehouse already current through yesterday — nothing to do."
    exit 0
fi

# Export FACT_START_DATE / INVOICE_START for simulate_data.py and switch the
# loader into append mode.
export $(echo "$REFRESH_VARS" | xargs)
export REFRESH_MODE=incremental

echo ""
echo "1/4 Generating missing-day CSVs (simulate_data.py, incremental)..."
python3 simulate_data.py

echo ""
echo "2/4 Appending facts + rebuilding aggregates/model (load_bigquery.py)..."
python3 load_bigquery.py

echo ""
echo "3/4 Refreshing forecast cache..."
python3 - << 'PYEOF'
from google.cloud import bigquery
client = bigquery.Client(project="mallpulse-hackathon")

# Clear stale cache rows
client.query("DELETE FROM `mallpulse-hackathon.goldengate_core.forecast_cache` WHERE TRUE").result()

# Repopulate from ARIMA model
sql = """
INSERT INTO `mallpulse-hackathon.goldengate_core.forecast_cache`
  (mall_id, forecast_date, forecast_revenue, lower_90, upper_90, cached_at)
SELECT
  m.mall_id,
  CAST(f.forecast_timestamp AS DATE),
  ROUND(f.forecast_value, 2),
  ROUND(f.prediction_interval_lower_bound, 2),
  ROUND(f.prediction_interval_upper_bound, 2),
  CURRENT_TIMESTAMP()
FROM ML.FORECAST(
  MODEL `mallpulse-hackathon.goldengate_core.revenue_forecast`,
  STRUCT(30 AS horizon, 0.9 AS confidence_level)
) f
JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m ON m.mall_id = f.mall_id
"""
job = client.query(sql)
job.result()
print(f"Forecast cache refreshed: {job.num_dml_affected_rows} rows")
PYEOF

echo ""
echo "4/4 Done."
echo "=== Refresh complete ==="
