"""
app.py — GoldenGate Retail AI Streamlit Chat UI.

Local dev:
    streamlit run app.py

Cloud Run (prod):
    bash deploy_cloudrun.sh
    OR: streamlit run app.py --server.port 8080

The UI talks directly to the ADK multi-agent system:
  root (goldengate) → data_unifier (BigQuery + Fivetran MCP)
                    → tenant_diagnoser (BigQuery)
                    → action_recommender (BigQuery + ML forecast)

⚠️ All data is completely synthetic and generated for demonstration purposes.
"""

import asyncio
import os
import sys
import uuid
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
from tools.bigquery_tools import query_warehouse  # noqa: E402

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="GoldenGate Retail AI",
    page_icon="🌉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Fonts + comprehensive UI theme ───────────────────────────────────────────
# st.html() injects <style>/<link> into the parent document head (Streamlit 1.31+)
# Do NOT use st.markdown for CSS — it strips <style> tags in newer versions.
st.html("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/icon?family=Material+Icons+Round" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20,400,0,0" rel="stylesheet">
<style>
/* ── Typography ─────────────────────────────────────────────────────────── */
html, body, [class*="css"], p, span, div, li, td, th, label,
.stMarkdown, .stChatMessage { font-family:'Inter',-apple-system,sans-serif !important; }
h1,h2,h3,h4,h5,h6 { font-family:'Plus Jakarta Sans',sans-serif !important;
    font-weight:700 !important; color:#1A1735 !important; }

/* ── App background — Lavender ──────────────────────────────────────────── */
.stApp, body { background-color:#EEEDFE !important; }
.main .block-container { padding-top:1.5rem !important; }

/* ── Sidebar — stays dark purple ────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#150F2D 0%,#2D2156 100%) !important;
    border-right:1px solid rgba(83,74,183,0.35) !important;
}
[data-testid="stSidebar"] .block-container { padding-top:1.25rem !important; }
/* Sidebar text: force light on dark background */
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span,
[data-testid="stSidebar"] .stCaption { color:rgba(244,243,255,0.65) !important; }

/* ── Buttons — primary (Deep Purple gradient) ───────────────────────────── */
.stButton>button[kind="primary"] {
    background:linear-gradient(135deg,#3C3489 0%,#534AB7 100%) !important;
    color:#fff !important; border:none !important; border-radius:10px !important;
    font-weight:600 !important; font-family:'Inter',sans-serif !important;
    box-shadow:0 2px 10px rgba(60,52,137,0.25) !important;
    transition:all 0.2s !important;
}
.stButton>button[kind="primary"]:hover {
    transform:translateY(-1px) !important;
    box-shadow:0 6px 20px rgba(83,74,183,0.4) !important;
}
/* ── Buttons — sidebar quick-question buttons (dark bg) ─────────────────── */
[data-testid="stSidebar"] .stButton>button {
    background:rgba(60,52,137,0.28) !important;
    border:1px solid rgba(83,74,183,0.45) !important;
    border-radius:10px !important; color:rgba(244,243,255,0.88) !important;
    font-family:'Inter',sans-serif !important; font-size:0.85rem !important;
    transition:all 0.15s !important;
}
[data-testid="stSidebar"] .stButton>button:hover {
    background:rgba(83,74,183,0.4) !important;
    border-color:#534AB7 !important; color:#F4F3FF !important;
}
/* ── Buttons — main area (lavender bg) ──────────────────────────────────── */
.main .stButton>button {
    background:rgba(60,52,137,0.08) !important;
    border:1px solid rgba(83,74,183,0.3) !important;
    border-radius:10px !important; color:#3C3489 !important;
    font-family:'Inter',sans-serif !important; font-size:0.85rem !important;
    transition:all 0.15s !important;
}
.main .stButton>button:hover {
    background:rgba(83,74,183,0.14) !important;
    border-color:#534AB7 !important; color:#1A1735 !important;
}

/* ── Chat bubbles (on lavender) ─────────────────────────────────────────── */
[data-testid="stChatMessage"] { border-radius:14px !important; margin-bottom:6px !important; }
[data-testid="stChatMessage"][data-message-author-role="user"] {
    background:rgba(60,52,137,0.07) !important;
    border:1px solid rgba(83,74,183,0.18) !important;
}
[data-testid="stChatMessage"][data-message-author-role="assistant"] {
    background:rgba(255,255,255,0.68) !important;
    border:1px solid rgba(29,158,117,0.22) !important;
}

/* ── Chat input ─────────────────────────────────────────────────────────── */
[data-testid="stChatInputTextArea"] {
    background:rgba(255,255,255,0.82) !important;
    border:1px solid rgba(83,74,183,0.4) !important;
    border-radius:12px !important; color:#1A1735 !important;
}
[data-testid="stChatInputTextArea"]:focus-within {
    border-color:#534AB7 !important; box-shadow:0 0 0 2px rgba(83,74,183,0.15) !important;
}

/* ── Expanders ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background:rgba(255,255,255,0.55) !important;
    border:1px solid rgba(83,74,183,0.22) !important; border-radius:10px !important;
}
[data-testid="stExpander"] summary { color:#2D2156 !important; font-size:0.83rem !important; }

/* ── Code ───────────────────────────────────────────────────────────────── */
code,pre { background:#F0EFFE !important; border:1px solid rgba(83,74,183,0.18) !important; border-radius:7px !important; }
code { color:#1D9E75 !important; }

/* ── Tables ─────────────────────────────────────────────────────────────── */
table { background:rgba(255,255,255,0.5) !important; border-radius:8px !important; }
thead tr { background:rgba(60,52,137,0.08) !important; }
th { color:#1A1735 !important; font-family:'Plus Jakarta Sans',sans-serif !important; }
td { color:#1A1735 !important; }

/* ── Dividers ───────────────────────────────────────────────────────────── */
hr { border-color:rgba(83,74,183,0.18) !important; margin:0.6rem 0 !important; }

/* ── Caption / small ────────────────────────────────────────────────────── */
.stCaption,small { color:rgba(26,23,53,0.5) !important; font-size:0.77rem !important; }

/* ── Spinner ────────────────────────────────────────────────────────────── */
.stSpinner>div { border-top-color:#1D9E75 !important; }

/* ── Alert card (coral accent) ──────────────────────────────────────────── */
.alert-card {
    background:rgba(216,90,48,0.07); border-left:3px solid #D85A30;
    border-radius:0 8px 8px 0; padding:9px 14px; margin-bottom:6px;
    font-size:0.87rem; font-family:'Inter',sans-serif; color:#2D2156;
}

/* ── Tag / badge ────────────────────────────────────────────────────────── */
.tag-teal  { color:#1D9E75; font-weight:600; }
.tag-coral { color:#D85A30; font-weight:600; }
.tag-purple{ color:#534AB7; font-weight:600; }

/* ── Toggle — make visible on dark sidebar ──────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stToggle"] label {
    color:rgba(244,243,255,0.88) !important;
}
[data-testid="stSidebar"] [data-testid="stToggle"] p {
    color:rgba(244,243,255,0.88) !important;
}
[data-testid="stSidebar"] [role="switch"] {
    background-color:rgba(83,74,183,0.5) !important;
    border:1px solid rgba(83,74,183,0.8) !important;
}
[data-testid="stSidebar"] [role="switch"][aria-checked="true"] {
    background-color:#1D9E75 !important;
    border-color:#1D9E75 !important;
}

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width:5px; height:5px; }
::-webkit-scrollbar-track { background:#EEEDFE; }
::-webkit-scrollbar-thumb { background:#534AB7; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#3C3489; }

/* ── Hide Streamlit chrome ──────────────────────────────────────────────── */
#MainMenu,footer { visibility:hidden; }
</style>
""")

# ── Example prompts ───────────────────────────────────────────────────────────
EXAMPLE_PROMPTS = [
    ("↗ Revenue",     "How much revenue did Valley Fair generate last month?"),
    ("◈ Top tenants", "Who are the top 5 tenants at Stanford Shopping Center by revenue?"),
    ("⊘ Leases",      "Which tenants have leases expiring in the next 6 months?"),
    ("⇄ Cross-mall",  "Compare lululemon's performance across all Bay Area malls"),
    ("◌ Weather",     "What was the weather impact on foot traffic at Santana Row last quarter?"),
    ("⊕ Forecast",    "Forecast next 30 days revenue for Valley Fair"),
    ("⟳ Pipeline",    "Is the Fivetran data pipeline healthy?"),
    ("◎ Actions",     "What are the top 3 actions I should take this week at Valley Fair?"),
]


# ── Runner bootstrap (cached across reruns and users) ─────────────────────────
# @st.cache_resource ensures the MCP subprocess and BigQuery client are
# initialised once per Cloud Run instance, not on every Streamlit rerun.
@st.cache_resource
def _get_runner() -> tuple[Runner, InMemorySessionService]:
    svc = InMemorySessionService()
    r = Runner(agent=root_agent, app_name="goldengate", session_service=svc)
    return r, svc


runner, _svc = _get_runner()


def _get_user_id() -> str:
    """Return a unique user ID per browser session (multi-user safe)."""
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())[:8]
    return st.session_state.user_id


def _get_session_id() -> str:
    """Return the current user's ADK session ID, creating one on first visit."""
    if "adk_session_id" not in st.session_state:
        session = asyncio.run(
            _svc.create_session(app_name="goldengate", user_id=_get_user_id())
        )
        st.session_state.adk_session_id = session.id
        st.session_state.messages = []
    return st.session_state.adk_session_id


# ── Proactive anomaly alerts (cached 1 hour) ──────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _get_anomaly_alerts() -> list[str]:
    """Return top-5 tenants where annual rent is highest % of annual revenue."""
    try:
        # Uses 365-day window for stable annual revenue, then compares monthly/monthly.
        # Filters: effective_to >= today (active tenants), annual_rev >= 200K (not sparse).
        # No threshold — always returns the 5 most stressed tenants.
        result = query_warehouse("""
        SELECT
            t.tenant_name,
            m.mall_name,
            CAST(ROUND(l.monthly_base_rent) AS INT64)               AS monthly_rent,
            CAST(ROUND(a.annual_rev / 12) AS INT64)                 AS monthly_rev_avg,
            ROUND(l.monthly_base_rent * 12 / a.annual_rev * 100, 1) AS rent_to_sales_pct
        FROM (
            SELECT tenant_id, SUM(revenue) AS annual_rev
            FROM `mallpulse-hackathon.goldengate_core.agg_tenant_daily`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY)
            GROUP BY tenant_id
        ) a
        JOIN `mallpulse-hackathon.goldengate_core.dim_tenant` t ON t.tenant_id = a.tenant_id
        JOIN `mallpulse-hackathon.goldengate_core.dim_mall`   m ON m.mall_id = t.mall_id
        JOIN `mallpulse-hackathon.goldengate_core.dim_lease`  l ON l.tenant_id = a.tenant_id
        WHERE t.effective_to >= CURRENT_DATE()
          AND a.annual_rev >= 50000
          AND rent_to_sales_pct > 12
        ORDER BY rent_to_sales_pct DESC
        LIMIT 5
        """)
        if "BigQuery error" in result or "returned no rows" in result.lower():
            return []
        alerts = []
        for line in result.strip().split("\n")[2:]:  # skip header + separator rows
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 5:
                try:
                    name = parts[0]
                    mall = parts[1]
                    rent = int(parts[2].replace(",", ""))
                    rev  = int(parts[3].replace(",", ""))
                    pct  = float(parts[4])
                    alerts.append(
                        f"🚨 **{name}** at {mall} — "
                        f"rent ${rent:,} vs avg rev ${rev:,}/mo "
                        f"(**{pct:.0f}% rent-to-sales**)"
                    )
                except (ValueError, IndexError):
                    pass
        return alerts
    except Exception:
        return []


# ── Helpers ───────────────────────────────────────────────────────────────────
def _reset_conversation() -> None:
    """Clear chat history and start a fresh ADK session."""
    session = asyncio.run(
        _svc.create_session(app_name="goldengate", user_id=_get_user_id())
    )
    st.session_state.adk_session_id = session.id
    st.session_state.messages = []
    st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style="padding:4px 0 18px;">
  <div style="display:flex;align-items:center;gap:11px;">
    <div style="width:40px;height:40px;background:linear-gradient(135deg,#3C3489 0%,#1D9E75 100%);
         border-radius:11px;display:flex;align-items:center;justify-content:center;
         font-size:20px;box-shadow:0 3px 12px rgba(60,52,137,0.45);flex-shrink:0;">🌉</div>
    <div>
      <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:1.05rem;
           font-weight:800;color:#F4F3FF;line-height:1.15;letter-spacing:-0.3px;">GoldenGate Retail AI</div>
      <div style="font-size:0.68rem;color:#1D9E75;font-weight:600;letter-spacing:0.6px;
           font-family:'Inter',sans-serif;text-transform:uppercase;">Bay Area Retail Intelligence</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<p style="font-size:0.72rem;color:#D85A30;font-weight:700;letter-spacing:0.9px;text-transform:uppercase;margin:0 0 8px;font-family:\'Inter\',sans-serif;">Quick questions</p>', unsafe_allow_html=True)
    for label, prompt_text in EXAMPLE_PROMPTS:
        if st.button(label, use_container_width=True, key=f"ex_{label}"):
            st.session_state.pending_prompt = prompt_text

    st.divider()
    st.markdown("""
<p style="font-size:0.72rem;color:rgba(244,243,255,0.45);font-weight:600;letter-spacing:0.8px;
text-transform:uppercase;margin:0 0 6px;font-family:'Inter',sans-serif;">About</p>
<p style="font-size:0.8rem;color:rgba(244,243,255,0.6);line-height:1.55;font-family:'Inter',sans-serif;margin:0;">
1M+ transactions · 13 Bay Area malls<br>
Jan 2020 – yesterday · updated daily<br>
<span style="color:#1D9E75;font-weight:500;">Fivetran → BigQuery</span> ·
<span style="color:#534AB7;font-weight:500;">Gemini 3</span> on Google ADK
</p>
<p style="font-size:0.72rem;color:rgba(244,243,255,0.3);margin:10px 0 0;font-family:'Inter',sans-serif;font-style:italic;">
⚠️ All data is synthetic — for demo purposes only.
</p>
""", unsafe_allow_html=True)

    st.divider()

    # ── Dashboard toggle ──────────────────────────────────────────────────────
    st.markdown('<p style="font-size:0.72rem;color:rgba(244,243,255,0.45);font-weight:600;letter-spacing:0.8px;text-transform:uppercase;margin:0 0 8px;font-family:\'Inter\',sans-serif;">Live Dashboard</p>', unsafe_allow_html=True)
    dashboard_url = os.getenv("LOOKER_STUDIO_URL", "").strip()
    if dashboard_url:
        show_dash = st.toggle("Show Looker Studio", value=False)
        st.session_state.show_dashboard = show_dash
    else:
        st.caption("Set LOOKER\\_STUDIO\\_URL to enable")
        st.session_state.show_dashboard = False

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        _reset_conversation()


# ── Dashboard embed (full width, above chat) ──────────────────────────────────
dashboard_url = os.getenv("LOOKER_STUDIO_URL", "").strip()
if st.session_state.get("show_dashboard") and dashboard_url:
    st.markdown("## 📊 Live Dashboard")
    components.iframe(dashboard_url, height=620, scrolling=True)
    st.divider()

# ── Main header ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:center;gap:14px;padding:4px 0 6px;">
  <div style="width:52px;height:52px;background:linear-gradient(135deg,#3C3489 0%,#1D9E75 100%);
       border-radius:14px;display:flex;align-items:center;justify-content:center;
       font-size:26px;box-shadow:0 4px 18px rgba(60,52,137,0.35);flex-shrink:0;">🌉</div>
  <div>
    <div style="font-family:'Plus Jakarta Sans',sans-serif;font-size:2rem;font-weight:800;
         color:#1A1735;line-height:1.1;letter-spacing:-0.8px;">GoldenGate Retail AI</div>
    <div style="font-size:0.78rem;color:rgba(26,23,53,0.5);font-weight:500;
         font-family:'Inter',sans-serif;letter-spacing:0.2px;">
      Tenant performance · Revenue trends · Lease health · Forecasts
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Proactive anomaly alerts ──────────────────────────────────────────────────
alerts = _get_anomaly_alerts()
if alerts:
    st.markdown("**⚠️ Alerts — High rent-to-sales tenants**")
    for alert in alerts:
        st.markdown(f'<div class="alert-card">{alert}</div>', unsafe_allow_html=True)

st.divider()

_AVATAR = {"user": "🧑‍💼", "assistant": "🌉"}

# Render history
for msg in st.session_state.get("messages", []):
    with st.chat_message(msg["role"], avatar=_AVATAR.get(msg["role"])):
        st.markdown(msg["content"])

# Resolve prompt — chat input OR sidebar example button
prompt = st.chat_input("Ask about Valley Fair, Stanford, Santana Row…")
if not prompt and "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

# Handle new message
if prompt:
    _get_session_id()  # ensure session exists before rendering

    # Guard against double-render on sidebar button click mid-conversation
    msgs = st.session_state.get("messages", [])
    if not msgs or msgs[-1].get("content") != prompt or msgs[-1].get("role") != "user":
        st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🌉"):
        status_slot = st.empty()
        text_slot = st.empty()
        full_text = ""

        try:
            for event in runner.run(
                user_id=_get_user_id(),
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
            err = str(exc).lower()
            if "quota" in err or "rate" in err:
                full_text = "⚠️ Query limit reached — please try again in a moment."
            elif "bigquery" in err or "google.api" in err:
                full_text = "⚠️ Data warehouse is temporarily unavailable. Historical data is still intact."
            elif "fivetran" in err:
                full_text = "⚠️ Fivetran pipeline is unreachable. BigQuery data from the last sync is still available."
            else:
                full_text = "⚠️ Something went wrong. Try rephrasing your question."

        status_slot.empty()
        text_slot.markdown(full_text or "_(No response — try rephrasing your question.)_")

    st.session_state.messages.append({"role": "assistant", "content": full_text})
