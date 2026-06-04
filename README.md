# 🌉 GoldenGate Retail AI

**AI Co-Pilot for Bay Area Shopping Mall General Managers**

> ⚠️ **All data in this project is completely synthetic and generated for demonstration purposes only.** Revenue figures, transaction data, tenant names, and performance metrics are fictitious. Real brand names are used solely to make the demo realistic and are not associated with any actual business data.

GoldenGate Retail AI is a multi-agent system that turns a retail data warehouse into instant, actionable intelligence. Mall GMs ask natural-language questions about tenant performance, revenue trends, lease health, weather impact, and 30-day revenue forecasts — and get data-backed answers in seconds, every number traceable to the SQL behind it.

**🔗 Live demo:** https://goldengate-3f3swnt3qq-uc.a.run.app

---

## What it does

These are the app's built-in quick questions — each maps to a capability verified against the warehouse:

| Ask this… | GoldenGate answers with… | Agent |
|---|---|---|
| *"How much revenue did Westfield Valley Fair generate last month?"* | Exact revenue + transaction count from BigQuery | Data Unifier |
| *"Which Bay Area mall had the highest revenue last month?"* | Ranked portfolio comparison | Data Unifier |
| *"How does Stanford Shopping Center compare to other Bay Area malls this year?"* | Cross-mall comparison table | Data Unifier |
| *"What was the weather impact on foot traffic at Bay Street Emeryville last quarter?"* | Visits bucketed by weather condition + temperature | Data Unifier |
| *"Is the Fivetran data pipeline healthy?"* | Live connector status via Fivetran MCP **plus** a data-freshness cross-check (`MAX(date)`) | Data Unifier |
| *"Who are the top 5 tenants at Stanford Shopping Center by revenue?"* | Ranked table with $ totals | Tenant Diagnoser |
| *"Which tenants at Santana Row have leases expiring in the next 6 months?"* | Risk-flagged list with rent-to-sales ratios | Tenant Diagnoser |
| *"Compare lululemon's performance across all Bay Area malls"* | Per-location revenue with active / historical status | Tenant Diagnoser |
| *"Forecast next 30 days revenue for Broadway Plaza"* | ARIMA_PLUS daily forecast, 90% CI, and a grounded 30-day total | Action Recommender |
| *"What are the top 3 actions I should take this week at Stoneridge Shopping Center?"* | Prioritised, data-backed action list | Action Recommender |

The sidebar mall selector re-scopes every quick question to whichever mall you pick.

---

## Accuracy & reliability

GoldenGate is built so a GM can trust the numbers:

- **Show the SQL** — every answer has an expander with the exact query that produced it.
- **Correct aggregate semantics** — unique customers use `COUNT(DISTINCT customer_id)` (never summed daily uniques); average basket uses `SUM(revenue) / SUM(transactions)` (never average-of-averages).
- **No fabrication** — when a requested period has no data (e.g. 2018 or a future year), the agent says so and stops; it never substitutes a figure from another period.
- **Grounded forecast totals** — the 30-day total is computed in the tool and quoted verbatim, so it can't drift from the daily rows.
- **Honest freshness** — pipeline-health answers cross-check the actual `MAX(date)` rather than assuming a healthy connector means current data.
- **Regression tests** — `tests/test_accuracy.py` locks these guarantees as runtime invariants against the live warehouse.

---

## Architecture

