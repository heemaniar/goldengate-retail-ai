"""
bigquery_tools.py — Read-only BigQuery tools for MallPulse agents.

All tools return markdown tables (max 50 rows) or plain-text summaries
so the LLM can reason directly over the results.
"""

import re

from google.cloud import bigquery

PROJECT = "mallpulse-hackathon"
DATASET = "mallpulse_core"
_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT)
    return _client


# Schema summary injected into every agent's system prompt
SCHEMA = """
BigQuery dataset: mallpulse_core (project: mallpulse-hackathon)

Dimension tables:
  dim_mall       : mall_id, mall_name, city, country, latitude, longitude,
                   gross_leasable_sqm, opened_year
  dim_tenant     : tenant_id, tenant_name, mall_id, category, subcategory,
                   unit_size_sqm, store_format
  dim_lease      : tenant_id, lease_start_date, lease_end_date,
                   monthly_base_rent, rent_pct_of_sales
  dim_date       : date, day_of_week, is_weekend, is_holiday, holiday_name,
                   week_of_year, month, quarter, year
  dim_customer   : customer_id, gender, age_band, loyalty_tier

Fact tables:
  fact_transactions : invoice_no, tenant_id, mall_id, customer_id, date,
                      category, quantity, unit_price, total_amount, payment_method
  fact_foot_traffic : mall_id, date, hour, estimated_visits
  fact_weather      : mall_id, date, temperature_c, precipitation_mm, weather_code

Aggregate tables (use these for speed):
  agg_tenant_daily : tenant_id, mall_id, date, transactions, revenue,
                     avg_basket, unique_customers
  agg_mall_daily   : mall_id, date, total_revenue, total_transactions,
                     unique_customers

ML model:
  revenue_forecast — BigQuery ML ARIMA_PLUS, trained on agg_mall_daily.
  Call forecast_mall_revenue(mall_name, days) — do NOT write raw ML.FORECAST SQL.
  Returns daily revenue forecast with 90% confidence intervals.

Date range: 2020-01-01 through yesterday (data updated daily)
Malls: Kanyon, Forum Istanbul, Metrocity, Metropol AVM, Istinye Park,
       Mall of Istanbul, Emaar Square Mall, Cevahir AVM, Viaport Outlet,
       Zorlu Center
"""


def query_warehouse(sql: str) -> str:
    """Execute a read-only SQL query against the MallPulse BigQuery warehouse.

    Args:
        sql: A valid BigQuery SELECT statement. Always qualify table names as
             `mallpulse-hackathon.mallpulse_core.<table_name>`.

    Returns:
        Query results as a markdown table (up to 50 rows), or an error message.
    """
    # Safety: block mutations — use word-boundary match so column aliases like
    # "drop_count" don't trigger a false positive.
    normalised = sql.strip().upper()
    for keyword in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "TRUNCATE", "MERGE"):
        if re.search(rf"\b{keyword}\b", normalised):
            return f"Error: {keyword} statements are not allowed. Use SELECT only."

    try:
        client   = _get_client()
        job      = client.query(sql)
        iterator = job.result(max_results=50)  # RowIterator
        rows     = list(iterator)

        if not rows:
            return "Query returned no rows."

        # schema is on the RowIterator, not the job
        headers = [f.name for f in iterator.schema]
        md  = "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for row in rows:
            md += "| " + " | ".join(str(v) if v is not None else "" for v in row.values()) + " |\n"

        return md

    except Exception as e:
        return f"BigQuery error: {e}"


def get_mall_summary(mall_name: str) -> str:
    """Return a quick revenue and traffic summary for a specific mall.

    Args:
        mall_name: The full mall name, e.g. 'Kanyon' or 'Forum Istanbul'.

    Returns:
        A markdown table with daily revenue stats and average foot traffic.
    """
    sql = f"""
    SELECT
        m.mall_name,
        COUNT(DISTINCT d.date)       AS trading_days,
        ROUND(SUM(d.total_revenue))  AS total_revenue,
        ROUND(AVG(d.total_revenue))  AS avg_daily_revenue,
        ROUND(MAX(d.total_revenue))  AS peak_daily_revenue,
        SUM(d.total_transactions)    AS total_transactions
    FROM `{PROJECT}.{DATASET}.agg_mall_daily` d
    JOIN `{PROJECT}.{DATASET}.dim_mall` m USING (mall_id)
    WHERE LOWER(m.mall_name) = LOWER('{mall_name}')
    GROUP BY 1
    """
    return query_warehouse(sql)


def get_top_tenants(mall_name: str, metric: str = "revenue", limit: int = 10) -> str:
    """Return top-performing tenants for a mall, ranked by a given metric.

    Args:
        mall_name: The full mall name, e.g. 'Kanyon'.
        metric: One of 'revenue', 'transactions', or 'avg_basket'.
        limit: Number of tenants to return (default 10).

    Returns:
        A markdown table of top tenants.
    """
    col_map = {
        "revenue":      "SUM(d.revenue)",
        "transactions": "SUM(d.transactions)",
        "avg_basket":   "AVG(d.avg_basket)",
    }
    order_col = col_map.get(metric.lower(), "SUM(d.revenue)")
    limit = min(int(limit), 50)

    sql = f"""
    SELECT
        t.tenant_name,
        t.category,
        ROUND(SUM(d.revenue), 2)      AS total_revenue,
        SUM(d.transactions)           AS total_transactions,
        ROUND(AVG(d.avg_basket), 2)   AS avg_basket
    FROM `{PROJECT}.{DATASET}.agg_tenant_daily` d
    JOIN `{PROJECT}.{DATASET}.dim_tenant` t USING (tenant_id)
    JOIN `{PROJECT}.{DATASET}.dim_mall`   m ON m.mall_id = t.mall_id
    WHERE LOWER(m.mall_name) = LOWER('{mall_name}')
      AND d.date >= '2020-01-01'
    GROUP BY 1, 2
    ORDER BY {order_col} DESC
    LIMIT {limit}
    """
    return query_warehouse(sql)


