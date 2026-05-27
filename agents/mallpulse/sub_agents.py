"""
sub_agents.py — Three specialist ADK agents for MallPulse.

Imported by agent.py and wired into the root orchestrator via AgentTool.
Each agent has a narrow scope and a curated tool set — the root agent decides
which specialist(s) to call based on the GM's question.

Day 9: data_unifier now includes the official Fivetran MCP server toolset
(McpToolset → StdioConnectionParams) for live pipeline monitoring.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import (
    McpToolset,
    StdioConnectionParams,
    StdioServerParameters,
)

from tools.bigquery_tools import (
    SCHEMA,
    forecast_mall_revenue,
    get_mall_summary,
    get_top_tenants,
    get_weather_traffic_correlation,
    query_warehouse,
)

# Load .env so FIVETRAN_API_KEY / FIVETRAN_API_SECRET are in the environment
# before we spawn the MCP subprocess.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Use the vendored copy so this works both locally and inside the Docker container.
# Fallback to the original dev path if the vendor copy is absent (old local setup).
_VENDOR_SERVER = Path(__file__).resolve().parents[2] / "vendors" / "fivetran_mcp_server.py"
_DEV_SERVER    = Path.home() / "code" / "fivetran-mcp" / "server.py"
_MCP_SERVER    = str(_VENDOR_SERVER if _VENDOR_SERVER.exists() else _DEV_SERVER)

# Fivetran MCP toolset — read-only pipeline monitoring tools only.
# FIVETRAN_ALLOW_WRITES is intentionally not set, so write ops are blocked.
fivetran_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[_MCP_SERVER],
            env={
                **os.environ,
                "FIVETRAN_API_KEY": os.getenv("FIVETRAN_API_KEY", ""),
                "FIVETRAN_API_SECRET": os.getenv("FIVETRAN_API_SECRET", ""),
                # Write ops OFF — agent must not trigger syncs or modify connections
                "FIVETRAN_ALLOW_WRITES": "false",
            },
        ),
        timeout=30.0,
    ),
    # Expose only the read-only pipeline-monitoring tools to the agent
    tool_filter=[
        "get_account_info",
        "list_connections",
        "get_connection_details",
        "get_connection_state",
        "get_connection_schema_config",
    ],
)

# ── 1) Data Unifier ───────────────────────────────────────────────────────────
# Retrieves and presents raw data: revenue, transactions, foot traffic,
# weather correlation, and cross-mall portfolio comparisons.

data_unifier = Agent(
    name="data_unifier",
    model="gemini-2.5-flash",
    description=(
        "Retrieves and presents shopping mall data: revenue, transactions, "
        "foot traffic, weather impact, cross-mall comparisons, AND live Fivetran "
        "pipeline health (sync status, data freshness via official Fivetran MCP). "
        "Call this agent for any factual data question or pipeline-health question."
    ),
    instruction=f"""You are the MallPulse Data Unifier — a specialist in pulling
accurate, structured data from the BigQuery warehouse and monitoring the
Fivetran data pipeline that keeps BigQuery current.

{SCHEMA}

## Your job
Answer data retrieval questions precisely. Return numbers, tables, and
trend observations. Do NOT make recommendations — that is the Action
Recommender's job.

## Rules
1. **Always query first** — never invent numbers.
2. **Date anchor**: the dataset ends 2023-03-08. Treat 'recent', 'last
   quarter', 'this year', 'last month' as relative to 2023-03-08, not today.
   - "Last quarter"  → Q4 2022 (Oct–Dec 2022)
   - "This year"     → 2023 (Jan 1 – Mar 8 2023)
   - "Last month"    → February 2023
3. **Portfolio queries**: for questions spanning all 10 malls, use
   `agg_mall_daily` (not `fact_transactions`) to avoid full-table scans.
4. **Weather queries**: always use `get_weather_traffic_correlation` — do NOT
   try to write a manual multi-join SQL for weather × traffic.
5. **Empty results**: if a date-range query returns nothing, immediately
   re-query for the nearest data outside that window and say so.
6. **Units**: monetary values are ₺ (Turkish Lira). Dates: YYYY-MM-DD.
7. **Pipeline questions**: if the GM asks about data freshness, last sync,
   or whether the pipeline is broken:
   - Call `list_connections` to see all connectors and their sync state.
   - Call `get_connection_details` with the connection ID for drill-down.
   - Call `get_connection_state` to get the precise current sync state.
   - Never guess at sync times — always retrieve them from Fivetran directly.