```
User (Streamlit chat UI — Show SQL on every answer)
        │
        ▼
┌──────────────────────────────────────────────────────┐
│         Root Orchestrator — goldengate                │
│         (Gemini 3 Flash Preview, Vertex AI global)    │
│  Routes intent → one or more specialist sub-agents    │
└──────┬─────────────────┬──────────────────┬───────────┘
       │                 │                  │
       ▼                 ▼                  ▼
┌────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Data      │  │  Tenant         │  │  Action         │
│  Unifier   │  │  Diagnoser      │  │  Recommender    │
│            │  │                 │  │                 │
│ BigQuery   │  │ BigQuery        │  │ BigQuery        │
│ Fivetran   │  │ rent-to-sales   │  │ ARIMA_PLUS      │
│ MCP server │  │ lease risk      │  │ forecast + total│
└────────────┘  └─────────────────┘  └─────────────────┘
       │
       ▼
┌───────────────────────────────────────────────────────┐
│                   Data Layer                          │
│  Fivetran → BigQuery (goldengate_core)                │
│  Daily incremental refresh (Cloud Run Job + Scheduler)│
│  fact_transactions · dim_tenant · dim_mall · dim_lease │
│  fact_weather · fact_foot_traffic · dim_customer       │
│  agg_mall_daily · agg_tenant_daily · revenue_forecast  │
└───────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| **AI agents** | Google ADK 1.34, Gemini 3 Flash Preview (Vertex AI global) |
| **Orchestration** | Root agent → 3 specialist sub-agents via `AgentTool` |
| **Partner integration** | Fivetran MCP server, wired via ADK `McpToolset` (read-only connector tools) |
| **Data warehouse** | BigQuery (`goldengate_core`: 10 tables + ARIMA model + forecast cache) |
| **ML forecasting** | BigQuery ML `ARIMA_PLUS` — 30-day revenue forecast with 90% CI, US holidays |
| **Data freshness** | Daily incremental refresh — Cloud Run Job triggered by Cloud Scheduler |
| **UI** | Streamlit (lavender theme, live tool-call status, Show SQL expander) |
| **Dashboard** | Google Data Studio (revenue trends, tenant performance) |
| **Testing** | pytest accuracy regression suite (`tests/test_accuracy.py`) |
| **Deployment** | Cloud Run (container, port 8080), Artifact Registry (`goldengate-repo`) |

---

## Dataset

- **Coverage:** 13 Bay Area malls (San Jose → San Francisco → Livermore), January 2020 – present (refreshed daily)
- **Volume:** ~1.5M synthetic transactions across 500+ tenants
- **Real-world events modeled:** COVID-19 lockdown (Mar–Jun 2020), 2020 wildfire smoke, supply-chain crunch (2021–2022), tech layoffs (2022–2023), Westfield SF Centre closure (Aug 2023), atmospheric rivers (Dec 2022–Mar 2023), Bay Area recovery (2024–2026)
- **Brands:** Real Bay Area brands (Philz Coffee, Blue Bottle, Boudin Bakery, lululemon, etc.) used with a clear synthetic-data disclaimer
- **Weather:** Bay Area–accurate patterns (SF fog, Livermore heat waves, atmospheric-river rain events)
- **Generation:** `simulate_data.py` produces the source CSVs → `load_bigquery.py` loads to BigQuery and trains the ARIMA model

> ⚠️ **Synthetic data disclaimer:** All transaction figures, revenue numbers, tenant performance data, and business metrics are completely fictitious and generated algorithmically. Real brand names are referenced purely for demo realism. No actual business or financial data is represented.

---

## 13 Bay Area Malls

| ID | Mall | City | Tier |
|---|---|---|---|
| m01 | Westfield Valley Fair | San Jose | Premium Regional |
| m02 | Stanford Shopping Center | Palo Alto | Luxury Open-Air |
| m03 | Santana Row | San Jose | Lifestyle Premium |
| m04 | Westfield SF Centre | San Francisco | Urban *(closed Aug 2023)* |
| m05 | Stonestown Galleria | San Francisco | Community Regional |
| m06 | Bay Street Emeryville | Emeryville | Lifestyle Open-Air |
| m07 | Great Mall | Milpitas | Value Outlet |
| m08 | Hillsdale Shopping Center | San Mateo | Mid-tier Regional |
| m09 | Stoneridge Shopping Center | Pleasanton | Mid-tier Regional |
| m10 | Broadway Plaza | Walnut Creek | Mid-tier Open-Air |
| m11 | Sunvalley Shopping Center | Concord | Value Regional |
| m12 | Westfield Oakridge | San Jose | Mid-tier Regional |
| m13 | San Francisco Premium Outlets | Livermore | Premium Outlets |

*(10 distinct cities across the portfolio.)*

---

## Three specialist agents

### 1 · Data Unifier
Retrieves raw data from BigQuery and monitors the Fivetran pipeline.
- Tools: `query_warehouse`, `get_mall_summary`, `get_weather_traffic_correlation`
- MCP: Fivetran connector tools via `McpToolset` (account info, connector state, schema config — read-only)
- Cross-checks `MAX(date)` for honest data-freshness answers

### 2 · Tenant Diagnoser
Flags at-risk tenants and surfaces lease + revenue signals.
- Classifies tenants: 🔴 Critical / 🟡 Watch / 🟢 Healthy
- Bay Area rent-to-sales benchmarks by format (kiosk, inline, anchor, luxury, etc.)
- Tools: `query_warehouse`, `get_top_tenants`

### 3 · Action Recommender
Translates data insights into a prioritised GM action list.
- Three tiers: Immediate (this week) / Short-term (1–3 months) / Strategic (6–12 months)
- Every recommendation is data-backed and cites a forecast or ratio
- Tools: `query_warehouse`, `get_top_tenants`, `forecast_mall_revenue` (ARIMA_PLUS + grounded 30-day total)

---

## Running locally

**Prerequisites:** Python 3.11+, `gcloud` CLI, and a GCP project with BigQuery + Vertex AI enabled.

```bash
git clone https://github.com/heemaniar/goldengate-retail-ai.git
cd goldengate-retail-ai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — fill in GCP project and Fivetran API key/secret

