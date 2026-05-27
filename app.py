"""
app.py — MallPulse Streamlit Chat UI.

Local dev:
    streamlit run app.py

Cloud Run (prod):
    python deploy.py          # builds image + deploys
    OR: streamlit run app.py --server.port 8080

The UI talks directly to the ADK multi-agent system:
  root → data_unifier (BigQuery + Fivetran MCP)
       → tenant_diagnoser (BigQuery)
       → action_recommender (BigQuery + ML forecast)
"""

import asyncio
import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# ── Path & env setup ──────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "agents"))

load_dotenv(_ROOT / ".env")

from agents.mallpulse.agent import root_agent  # noqa: E402 (after path setup)

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="MallPulse",
    page_icon="🏬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Example prompts ───────────────────────────────────────────────────────────
EXAMPLE_PROMPTS = [
    ("📊 Revenue", "How many transactions did Kanyon have in March 2023?"),
    ("🏆 Top tenants", "Who are the top 5 tenants at Forum Istanbul by revenue?"),
    ("📋 Leases", "Which tenants have leases expiring in the next 6 months?"),
    ("🔁 Cross-mall", "Compare Zara's performance across all malls"),
    ("🌧️ Weather", "What was the weather impact on foot traffic at Kanyon in 2022?"),
    ("📈 Forecast", "Forecast next 30 days revenue for Kanyon"),
    ("🔌 Pipeline", "Is the Fivetran data pipeline healthy?"),
    ("✅ Actions", "What are the top 3 actions I should take this week at Kanyon?"),
]


# ── Runner bootstrap (cached across reruns and users) ─────────────────────────
# @st.cache_resource ensures the MCP subprocess and BigQuery client are
# initialised once per Cloud Run instance, not on every Streamlit rerun.
@st.cache_resource
def _get_runner() -> tuple[Runner, InMemorySessionService]:
    svc = InMemorySessionService()
    r = Runner(agent=root_agent, app_name="mallpulse", session_service=svc)
    return r, svc


runner, _svc = _get_runner()


def _get_session_id() -> str:
    """Return the current user's ADK session ID, creating one on first visit."""
    if "adk_session_id" not in st.session_state:
        session = asyncio.run(_svc.create_session(app_name="mallpulse", user_id="gm"))
        st.session_state.adk_session_id = session.id
        st.session_state.messages = []
    return st.session_state.adk_session_id


# ── Helpers ───────────────────────────────────────────────────────────────────
def _reset_conversation() -> None:
    """Clear chat history and start a fresh ADK session."""
    session = asyncio.run(_svc.create_session(app_name="mallpulse", user_id="gm"))
    st.session_state.adk_session_id = session.id
    st.session_state.messages = []
    st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏬 MallPulse")
    st.caption("Mall Operations Co-Pilot · Istanbul, Turkey")
    st.divider()

    st.markdown("### 💡 Example questions")
    for label, prompt_text in EXAMPLE_PROMPTS:
        if st.button(f"{label}", use_container_width=True, key=f"ex_{label}"):
            st.session_state.pending_prompt = prompt_text

    st.divider()
    st.markdown("### ℹ️ About")
    st.caption(
        "MallPulse analyses 267K+ transactions across 10 Istanbul malls "
        "(Jan 2020 – yesterday, updated daily). Data via **Fivetran → BigQuery**. "
        "Agents powered by **Gemini 2.5 Flash** on Google ADK."
    )
    st.divider()

    # ── Dashboard toggle ──────────────────────────────────────────────────────
    st.markdown("### 📊 Live Dashboard")
    dashboard_url = os.getenv("LOOKER_STUDIO_URL", "").strip()
    if dashboard_url:
        show_dash = st.toggle("Show Looker Studio dashboard", value=False)
        st.session_state.show_dashboard = show_dash
    else:
        st.caption("_Dashboard coming soon — set LOOKER\\_STUDIO\\_URL in .env_")
        st.session_state.show_dashboard = False

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        _reset_conversation()


# ── Dashboard embed (full width, above chat) ──────────────────────────────────
dashboard_url = os.getenv("LOOKER_STUDIO_URL", "").strip()
if st.session_state.get("show_dashboard") and dashboard_url:
    st.markdown("## 📊 Live Dashboard")
    components.iframe(dashboard_url, height=620, scrolling=True)
    st.divider()

# ── Main chat area ─────────────────────────────────────────────────────────────
st.markdown("# 🏬 MallPulse")
st.caption(
    "Ask about tenant performance, revenue trends, lease health, "
    "weather impact, forecasts, or Fivetran pipeline status."
)
st.divider()

# Render history
for msg in st.session_state.get("messages", []):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Resolve prompt — chat input OR sidebar example button
prompt = st.chat_input("Ask about a tenant, mall, or data freshness…")
if not prompt and "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

# Handle new message
if prompt:
    _get_session_id()  # ensure session exists before rendering
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        status_slot = st.empty()
        text_slot = st.empty()
        full_text = ""

        try:
            for event in runner.run(
                user_id="gm",
                session_id=st.session_state.adk_session_id,
                new_message=Content(parts=[Part(text=prompt)], role="user"),
            ):
                # Surface tool calls as live status
                calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
                if calls:
                    tool_names = ", ".join(f"`{c.name}`" for c in calls)
                    status_slot.caption(f"⚙️ Calling {tool_names}…")

                # Stream partial text as it arrives
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            full_text += part.text
                            text_slot.markdown(full_text + " ▌")

        except Exception as exc:
            full_text = f"⚠️ Something went wrong: {exc}"

        status_slot.empty()
        text_slot.markdown(full_text or "_(No response — try rephrasing your question.)_")

    st.session_state.messages.append({"role": "assistant", "content": full_text})
