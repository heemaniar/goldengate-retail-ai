"""
bigquery_tools.py — Read-only BigQuery tools for GoldenGate Retail AI.

All tools return markdown tables (max 50 rows) or plain-text summaries
so the LLM can reason directly over the results.

⚠️ DISCLAIMER: All data is completely synthetic and generated for
demonstration purposes only. Revenue figures, transaction data, and
performance metrics are fictitious.
"""

import os
import re
from datetime import datetime, timezone

import requests
from google.cloud import bigquery

PROJECT = "mallpulse-hackathon"
DATASET = "goldengate_core"
_client: bigquery.Client | None = None


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT)
    return _client


# Schema summary injected into every agent's system prompt
SCHEMA = """
BigQuery dataset: goldengate_core (project: mallpulse-hackathon)

Dimension tables:
  dim_mall       : mall_id, mall_name, city, state, country, tier,
                   gross_leasable_sqft, latitude, longitude, opened_year
  dim_tenant     : tenant_id, tenant_name, mall_id, category, subcategory,
                   unit_size_sqm, store_format,
                   effective_from (DATE), effective_to (DATE),
                   is_replacement (BOOL)
                   NOTE: same (mall, category) slot may have 2 rows —
                   original tenant and a replacement. Filter by effective_from/to
                   to get who was active on a given date.
  dim_lease      : tenant_id, lease_start_date, lease_end_date,
                   monthly_base_rent (USD), rent_pct_of_sales
  dim_date       : date, day_of_week, is_weekend, is_holiday, holiday_name,
                   week_of_year, month, quarter, year
  dim_customer   : customer_id, gender, age_band, loyalty_tier

Fact tables:
  fact_transactions : invoice_no, tenant_id, mall_id, customer_id, date,
                      category, quantity, unit_price, total_amount (USD),
                      payment_method
  fact_foot_traffic : mall_id, date, hour, estimated_visits
  fact_weather      : mall_id, date, temperature_c, precipitation_mm, weather_code

Aggregate tables (use these for speed):
  agg_tenant_daily : tenant_id, mall_id, date, transactions, revenue (USD),
                     avg_basket, unique_customers
  agg_mall_daily   : mall_id, date, total_revenue (USD), total_transactions,
                     unique_customers

ML model:
  revenue_forecast — BigQuery ML ARIMA_PLUS, trained on agg_mall_daily.
  Call forecast_mall_revenue(mall_name, days) — do NOT write raw ML.FORECAST SQL.
  Returns daily revenue forecast with 90% confidence intervals.

Currency: All monetary values are in USD ($).
Date range: 2020-01-01 through 2026-05-27 (synthetic data, updated daily)

Bay Area Malls (13 total):
  m01: Westfield Valley Fair (San Jose) — Premium Regional, 1.8M sqft
  m02: Stanford Shopping Center (Palo Alto) — Luxury Open-Air, 1.4M sqft
  m03: Santana Row (San Jose) — Lifestyle Premium, 700K sqft
  m04: Westfield San Francisco Centre (San Francisco) — Urban; CLOSED Aug 2023
  m05: Stonestown Galleria (San Francisco) — Community Regional, 910K sqft
  m06: Bay Street Emeryville (Emeryville) — Lifestyle Open-Air, 420K sqft
  m07: Great Mall (Milpitas) — Value Outlet, 1.5M sqft
  m08: Hillsdale Shopping Center (San Mateo) — Mid-tier Regional, 1.1M sqft
  m09: Stoneridge Shopping Center (Pleasanton) — Mid-tier Regional, 1.2M sqft
  m10: Broadway Plaza (Walnut Creek) — Mid-tier Open-Air, 735K sqft
  m11: Sunvalley Shopping Center (Concord) — Value Regional, 1.1M sqft
  m12: Westfield Oakridge (San Jose) — Mid-tier Regional, 1.2M sqft
  m13: San Francisco Premium Outlets (Livermore) — Premium Outlets, 800K sqft

Key real-world events modeled in synthetic data:
  - COVID-19 shutdown: Mar 17 - Jun 14, 2020 (~0 transactions)
  - COVID partial reopen: Jun 2020 - Jun 2021 (30-85% normal)
  - 2020 Wildfire smoke: Aug 18 - Sep 15, 2020 (severe foot traffic drop)
  - Supply chain crunch: Oct 2021 - Mar 2022
  - Inflation impact: Jun 2022 - Jun 2023
  - Tech layoffs (Bay Area): Nov 2022 - Dec 2023 (premium malls affected)
  - Westfield SF Centre decline: Jan 2022 then closed Aug 15, 2023
  - Atmospheric rivers: Dec 26 2022 - Mar 10 2023
  - Bay Area recovery: 2024-2026
"""


