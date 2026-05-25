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
import sys
from pathlib import Path

import streamlit as st
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


# ── Session bootstrap ─────────────────────────────────────────────────────────
def _bootstrap_session() -> tuple[Runner, str]:
    """Create ADK session and runner exactly once; store in st.session_state."""
    if "adk_runner" not in st.session_state:
        svc = InMemorySessionService()
        session = asyncio.run(
            svc.create_session(app_name="mallpulse", user_id="gm")
        )
        st.session_state.adk_svc = svc
        st.session_state.adk_session_id = session.id
        st.session_state.adk_runner = Runner(
            agent=root_agent,
            app_name="mallpulse",
            session_service=svc,
        )
        st.session_state.messages = []

    return st.session_state.adk_runner, st.session_state.adk_session_id


runner, session_id = _bootstrap_session()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _reset_conversation() -> None:
    """Clear chat history and start a fresh ADK session."""
    session = asyncio.run(
        st.session_state.adk_svc.create_session(app_name="mallpulse", user_id="gm")
    )
    st.session_state.adk_session_id = session.id
    st.session_state.messages = []
    st.rerun()


def _run_agent(prompt: str) -> str:
    """
    Send a prompt through the ADK multi-agent pipeline.

    Uses Runner.run() (sync generator) so we can surface live tool-call
    status in the UI while the agent thinks.

    Returns the final response text.
    """
    status = st.empty()
    full_text = ""

    try:
        for event in runner.run(
            user_id="gm",
            session_id=st.session_state.adk_session_id,
            new_message=Content(parts=[Part(text=prompt)], role="user"),
        ):
            # Surface tool calls as live status so the user sees progress
            calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
            if calls:
                tool_names = ", ".join(f"`{c.name}`" for c in calls)
                status.caption(f"⚙️ Calling {tool_names}…")

            # Capture final response
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if part.text:
                        full_text += part.text

    except Exception as exc:
        status.empty()
        return f"⚠️ Something went wrong: {exc}"

    status.empty()
    return full_text or "_(No response — try rephrasing your question.)_"


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
        "MallPulse analyses 99K+ transactions across 10 Istanbul malls "
        "(Jan 2020 – Mar 2023). Data via **Fivetran → BigQuery**. "
        "Agents powered by **Gemini 2.5 Flash** on Google ADK."
    )
    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        _reset_conversation()


# ── Main chat area ─────────────────────────────────────────────────────────────
st.markdown("# 🏬 MallPulse")
st.caption(
    "Ask about tenant performance, revenue trends, lease health, "
    "weather impact, forecasts, or Fivetran pipeline status."
)
st.divider()

# Render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Resolve prompt — chat input OR sidebar example button
prompt = st.chat_input("Ask about a tenant, mall, or data freshness…")
if not prompt and "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

# Handle new message
if prompt:
    # Show user bubble
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream agent response
    with st.chat_message("assistant"):
        with st.spinner("MallPulse is thinking…"):
            response = _run_agent(prompt)
        st.markdown(response)

    st.session_state.messages.append({"role": "assistant", "content": response})
