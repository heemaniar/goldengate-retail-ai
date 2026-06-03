#!/usr/bin/env bash
# daily_refresh.sh — Regenerate synthetic data and reload BigQuery.
# Triggered daily by Cloud Scheduler → Cloud Run Job.
# Run manually: bash daily_refresh.sh

set -euo pipefail

echo "=== GoldenGate daily data refresh ==="
echo "Date: $(date -u '+%Y-%m-%d %H:%M UTC')"

echo ""
echo "1/3 Generating CSVs (simulate_data.py)..."
python3 simulate_data.py

echo ""
echo "2/3 Loading into BigQuery (load_bigquery.py)..."
python3 load_bigquery.py

echo ""
echo "3/3 Refreshing forecast cache..."
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
echo "=== Refresh complete ==="