def query_warehouse(sql: str) -> str:
    """Execute a read-only SQL query against the GoldenGate Retail AI BigQuery warehouse.

    Args:
        sql: A valid BigQuery SELECT statement. Always qualify table names as
             `mallpulse-hackathon.goldengate_core.<table_name>`.

    Returns:
        Query results as a markdown table (up to 50 rows), or an error message.
    """
    normalised = sql.strip().upper()
    for keyword in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "TRUNCATE", "MERGE"):
        if re.search(rf"\b{keyword}\b", normalised):
            return f"Error: {keyword} statements are not allowed. Use SELECT only."

    try:
        client   = _get_client()
        job      = client.query(sql)
        iterator = job.result(max_results=50)
        rows     = list(iterator)

        if not rows:
            return "Query returned no rows."

        headers = [f.name for f in iterator.schema]
        md  = "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for row in rows:
            md += "| " + " | ".join(str(v) if v is not None else "" for v in row) + " |\n"
        return md

    except Exception as e:
        return f"BigQuery error: {e}"


def get_mall_summary(mall_name: str, period_days: int = 30) -> str:
    """Get revenue, transaction, and foot traffic summary for a specific mall."""
    sql = f"""
    WITH mall AS (
        SELECT mall_id, mall_name, city, tier
        FROM `{PROJECT}.{DATASET}.dim_mall`
        WHERE LOWER(mall_name) LIKE LOWER('%{mall_name}%')
        LIMIT 1
    )
    SELECT
        mall.mall_name,
        mall.city,
        mall.tier,
        ROUND(SUM(a.total_revenue), 0)   AS revenue_usd,
        SUM(a.total_transactions)        AS transactions,
        ROUND(SUM(a.total_revenue) / NULLIF(SUM(a.total_transactions), 0), 2) AS avg_basket_usd
    FROM `{PROJECT}.{DATASET}.agg_mall_daily` a
    JOIN mall ON a.mall_id = mall.mall_id
    WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {period_days} DAY)
    GROUP BY mall.mall_name, mall.city, mall.tier
    """
    return query_warehouse(sql)


def get_top_tenants(mall_name: str, period_days: int = 30, limit: int = 10) -> str:
    """Get top-performing tenants at a mall by revenue."""
    sql = f"""
    SELECT
        t.tenant_name,
        t.category,
        t.store_format,
        ROUND(SUM(a.revenue), 0)       AS revenue_usd,
        SUM(a.transactions)            AS transactions,
        ROUND(AVG(a.avg_basket), 2)    AS avg_basket_usd
    FROM `{PROJECT}.{DATASET}.agg_tenant_daily` a
    JOIN `{PROJECT}.{DATASET}.dim_tenant` t ON t.tenant_id = a.tenant_id
    JOIN `{PROJECT}.{DATASET}.dim_mall`   m ON m.mall_id = a.mall_id
    WHERE LOWER(m.mall_name) LIKE LOWER('%{mall_name}%')
      AND a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {period_days} DAY)
      AND t.effective_to >= CURRENT_DATE()
    GROUP BY t.tenant_name, t.category, t.store_format
    ORDER BY revenue_usd DESC
    LIMIT {limit}
    """
    return query_warehouse(sql)


def get_weather_traffic_correlation(mall_name: str, period_days: int = 90) -> str:
    """Analyze the correlation between weather conditions and foot traffic."""
    sql = f"""
    SELECT
        CASE
            WHEN w.precipitation_mm > 15 THEN 'Heavy Rain (>15mm)'
            WHEN w.precipitation_mm > 5  THEN 'Moderate Rain (5-15mm)'
            WHEN w.precipitation_mm > 0  THEN 'Light Rain (<5mm)'
            WHEN w.weather_code = 45     THEN 'Foggy'
            ELSE 'Clear / Dry'
        END AS weather_condition,
        COUNT(DISTINCT w.date)          AS days,
        ROUND(AVG(ft.daily_visits), 0) AS avg_daily_visits,
        ROUND(AVG(w.temperature_c), 1) AS avg_temp_c
    FROM `{PROJECT}.{DATASET}.fact_weather` w
    JOIN `{PROJECT}.{DATASET}.dim_mall` m
        ON m.mall_id = w.mall_id AND LOWER(m.mall_name) LIKE LOWER('%{mall_name}%')
    JOIN (
        SELECT mall_id, date, SUM(estimated_visits) AS daily_visits
        FROM `{PROJECT}.{DATASET}.fact_foot_traffic`
        GROUP BY mall_id, date
    ) ft ON ft.mall_id = w.mall_id AND ft.date = w.date
    WHERE w.date >= DATE_SUB(CURRENT_DATE(), INTERVAL {period_days} DAY)
    GROUP BY weather_condition
    ORDER BY avg_daily_visits DESC
    """
    return query_warehouse(sql)