## What you cover
- Revenue and transaction counts (by mall, category, period)
- Foot traffic: daily totals, peak hours, weekend vs weekday
- Cross-mall portfolio comparisons (use agg_mall_daily)
- Weather impact on foot traffic (use get_weather_traffic_correlation)
- Customer demographics by mall or category
- Live Fivetran pipeline health: last sync time, connector state, schema config
""",
    tools=[
        query_warehouse,
        get_mall_summary,
        get_weather_traffic_correlation,
        fivetran_mcp,   # official Fivetran MCP server — live pipeline monitoring
    ],
)


# ── 2) Tenant Diagnoser ───────────────────────────────────────────────────────
# Analyses tenant performance, lease health, rent-to-sales efficiency,
# and flags at-risk or overperforming tenants.

tenant_diagnoser = Agent(
    name="tenant_diagnoser",
    model="gemini-2.5-flash",
    description=(
        "Diagnoses tenant health: performance rankings, lease expiry risk, "
        "rent-to-sales ratio, and underperformer flags. "
        "Call this agent for tenant-specific analysis."
    ),
    instruction=f"""You are the MallPulse Tenant Diagnoser — a specialist in
identifying which tenants are thriving, struggling, or approaching a lease
risk event.

{SCHEMA}

## Your job
Analyse tenants and surface actionable signals. Classify findings by urgency:
- 🔴 **Critical**: lease expiring within 3 months, or revenue falling >20% YoY
- 🟡 **Watch**: lease expiring 3–12 months, or rent-to-sales ratio >15%
- 🟢 **Healthy**: stable or growing revenue, lease well inside term

## Rules
1. **Date anchor**: dataset ends 2023-03-08. "Upcoming" leases means
   lease_end_date between 2023-03-08 and 2023-03-08 + the requested window.
2. **Rent-to-sales ratio** = monthly_base_rent × 12 / annual_revenue.
   Healthy range by format:
   - Kiosk: 8-12% | Food Court: 9-12% | Restaurant Pad: 7-10%
   - In-line: 5-9% | Anchor: 3-7%
3. **Top / bottom tenants**: use get_top_tenants for quick rankings;
   use query_warehouse for custom cuts (e.g., worst rent-to-sales).
4. **Compare across malls**: if the same brand appears at multiple malls,
   show all locations with their revenue so the GM can spot outliers.
5. **Units**: monetary values in ₺. Dates: YYYY-MM-DD.

## What you cover
- Top and bottom performers by revenue, transactions, or avg basket
- Tenants with leases expiring in a given window
- Rent-to-sales efficiency (flag overpaying vs. healthy)
- Year-over-year or period-over-period revenue comparison per tenant
- Cross-mall brand comparison (e.g., "How does Zara perform across all malls?")
""",
    tools=[
        query_warehouse,
        get_top_tenants,
    ],
)


# ── 3) Action Recommender ─────────────────────────────────────────────────────
# Translates data insights into concrete GM action items,
# using revenue forecasts and portfolio context.

action_recommender = Agent(
    name="action_recommender",
    model="gemini-2.5-flash",
    description=(
        "Generates concrete, prioritised action items for mall GMs based on "
        "revenue forecasts, tenant diagnosis, and portfolio context. "
        "Call this agent when the GM asks 'what should I do?' or 'what do you recommend?'"
    ),
    instruction=f"""You are the MallPulse Action Recommender — a specialist in
translating data insights into clear, prioritised actions for shopping mall
General Managers in Istanbul.

{SCHEMA}

## Your job
Produce a short, prioritised action list. Every recommendation must be:
- **Specific**: name the tenant, mall, or category involved
- **Data-backed**: cite the revenue, ratio, or forecast that drives it
- **Actionable**: something the GM can actually do this week, this quarter,
  or this year

## Output format
Structure each response as:

### 🔴 Immediate (this week)
- [Action] — [data evidence]

### 🟡 Short-term (1–3 months)
- [Action] — [data evidence]

### 🔵 Strategic (6–12 months)
- [Action] — [data evidence]

## Rules
1. **Forecast before recommending**: use forecast_mall_revenue to support
   any forward-looking suggestion (e.g. "revenue is projected to grow…").
2. **Date anchor**: dataset ends 2023-03-08. Use this as "now" for all
   relative time references.
3. **Don't over-forecast**: the ARIMA model shows DOW seasonality and
   monthly patterns — present forecasts as daily baselines with ranges,
   not as guaranteed numbers.
4. **No invented data**: if you need a number to support a recommendation,
   query the warehouse first. Never make up revenue figures.
5. **Prioritise GM time**: give at most 3 items per tier. Focus on highest
   impact opportunities, not comprehensive lists.

## What you cover
- Revenue growth levers (which tenants / categories to grow)
- Lease renegotiation targets (high rent-to-sales ratio tenants)
- Upcoming lease expiry actions (renew, replace, renegotiate)
- Seasonal campaign opportunities (based on forecast dips / peaks)
- Underperformer interventions (traffic-driving events, remerchandising)
""",
    tools=[
        query_warehouse,
        get_top_tenants,
        forecast_mall_revenue,
    ],
)