# Authenticate to GCP (needed for BigQuery + Vertex AI)
gcloud auth application-default login

# Generate synthetic data and load to BigQuery (first run only)
python simulate_data.py     # generates the source CSVs in data/
python load_bigquery.py     # CSV → BigQuery goldengate_core + trains ARIMA model

streamlit run app.py
# → http://localhost:8501
```

---

## Running tests

```bash
pip install pytest          # first time only
pytest -v                   # full suite
pytest -v tests/test_accuracy.py   # accuracy regression invariants
```

The accuracy suite hits BigQuery read-only and **skips** (rather than fails) if no GCP credentials are present, so it stays CI-friendly.

---

## Deploying to Cloud Run

```bash
# One command — builds with Cloud Build, deploys to Cloud Run
bash deploy_cloudrun.sh
```

The script creates the Artifact Registry repo (`goldengate-repo`), builds the image via Cloud Build (no local Docker needed), and deploys the `goldengate` Cloud Run service with env vars from `.env`. A separate Cloud Run Job + Cloud Scheduler keeps the warehouse refreshed daily.

---

## Project structure

```
goldengate-retail-ai/
├── agents/
│   └── mallpulse/
│       ├── agent.py          # Root orchestrator (goldengate)
│       └── sub_agents.py     # Data Unifier, Tenant Diagnoser, Action Recommender (+ Fivetran McpToolset)
├── tools/
│   └── bigquery_tools.py     # BQ query, mall summary, forecast (+ grounded total), weather correlation
├── vendors/
│   └── fivetran_mcp_server.py  # Bundled Fivetran MCP server (read-only)
├── tests/
│   └── test_accuracy.py      # Accuracy regression invariants
├── data/                     # Generated CSVs (gitignored)
├── app.py                    # Streamlit chat UI (Show SQL, mall selector)
├── simulate_data.py          # Synthetic Bay Area data generator
├── load_bigquery.py          # CSV → BigQuery loader + ARIMA model trainer
├── deploy_cloudrun.sh        # Cloud Run one-command deploy
├── Dockerfile
└── requirements.txt
```

---

## Hackathon

Built for the **[Google Cloud Rapid Agent Hackathon](https://googlecloudagents.devpost.com/)** — Fivetran track.

**Submission deadline:** June 11, 2026

---

## License

MIT — see [LICENSE](LICENSE)