def forecast_mall_revenue(mall_name: str, days: int = 30) -> str:
    """Forecast daily revenue for a mall using BigQuery ML ARIMA_PLUS."""
    days = min(days, 30)

    cache_sql = f"""
    SELECT m.mall_name, fc.forecast_date,
           ROUND(fc.forecast_revenue, 0) AS forecast_revenue_usd,
           ROUND(fc.lower_90, 0)         AS lower_90_usd,
           ROUND(fc.upper_90, 0)         AS upper_90_usd
    FROM `{PROJECT}.{DATASET}.forecast_cache` fc
    JOIN `{PROJECT}.{DATASET}.dim_mall` m ON m.mall_id = fc.mall_id
    WHERE LOWER(m.mall_name) LIKE LOWER('%{mall_name}%')
      AND DATE(fc.cached_at) = CURRENT_DATE()
    ORDER BY fc.forecast_date
    LIMIT {days}
    """
    cached = query_warehouse(cache_sql)
    if "BigQuery error" not in cached and "returned no rows" not in cached.lower():
        return cached

    live_sql = f"""
    SELECT
        m.mall_name,
        CAST(f.forecast_timestamp AS DATE) AS forecast_date,
        ROUND(f.forecast_value, 0)          AS forecast_revenue_usd,
        ROUND(f.prediction_interval_lower_bound, 0) AS lower_90_usd,
        ROUND(f.prediction_interval_upper_bound, 0) AS upper_90_usd
    FROM ML.FORECAST(
        MODEL `{PROJECT}.{DATASET}.revenue_forecast`,
        STRUCT({days} AS horizon, 0.9 AS confidence_level)
    ) f
    JOIN `{PROJECT}.{DATASET}.dim_mall` m ON m.mall_id = f.mall_id
    WHERE LOWER(m.mall_name) LIKE LOWER('%{mall_name}%')
    ORDER BY forecast_date
    LIMIT {days}
    """
    return query_warehouse(live_sql)


# ── Fivetran pipeline health ──────────────────────────────────────────────────

_FIVETRAN_BASE = "https://api.fivetran.com/v1"


def _fivetran_auth() -> tuple[str, str] | None:
    key    = os.environ.get("FIVETRAN_API_KEY", "")
    secret = os.environ.get("FIVETRAN_API_SECRET", "")
    if not key or not secret:
        return None
    return (key, secret)