def get_weather_traffic_correlation(mall_name: str, year: int = 2022) -> str:
    """Analyse how weather conditions correlate with daily foot traffic at a mall.

    Buckets days by precipitation level (Dry / Light Rain / Heavy Rain) and
    temperature band, then returns average, min, and max daily visits per bucket.
    Use this for any question involving weather impact on foot traffic or sales.

    Args:
        mall_name: Full mall name, e.g. 'Kanyon' or 'Forum Istanbul'.
        year: Calendar year to analyse (default 2022). Data covers 2020 through yesterday.

    Returns:
        Markdown table of avg daily visits by weather type and temperature band.
    """
    sql = f"""
    WITH daily AS (
        SELECT
            w.date,
            SUM(f.estimated_visits) AS daily_visits,
            w.temperature_c,
            w.precipitation_mm,
            CASE
                WHEN w.precipitation_mm > 10 THEN 'Heavy Rain (>10mm)'
                WHEN w.precipitation_mm > 2  THEN 'Light Rain (2-10mm)'
                ELSE 'Dry (<2mm)'
            END AS weather_type,
            CASE
                WHEN w.temperature_c < 5  THEN 'Cold (<5°C)'
                WHEN w.temperature_c < 15 THEN 'Cool (5-15°C)'
                WHEN w.temperature_c < 25 THEN 'Mild (15-25°C)'
                ELSE 'Hot (>25°C)'
            END AS temp_band
        FROM `{PROJECT}.{DATASET}.fact_weather`   w
        JOIN `{PROJECT}.{DATASET}.fact_foot_traffic` f
            ON  w.mall_id = f.mall_id AND w.date = f.date
        JOIN `{PROJECT}.{DATASET}.dim_mall` m
            ON  w.mall_id = m.mall_id
        WHERE LOWER(m.mall_name) = LOWER('{mall_name}')
          AND EXTRACT(YEAR FROM w.date) = {year}
        GROUP BY w.date, w.temperature_c, w.precipitation_mm, weather_type, temp_band
    )
    SELECT
        weather_type,
        temp_band,
        COUNT(*)                       AS days,
        ROUND(AVG(daily_visits))       AS avg_daily_visits,
        ROUND(MIN(daily_visits))       AS min_visits,
        ROUND(MAX(daily_visits))       AS max_visits
    FROM daily
    GROUP BY 1, 2
    ORDER BY avg_daily_visits DESC
    """
    result = query_warehouse(sql)
    return f"**Weather × Foot Traffic — {mall_name} ({year})**\n\n" + result


def forecast_mall_revenue(mall_name: str, days: int = 30) -> str:
    """Forecast daily revenue for a mall using BigQuery ML ARIMA_PLUS model.

    Uses a model trained on historical agg_mall_daily data.
    Returns a markdown table with forecast dates, predicted revenue,
    and 90% confidence interval bounds.

    Args:
        mall_name: Full mall name, e.g. 'Kanyon' or 'Forum Istanbul'.
        days: Number of days to forecast ahead (default 30, max 90).

    Returns:
        Markdown table of forecasted daily revenue with confidence bounds.
    """
    days = min(int(days), 90)

    # Resolve mall_name → mall_id first
    id_sql = f"""
    SELECT mall_id FROM `{PROJECT}.{DATASET}.dim_mall`
    WHERE LOWER(mall_name) = LOWER('{mall_name}')
    LIMIT 1
    """
    client   = _get_client()
    id_rows  = list(client.query(id_sql).result())
    if not id_rows:
        return f"Mall '{mall_name}' not found. Check spelling."
    mall_id = id_rows[0]["mall_id"]
    # Don't quote integer IDs — avoids a type mismatch in BigQuery ML queries
    mall_id_literal = mall_id if isinstance(mall_id, int) else f"'{mall_id}'"

    sql = f"""
    SELECT
        DATE(forecast_timestamp)                    AS forecast_date,
        ROUND(forecast_value, 0)                    AS forecast_revenue,
        ROUND(prediction_interval_lower_bound, 0)   AS lower_90,
        ROUND(prediction_interval_upper_bound, 0)   AS upper_90
    FROM ML.FORECAST(
        MODEL `{PROJECT}.{DATASET}.revenue_forecast`,
        STRUCT({days} AS horizon, 0.90 AS confidence_level)
    )
    WHERE mall_id = {mall_id_literal}
    ORDER BY forecast_timestamp
    """
    result = query_warehouse(sql)
    return f"**Revenue forecast for {mall_name} — next {days} days**\n\n" + result
