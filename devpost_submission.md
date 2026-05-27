# MallPulse — Devpost Submission Draft
# Google Cloud Rapid Agent Hackathon · Fivetran Track
# Deadline: June 11, 2026 @ 10 AM PT
#
# Copy-paste each section into the Devpost form fields.
# Fields marked [REQUIRED] must be filled before submitting.

---

## PROJECT NAME
MallPulse

## TAGLINE (max 60 chars)
AI co-pilot for shopping mall operations — ask in English, act in data.

## DEMO URL [REQUIRED — paste before submitting]
https://mallpulse-3f3swnt3qq-uc.a.run.app

## VIDEO URL [REQUIRED — upload to YouTube/Loom, paste link]
[PASTE VIDEO URL HERE]

## GITHUB REPO [REQUIRED]
https://github.com/heemaniar/mallpulse

---

## INSPIRATION

Shopping mall General Managers in emerging markets manage 50–200 tenants across millions of square feet — yet most still rely on weekly Excel reports to make lease, event, and investment decisions. By the time a problem shows up in a report, it's already too late to act.

MallPulse was built to answer the question: *what if a GM could just ask?*

---

## WHAT IT DOES

MallPulse is a multi-agent AI co-pilot that gives Istanbul mall managers instant, data-backed answers to their most critical operational questions:

- **Revenue & transactions** — "How many transactions did Kanyon have in March 2023?"
- **Tenant rankings** — "Who are the top 5 tenants at Forum Istanbul by revenue?"
- **Lease risk** — "Which tenants have leases expiring in the next 6 months?"
- **Cross-mall comparisons** — "Compare Zara's performance across all 10 malls"
- **Weather impact** — "What was the rain impact on Kanyon foot traffic in 2022?"
- **30-day forecasts** — "Forecast next month's revenue for Kanyon"
- **Pipeline health** — "Is the Fivetran data pipeline healthy?"

Every answer is grounded in real warehouse data — the agent never makes up numbers.

---

## HOW WE BUILT IT

### Data pipeline
Raw Istanbul Mall transaction data (~99,458 rows, 10 malls, Jan 2020–Mar 2023) is loaded into **Cloud SQL Postgres**, then synced to **BigQuery** via **Fivetran**. A `prep_data.py` script augments the base dataset with synthetic tenant names, lease terms, Open-Meteo weather data, and Turkish public holidays.

### BigQuery warehouse
Eight tables in `mallpulse_core`:
- `fact_transactions` — raw purchase-level data
- `dim_mall`, `dim_tenant`, `dim_lease` — dimension tables
- `fact_weather` — daily temperature, rainfall, wind
- `agg_mall_daily`, `agg_tenant_daily` — pre-aggregated for fast portfolio queries
- `bqml_revenue_forecast` — ARIMA_PLUS 30-day forecast output

### Multi-agent system (Google ADK)
Built on **Google ADK 1.34** with **Gemini 2.5 Flash** on Vertex AI. The root orchestrator classifies each question and delegates to specialist sub-agents:

1. **Data Unifier** — pulls BigQuery data and monitors the Fivetran pipeline via the **Fivetran MCP server**. This is the hackathon's Fivetran-track integration: the MCP server exposes live connector health, last sync time, and schema configuration directly to the AI agent.

2. **Tenant Diagnoser** — classifies tenants as 🔴 Critical / 🟡 Watch / 🟢 Healthy using rent-to-sales ratio benchmarks by tenant format.

3. **Action Recommender** — produces a prioritised three-tier GM action list (this week / 1–3 months / 6–12 months), backed by ARIMA-Plus forecasts.

### UI & deployment
- **Streamlit** chat UI with dark theme, live tool-call status, and embedded Looker Studio dashboard
- Deployed to **Cloud Run** via Cloud Build (Dockerfile included)
- Looker Studio dashboard shows revenue trends (agg_mall_daily) and top tenants by revenue (agg_tenant_daily joined to dim_tenant)

---

## CHALLENGES WE RAN INTO

1. **Flat revenue forecasts** — BigQuery ML's ARIMA_PLUS returned a single flat line until we resampled dates with realistic seasonality (weekends ×1.40, December +30%, Turkish holidays ×1.50) in `prep_data.py`.

2. **Relative date reasoning** — "last quarter" in a 2026 chat session mapped to Q1 2026, not Q4 2022 (the dataset's most recent data). Fixed with an explicit date anchor in every sub-agent's system prompt: *"treat all relative dates as relative to 2023-03-08."*

3. **Fivetran MCP path for Cloud Run** — the MCP server runs as a subprocess. The local dev path (`~/code/fivetran-mcp/server.py`) doesn't exist inside a Docker container. Solved by vendoring `server.py` into `vendors/fivetran_mcp_server.py` and using a fallback path resolution in `sub_agents.py`.

4. **Looker Studio blend with dim_tenant** — the join key existed in both tables but Looker Studio wouldn't surface `dim_tenant` in the blend picker until it was added as a separate report-level data source first.

---

## ACCOMPLISHMENTS THAT WE'RE PROUD OF

- A GM can go from "Is Zara underperforming?" to a data-backed answer in under 10 seconds — with zero SQL knowledge
- The Fivetran MCP integration gives real-time pipeline visibility inside the AI conversation (not just a dashboard)
- The three-agent architecture separates *data retrieval*, *diagnosis*, and *recommendation* — each agent has a narrow scope and stays in its lane
- Every BigQuery query is generated at runtime by the agent, not hardcoded — genuinely generative analytics

---

## WHAT WE LEARNED

- Google ADK's `AgentTool` wrapper makes sub-agent composition surprisingly clean — far easier than building a router from scratch
- MCP servers (`McpToolset` + `StdioConnectionParams`) are a natural fit for agentic pipelines that need to talk to external APIs
- BigQuery ML's ARIMA_PLUS is powerful but needs careful data preparation — garbage in, flat forecast out
- Cloud Run cold starts with a full ML agent stack are tolerable (~3–5s) with `--min-instances=0` but worth pre-warming for demos

---

## WHAT'S NEXT FOR MALLPULSE

- **Real-time alerts** — push Pub/Sub notifications when a tenant's revenue drops >15% week-over-week
- **Multi-language support** — Turkish-language queries via Gemini's multilingual capability
- **Lease renewal workflow** — agent drafts a lease renegotiation memo when it flags a high rent-to-sales ratio
- **Expand beyond Istanbul** — the data model is mall-agnostic; any retail dataset with tenant + transaction data can slot in

---

## BUILT WITH

google-adk, gemini-2.5-flash, vertex-ai, bigquery, bigquery-ml, cloud-run, cloud-sql, fivetran, mcp, streamlit, looker-studio, artifact-registry, cloud-build, python

---

## TRACKS

- [x] Fivetran Track (Fivetran MCP server integrated into Data Unifier agent)

---

## TEAM

Heema Maniar

---

## CHECKLIST BEFORE SUBMITTING

- [ ] Video uploaded to YouTube/Loom — URL added above
- [ ] GitHub repo is PUBLIC at https://github.com/heemaniar/mallpulse
- [ ] GitHub repo "About" section shows MIT license (visible on repo homepage)
- [ ] Cloud Run demo URL is live and publicly accessible
- [ ] Devpost form: all required fields filled
- [ ] Devpost form: "Built With" tags match actual stack
- [ ] Devpost form: video embeds/plays correctly
- [ ] Submitted before June 11, 2026 @ 10 AM PT
