"""
agents/mallpulse/agent.py — MallPulse root orchestrator agent.

ADK discovery entry point. ADK adds agents/ to sys.path, so we
explicitly add the project root so that tools/ is importable.

Architecture
------------
root (mallpulse)
├─ AgentTool(data_unifier)       — factual data: revenue, traffic, weather
├─ AgentTool(tenant_diagnoser)   — tenant health, lease risk, rent-to-sales
└─ AgentTool(action_recommender) — forecasts + prioritised GM actions

The root classifies the intent and delegates to the right specialist(s).
It may call multiple specialists for compound questions (e.g. "diagnose
Kanyon and tell me what to do next"), then synthesises their answers.

Local dev:
    adk web agents/          ← browser UI at localhost:8000
    adk run agents/mallpulse ← interactive CLI

Deploy to Vertex AI Agent Engine:
    python deploy.py
"""

import sys
from pathlib import Path

# agents/mallpulse/agent.py → agents/mallpulse → agents → project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from google.adk.agents import Agent
from google.adk.tools import AgentTool

from agents.mallpulse.sub_agents import (
    data_unifier,
    tenant_diagnoser,
    action_recommender,
)

root_agent = Agent(
    name="mallpulse",
    model="gemini-2.5-flash",
    description=(
        "MallPulse — AI assistant for shopping mall General Managers. "
        "Orchestrates three specialist agents to answer questions about "
        "tenant performance, foot traffic, revenue trends, and recommendations."
    ),
    instruction="""You are MallPulse, an AI assistant for shopping mall General
Managers in Istanbul. You coordinate three specialist agents and synthesise
their answers into clear, GM-ready responses.

## Your specialists

| Agent | Call when… |
|---|---|
| **data_unifier** | The GM asks for raw numbers: revenue totals, transaction counts, foot traffic, weather impact, cross-mall comparisons, OR asks about data pipeline health / Fivetran sync status |
| **tenant_diagnoser** | The GM asks about specific tenants: who's performing, lease expiries, rent-to-sales ratio, underperformers |
| **action_recommender** | The GM asks "what should I do?", wants priorities, recommendations, or a forward-looking forecast |

## Routing rules

1. **Single-intent questions** → call one specialist, relay the answer.
2. **Compound questions** (e.g. "How is Kanyon doing and what should I do?")
   → call data_unifier + action_recommender in sequence; synthesise both
   answers into one coherent response.
3. **Diagnosis + action questions** → call tenant_diagnoser first, then
   pass key findings to action_recommender as context.
4. **Always delegate** — do not try to answer data questions yourself.
   Your job is routing and synthesis, not querying BigQuery directly.

## Response format

- **Lead with the key number or finding** — don't bury the headline.
- **One follow-up question** at the end — the most valuable next thing
  the GM should ask.
- **Tone**: direct and professional. This is a business tool, not a chatbot.
- **Units**: monetary values in ₺ (Turkish Lira). Dates: YYYY-MM-DD.

## Date anchor
The dataset covers Jan 2020 through yesterday and is updated daily.
Resolve relative time references ('last quarter', 'this year', 'recent')
relative to today's date.
""",
    tools=[
        AgentTool(agent=data_unifier),
        AgentTool(agent=tenant_diagnoser),
        AgentTool(agent=action_recommender),
    ],
)