def check_fivetran_pipeline() -> str:
    """Check the health of the Fivetran data pipeline syncing into BigQuery.

    Returns a plain-text summary of all Fivetran connectors: their sync state,
    last successful sync time, schedule frequency, and any errors.
    """
    auth = _fivetran_auth()
    if not auth:
        return "Fivetran credentials not configured (FIVETRAN_API_KEY / FIVETRAN_API_SECRET missing)."

    connector_id = os.environ.get("FIVETRAN_CONNECTOR_ID", "")

    # --- List all connectors in the account ---
    try:
        group_resp = requests.get(f"{_FIVETRAN_BASE}/groups", auth=auth, timeout=10)
        group_resp.raise_for_status()
        groups = group_resp.json().get("data", {}).get("items", [])
    except Exception as e:
        return f"Fivetran API error (groups): {e}"

    lines: list[str] = ["## Fivetran Pipeline Health\n"]

    for group in groups:
        gid   = group["id"]
        gname = group.get("name", gid)

        try:
            conn_resp = requests.get(
                f"{_FIVETRAN_BASE}/groups/{gid}/connectors", auth=auth, timeout=10
            )
            conn_resp.raise_for_status()
            connectors = conn_resp.json().get("data", {}).get("items", [])
        except Exception as e:
            lines.append(f"- Group **{gname}**: API error — {e}")
            continue

        for c in connectors:
            cid      = c.get("id", "?")
            service  = c.get("service", "?")
            schema   = c.get("schema", "?")
            status   = c.get("status", {})
            sync_st  = status.get("sync_state", "unknown")
            setup_st = status.get("setup_state", "unknown")
            update_st = status.get("update_state", "unknown")
            paused   = c.get("paused", False)
            freq_min = c.get("sync_frequency", "?")
            succeeded_at = c.get("succeeded_at") or "never"
            failed_at    = c.get("failed_at")
            warnings     = status.get("warnings", [])
            tasks        = status.get("tasks", [])

            # Compute data freshness
            freshness = ""
            if succeeded_at and succeeded_at != "never":
                try:
                    last = datetime.fromisoformat(succeeded_at.replace("Z", "+00:00"))
                    age  = datetime.now(timezone.utc) - last
                    h, m = divmod(int(age.total_seconds() // 60), 60)
                    freshness = f" — last sync **{h}h {m}m ago**"
                except Exception:
                    freshness = f" — last sync {succeeded_at}"

            # Health icon
            if paused:
                icon = "⏸️"
            elif failed_at and (not succeeded_at or failed_at > succeeded_at):
                icon = "🔴"
            elif update_st == "delayed":
                icon = "🟡"
            else:
                icon = "🟢"

            lines.append(
                f"{icon} **{service}** (schema: `{schema}`, id: `{cid}`)\n"
                f"  - Setup: {setup_st} | Sync: {sync_st} | Updates: {update_st}"
                f"{' | ⏸ PAUSED' if paused else ''}\n"
                f"  - Frequency: every {freq_min} min{freshness}"
            )
            if failed_at:
                lines.append(f"  - 🔴 Last failure: {failed_at}")
            if warnings:
                for w in warnings[:3]:
                    lines.append(f"  - ⚠️ {w.get('message', w)}")
            if tasks:
                for t in tasks[:3]:
                    lines.append(f"  - 📋 {t.get('message', t)}")

    if not lines or len(lines) == 1:
        # Fallback: check the single connector ID if present
        if connector_id:
            return _check_single_connector(auth, connector_id)
        return "No Fivetran connectors found in this account."

    return "\n".join(lines)


def _check_single_connector(auth: tuple[str, str], connector_id: str) -> str:
    """Fallback: check one connector by ID when group listing returns nothing."""
    try:
        r = requests.get(f"{_FIVETRAN_BASE}/connectors/{connector_id}", auth=auth, timeout=10)
        r.raise_for_status()
        c = r.json().get("data", {})
    except Exception as e:
        return f"Fivetran API error: {e}"

    service      = c.get("service", "?")
    schema       = c.get("schema", "?")
    status       = c.get("status", {})
    sync_st      = status.get("sync_state", "unknown")
    setup_st     = status.get("setup_state", "unknown")
    update_st    = status.get("update_state", "unknown")
    paused       = c.get("paused", False)
    freq_min     = c.get("sync_frequency", "?")
    succeeded_at = c.get("succeeded_at") or "never"
    failed_at    = c.get("failed_at")

    freshness = ""
    if succeeded_at != "never":
        try:
            last = datetime.fromisoformat(succeeded_at.replace("Z", "+00:00"))
            age  = datetime.now(timezone.utc) - last
            h, m = divmod(int(age.total_seconds() // 60), 60)
            freshness = f"Last successful sync: **{h}h {m}m ago** ({succeeded_at})"
        except Exception:
            freshness = f"Last successful sync: {succeeded_at}"

    icon = "⏸️" if paused else ("🔴" if failed_at else "🟢")
    lines = [
        f"## Fivetran Pipeline Health\n",
        f"{icon} **{service}** (schema: `{schema}`, id: `{connector_id}`)",
        f"- Setup: **{setup_st}** | Sync: **{sync_st}** | Updates: **{update_st}**",
        f"- Frequency: every **{freq_min} minutes**",
    ]
    if freshness:
        lines.append(f"- {freshness}")
    if failed_at:
        lines.append(f"- 🔴 Last failure: {failed_at}")
    if paused:
        lines.append(f"- ⏸️ Pipeline is **paused**")
    for w in status.get("warnings", [])[:3]:
        lines.append(f"- ⚠️ {w.get('message', w)}")
    for t in status.get("tasks", [])[:3]:
        lines.append(f"- 📋 {t.get('message', t)}")

    return "\n".join(lines)
