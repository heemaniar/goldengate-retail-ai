# 🌉 GoldenGate Retail AI

**AI Co-Pilot for Bay Area Shopping Mall General Managers**

> ⚠️ **All data in this project is completely synthetic and generated for demonstration purposes only.** Revenue figures, transaction data, tenant names, and performance metrics are fictitious. Real brand names are used solely to make the demo realistic and are not associated with any actual business data.

GoldenGate Retail AI is a multi-agent AI system that turns raw retail data into instant, actionable intelligence. Mall GMs can ask natural-language questions about tenant performance, revenue trends, lease health, weather impact, and 30-day revenue forecasts — and get data-backed answers in seconds.

**🔗 Live demo:** https://goldengate-3f3swnt3qq-uc.a.run.app

---

## What it does

| Ask this… | GoldenGate answers with… | Agent |
|---|---|---|
| *"How much revenue did Valley Fair generate last month?"* | Exact total + daily trend from BigQuery | Data Unifier |
| *"Give me a summary of Stanford Shopping Center's performance"* | Total, avg daily, peak, trading days | Data Unifier |
| *"Which Bay Area mall had the highest revenue in 2024?"* | Ranked portfolio table | Data Unifier |
| *"What was the weather impact on foot traffic at Santana Row?"* | Visits by weather bucket + temperature band | Data Unifier |
| *"Is the Fivetran data pipeline healthy?"* | Live sync status from Fivetran API | Data Unifier |
| *"Who are the top 5 tenants at Stanford by revenue?"* | Ranked table with $ totals | Tenant Diagnoser |
| *"Which tenants have leases expiring in the next 6 months?"* | Risk-flagged list with rent-to-sales ratios | Tenant Diagnoser |
| *"How does lululemon perform across all Bay Area malls?"* | Per-location revenue breakdown | Tenant Diagnoser |
| *"Forecast next 30 days revenue for Valley Fair"* | ARIMA-Plus daily forecast with 90% CI | Action Recommender |
| *"What are the top 3 actions I should take this week at Valley Fair?"* | Prioritised actions backed by data | Action Recommender |
| *"What is the customer age breakdown at Great Mall?"* | Demographics by age band | Data Unifier |

---

## Architecture

```
User (Streamlit chat UI)
        │
        ▼
┌──────────────────────────────────────────────────────┐
│         Root Orchestrator — goldengate               │
│         (Gemini 3 Flash Preview, Vertex AI global)   │
│  Routes intent → one or more specialist sub-agents   │
└──────┬─────────────────┬──────────────────┬──────────┘
       │                 │                  │
       ▼                 ▼                  ▼
┌────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Data      │  │  Tenant         │  │  Action         │
│  Unifier   │  │  Diagnoser      │  │  Recommender    │
│            │  │                 │  │                 │
│ BigQuery   │  │ BigQuery        │  │ BigQuery        │
│ Fivetran   │  │ rent-to-sales   │  │ ARIMA-Plus      │
│ MCP Server │  │ lease risk      │  │ forecast        │
└────────────┘  └─────────────────┘  └─────────────────┘
       │
       ▼
┌───────────────────────────────────────────────────────┐
│                   Data Layer                          │
│  Fivetran → BigQuery (goldengate_core)                │
│  fact_transactions · dim_tenant · dim_mall            │
│  dim_lease · fact_weather · fact_foot_traffic         │
│  agg_mall_daily · agg_tenant_daily · revenue_forecast │
└───────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Technology |
|---|---|
| **AI agents** | Google ADK 1.34, Gemini 3 Flash Preview (Vertex AI global) |
| **Orchestration** | Root agent → 3 specialist sub-agents via `AgentTool` |
| **Pipeline tools** | Fivetran MCP server (live pipeline monitoring) |
| **Data warehouse** | BigQuery (`goldengate_core` dataset, 9 tables + ML model) |
| **ML forecasting** | BigQuery ML `ARIMA_PLUS` (30-day revenue forecasts, US holidays) |
| **UI** | Streamlit (lavender theme, live tool-call status) |
| **Dashboard** | Looker Studio (revenue trends, tenant bar chart) |
| **Deployment** | Cloud Run (container, port 8080) |
| **Container registry** | Artifact Registry (`goldengate-repo`) |

---

## Dataset

- **Coverage:** 13 Bay Area malls (San Jose → San Francisco → Livermore), January 2020 – present
- **Volume:** 1M+ synthetic transactions across 500+ tenants
- **Real-world events modeled:** COVID-19 lockdown (Mar–Jun 2020), 2020 wildfire smoke, supply chain crunch (2021–2022), tech layoffs (2022–2023), Westfield SF Centre closure (Aug 2023), atmospheric rivers (Dec 2022–Mar 2023), Bay Area recovery (2024–2026)
- **Brands:** Real Bay Area brands (Philz Coffee, Blue Bottle, Boudin Bakery, lululemon, etc.) used with clear synthetic data disclaimer
- **Weather:** Bay Area–accurate patterns (SF fog, Livermore heat waves, atmospheric river rain events)
- **Generation:** `simulate_data.py` produces 8 CSVs → `load_bigquery.py` loads to BigQuery + retrains ARIMA model

> ⚠️ **Synthetic data disclaimer:** All transaction figures, revenue numbers, tenant performance data, and business metrics in this dataset are completely fictitious and generated algorithmically. Real brand names are referenced purely for demo realism. No actual business or financial data is represented.

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

---

## Three specialist agents

### 1 · Data Unifier
Retrieves raw data from BigQuery and monitors the Fivetran pipeline.
- Tools: `query_warehouse`, `get_mall_summary`, `get_weather_traffic_correlation`
- MCP: Fivetran REST API (connector health, last sync time, schema config)

### 2 · Tenant Diagnoser
Flags at-risk tenants and surfaces lease + revenue signals.
- Classifies tenants: 🔴 Critical / 🟡 Watch / 🟢 Healthy
- Bay Area rent-to-sales benchmarks by format (kiosk, inline, anchor, luxury, etc.)
- Tools: `query_warehouse`, `get_top_tenants`

### 3 · Action Recommender
Translates data insights into a prioritised GM action list.
- Three tiers: Immediate (this week) / Short-term (1–3 months) / Strategic (6–12 months)
- Every recommendation is data-backed and cites a forecast or ratio
- Tools: `query_warehouse`, `get_top_tenants`, `forecast_mall_revenue`

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
# Edit .env — fill in GCP project and Fivetran API key

# Authenticate to GCP (needed for BigQuery + Vertex AI)
gcloud auth application-default login

# Generate synthetic data and load to BigQuery (first run only)
python simulate_data.py     # generates 8 CSVs in data/
python load_bigquery.py     # CSV → BigQuery goldengate_core + retrains ARIMA model

streamlit run app.py
# → http://localhost:8501
```

---

## Running tests

```bash
pip install pytest          # first time only
pytest -v                   # runs all tests (no PYTHONPATH export needed)
```

---

## Deploying to Cloud Run

```bash
# One command — builds with Cloud Build, deploys to Cloud Run
bash deploy_cloudrun.sh
```

The script:
1. Creates an Artifact Registry repo (`goldengate-repo`)
2. Builds the Docker image via Cloud Build (no local Docker needed)
3. Deploys to Cloud Run service `goldengate` with all env vars from `.env`

---

## Project structure

```
goldengate-retail-ai/
├── agents/
│   └── mallpulse/
│       ├── agent.py          # Root orchestrator (goldengate)
│       └── sub_agents.py     # Data Unifier, Tenant Diagnoser, Action Recommender
├── tools/
│   └── bigquery_tools.py     # BQ query, mall summary, forecast, weather correlation
├── vendors/
│   └── fivetran_mcp_server.py  # Bundled Fivetran MCP server
├── data/                     # Generated CSVs (gitignored)
├── app.py                    # Streamlit chat UI
├── simulate_data.py          # Synthetic Bay Area data generator
├── load_bigquery.py          # CSV → BigQuery loader + ARIMA model trainer
├── deploy_cloudrun.sh        # Cloud Run one-command deploy
├── Dockerfile                # Container definition
└── requirements.txt          # Python dependencies
```

---

## Hackathon

Built for the **[Google Cloud Rapid Agent Hackathon](https://googlecloudagents.devpost.com/)** — Fivetran track.

**Submission deadline:** June 11, 2026

---

## License

MIT — see [LICENSE](LICENSE)
