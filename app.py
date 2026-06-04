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
from tools.bigquery_tools import (  # noqa: E402
    query_warehouse,
    reset_executed_sql,
    get_executed_sql,
)

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
<style>
/* ── Typography ─────────────────────────────────────────────────────────── */
/* NOTE: exclude <span> — Streamlit uses Material Symbols spans for expander
   icons; forcing Inter on them corrupts glyph rendering (shows raw ligature text) */
html, body, [class*="css"], p, div, li, td, th, label,
.stMarkdown, .stChatMessage { font-family:'Inter',-apple-system,sans-serif !important; }
h1,h2,h3,h4,h5,h6 { font-family:'Plus Jakarta Sans',sans-serif !important;
    font-weight:700 !important; color:#1A1735 !important; }

/* ── App background — Lavender ──────────────────────────────────────────── */
.stApp, body { background-color:#EEEDFE !important; }
.main .block-container { padding-top:1.5rem !important; }

/* ── Sidebar — light lavender ────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background:#E8E6FC !important;
    border-right:1px solid rgba(60,52,137,0.15) !important;
}
[data-testid="stSidebar"] .block-container { padding-top:1.25rem !important; }
/* Sidebar text: dark on light background */
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span,
[data-testid="stSidebar"] .stCaption { color:#3C3489 !important; }

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
/* ── Buttons — sidebar quick-question buttons (light bg) ────────────────── */
[data-testid="stSidebar"] .stButton>button {
    background:#3C3489 !important;
    border:1px solid #3C3489 !important;
    border-radius:10px !important; color:#FFFFFF !important;
    font-family:'Inter',sans-serif !important; font-size:0.85rem !important;
    font-weight:500 !important;
    transition:all 0.15s !important;
}
[data-testid="stSidebar"] .stButton>button:hover {
    background:#2D2568 !important;
    border-color:#2D2568 !important; color:#FFFFFF !important;
    transform:translateY(-1px) !important;
    box-shadow:0 4px 12px rgba(60,52,137,0.3) !important;
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

/* ── Toggle — visible on light sidebar ──────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stToggle"] label {
    color:#3C3489 !important;
}
[data-testid="stSidebar"] [data-testid="stToggle"] p {
    color:#3C3489 !important;
}
[data-testid="stSidebar"] [role="switch"] {
    background-color:rgba(60,52,137,0.3) !important;
    border:1px solid rgba(60,52,137,0.5) !important;
}
[data-testid="stSidebar"] [role="switch"][aria-checked="true"] {
    background-color:#1D9E75 !important;
    border-color:#1D9E75 !important;
}

/* ── Sidebar selectbox (mall filter) ───────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background:#fff !important;
    border:1px solid rgba(60,52,137,0.35) !important;
    border-radius:9px !important;
    color:#3C3489 !important;
    font-family:'Inter',sans-serif !important;
    font-size:0.85rem !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg { fill:#3C3489 !important; }

/* ── Scrollbar ──────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width:5px; height:5px; }
::-webkit-scrollbar-track { background:#EEEDFE; }
::-webkit-scrollbar-thumb { background:#534AB7; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#3C3489; }

/* ── Hide Streamlit chrome ──────────────────────────────────────────────── */
#MainMenu,footer { visibility:hidden; }
</style>
""")

# ── Mall selector ────────────────────────────────────────────────────────────
MALL_OPTIONS = [
    "— All Malls —",
    "Westfield Valley Fair",
    "Stanford Shopping Center",
    "Santana Row",
    "Stonestown Galleria",
    "Bay Street Emeryville",
    "Great Mall",
    "Hillsdale Shopping Center",
    "Stoneridge Shopping Center",
    "Broadway Plaza",
    "Sunvalley Shopping Center",
    "Westfield Oakridge",
    "San Francisco Premium Outlets",
    "Westfield San Francisco Centre (historical)",
]


def _make_prompts(mall: str) -> list[tuple[str, str]]:
    """Return sidebar quick-question prompts scoped to the selected mall.
    When 'All Malls' is selected each question targets a different mall so
    the set stays varied and interesting.
    """
    if mall and mall != "— All Malls —":
        m = mall.replace(" (historical)", "")
        return [
            ("💰 Revenue",     f"How much revenue did {m} generate last month?"),
            ("🛍️ Top tenants", f"Who are the top 5 tenants at {m} by revenue?"),
            ("🔑 Leases",      f"Which tenants at {m} have leases expiring in the next 6 months?"),
            ("🗺️ Cross-mall",  f"How does {m} compare to other Bay Area malls this year?"),
            ("🌦️ Weather",     f"What was the weather impact on foot traffic at {m} last quarter?"),
            ("📉 Forecast",    f"Forecast next 30 days revenue for {m}"),
            ("⚙️ Pipeline",    "Is the Fivetran data pipeline healthy?"),
            ("⚡ Actions",     f"What are the top 3 actions I should take this week at {m}?"),
        ]
    else:
        return [
            ("💰 Revenue",     "How much revenue did Westfield Valley Fair generate last month?"),
            ("🛍️ Top tenants", "Who are the top 5 tenants at Stanford Shopping Center by revenue?"),
            ("🔑 Leases",      "Which tenants at Santana Row have leases expiring in the next 6 months?"),
            ("🗺️ Cross-mall",  "Compare lululemon's performance across all Bay Area malls"),
            ("🌦️ Weather",     "What was the weather impact on foot traffic at Bay Street Emeryville last quarter?"),
            ("📉 Forecast",    "Forecast next 30 days revenue for Broadway Plaza"),
            ("⚙️ Pipeline",    "Is the Fivetran data pipeline healthy?"),
            ("⚡ Actions",     "What are the top 3 actions I should take this week at Stoneridge Shopping Center?"),
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


# ── Top 3 action items (cached 2 hours) ──────────────────────────────────────
@st.cache_data(ttl=7200, show_spinner=False)
def _get_top_actions() -> list[dict]:
    """Return up to 3 proactive action items from live BigQuery data."""
    actions = []

    # 1. Most urgent lease expiry (next 90 days)
    try:
        r = query_warehouse("""
        SELECT t.tenant_name, m.mall_name, l.lease_end_date,
               DATE_DIFF(l.lease_end_date, CURRENT_DATE(), DAY) AS days_left
        FROM `mallpulse-hackathon.goldengate_core.dim_lease` l
        JOIN `mallpulse-hackathon.goldengate_core.dim_tenant` t USING (tenant_id)
        JOIN `mallpulse-hackathon.goldengate_core.dim_mall`   m ON m.mall_id = t.mall_id
        WHERE l.lease_end_date BETWEEN CURRENT_DATE()
              AND DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
          AND t.effective_to >= CURRENT_DATE()
        ORDER BY l.lease_end_date LIMIT 1
        """)
        if "BigQuery error" not in r and "no rows" not in r.lower():
            for line in r.strip().split("\n")[2:]:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 4:
                    actions.append({
                        "icon": "🔴",
                        "label": "Urgent lease",
                        "title": f"Renew **{parts[0]}** at {parts[1]}",
                        "detail": f"Lease expires in **{parts[3]} days** ({parts[2]})",
                        "prompt": f"What should I do about the upcoming lease for {parts[0]} at {parts[1]}?",
                    })
                    break
    except Exception:
        pass

    # 2. Biggest revenue decline month-over-month
    try:
        r = query_warehouse("""
        SELECT t.tenant_name, m.mall_name,
               ROUND(SUM(CASE WHEN a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                              THEN a.revenue ELSE 0 END), 0) AS rev_now,
               ROUND(SUM(CASE WHEN a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
                               AND a.date  <  DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                              THEN a.revenue ELSE 0 END), 0) AS rev_prev,
               ROUND((SUM(CASE WHEN a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                               THEN a.revenue ELSE 0 END)
                     - SUM(CASE WHEN a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
                                 AND a.date  <  DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                               THEN a.revenue ELSE 0 END))
                    / NULLIF(SUM(CASE WHEN a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
                                      AND a.date  <  DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                                     THEN a.revenue ELSE 0 END), 0) * 100, 1) AS pct_chg
        FROM `mallpulse-hackathon.goldengate_core.agg_tenant_daily` a
        JOIN `mallpulse-hackathon.goldengate_core.dim_tenant` t ON t.tenant_id = a.tenant_id
        JOIN `mallpulse-hackathon.goldengate_core.dim_mall`   m ON m.mall_id = a.mall_id
        WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 60 DAY)
          AND t.effective_to >= CURRENT_DATE()
          AND a.mall_id != 'm04'
        GROUP BY t.tenant_name, m.mall_name
        HAVING rev_prev > 500 AND pct_chg < -10
        ORDER BY pct_chg ASC LIMIT 1
        """)
        if "BigQuery error" not in r and "no rows" not in r.lower():
            for line in r.strip().split("\n")[2:]:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 5:
                    actions.append({
                        "icon": "🟡",
                        "label": "Revenue watch",
                        "title": f"Investigate **{parts[0]}** at {parts[1]}",
                        "detail": f"Revenue down **{parts[4]}%** vs prior 30 days",
                        "prompt": f"Why is {parts[0]} at {parts[1]} underperforming and what should I do?",
                    })
                    break
    except Exception:
        pass

    # 3. Top revenue mall last month (opportunity to reinforce)
    try:
        r = query_warehouse("""
        SELECT m.mall_name, ROUND(SUM(a.total_revenue), 0) AS rev
        FROM `mallpulse-hackathon.goldengate_core.agg_mall_daily` a
        JOIN `mallpulse-hackathon.goldengate_core.dim_mall` m ON m.mall_id = a.mall_id
        WHERE a.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
          AND a.mall_id != 'm04'
        GROUP BY m.mall_name ORDER BY rev DESC LIMIT 1
        """)
        if "BigQuery error" not in r and "no rows" not in r.lower():
            for line in r.strip().split("\n")[2:]:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    rev_fmt = f"${int(parts[1].replace(',','')):,}" if parts[1].replace(',','').isdigit() else parts[1]
                    actions.append({
                        "icon": "🟢",
                        "label": "Top performer",
                        "title": f"Maximise **{parts[0]}** momentum",
                        "detail": f"Leading portfolio last month at **{rev_fmt}**",
                        "prompt": f"What are the top 3 actions I should take this week at {parts[0]}?",
                    })
                    break
    except Exception:
        pass

    return actions


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
           font-weight:800;color:#3C3489;line-height:1.15;letter-spacing:-0.3px;">GoldenGate Retail AI</div>
      <div style="font-size:0.68rem;color:#1D9E75;font-weight:600;letter-spacing:0.6px;
           font-family:'Inter',sans-serif;text-transform:uppercase;">Bay Area Retail Intelligence</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Mall filter ───────────────────────────────────────────────────────────
    st.markdown('<p style="font-size:0.72rem;color:#D85A30;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;margin:0 0 6px;font-family:\'Inter\',sans-serif;">Filter by Mall</p>', unsafe_allow_html=True)
    selected_mall = st.selectbox(
        "mall_selector",
        options=MALL_OPTIONS,
        index=0,
        label_visibility="collapsed",
        key="selected_mall",
    )

    # Subtle badge when a mall is active
    if selected_mall != "— All Malls —":
        mall_display = selected_mall.replace(" (historical)", " 🔒")
        st.markdown(
            f'<div style="background:rgba(60,52,137,0.1);border:1px solid rgba(60,52,137,0.25);'
            f'border-radius:7px;padding:4px 10px;font-size:0.75rem;color:#3C3489;'
            f'font-family:\'Inter\',sans-serif;margin-bottom:8px;">📍 {mall_display}</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown('<p style="font-size:0.72rem;color:#D85A30;font-weight:700;letter-spacing:0.9px;text-transform:uppercase;margin:0 0 8px;font-family:\'Inter\',sans-serif;">Quick questions</p>', unsafe_allow_html=True)

    _prompts = _make_prompts(selected_mall)
    for label, prompt_text in _prompts:
        if st.button(label, use_container_width=True, key=f"ex_{label}"):
            st.session_state.pending_prompt = prompt_text

    st.divider()
    st.markdown("""
<p style="font-size:0.72rem;color:#D85A30;font-weight:700;letter-spacing:0.8px;
text-transform:uppercase;margin:0 0 6px;font-family:'Inter',sans-serif;">About</p>
<p style="font-size:0.8rem;color:#3C3489;line-height:1.55;font-family:'Inter',sans-serif;margin:0;">
1M+ transactions · 13 Bay Area malls<br>
Jan 2020 – yesterday · updated daily<br>
<span style="color:#1D9E75;font-weight:600;">Fivetran → BigQuery</span> ·
<span style="color:#1D9E75;font-weight:600;">Gemini 3</span> on Google ADK
</p>
<p style="font-size:0.72rem;color:rgba(60,52,137,0.5);margin:10px 0 0;font-family:'Inter',sans-serif;font-style:italic;">
⚠️ All data is synthetic — for demo purposes only.
</p>
""", unsafe_allow_html=True)

    st.divider()

    # ── Dashboard toggle ──────────────────────────────────────────────────────
    st.markdown('<p style="font-size:0.72rem;color:#D85A30;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;margin:0 0 8px;font-family:\'Inter\',sans-serif;">Live Dashboard</p>', unsafe_allow_html=True)
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

# ── Top 3 action items (shown only on fresh open, before any chat) ────────────
if not st.session_state.get("messages"):
    actions = _get_top_actions()
    if actions:
        st.markdown(
            '<p style="font-size:0.78rem;font-weight:700;color:#1A1735;'
            'font-family:\'Plus Jakarta Sans\',sans-serif;letter-spacing:0.2px;'
            'margin:0 0 10px;">📋 Today\'s top action items</p>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(actions))
        for col, action in zip(cols, actions):
            with col:
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.72);border:1px solid rgba(83,74,183,0.18);'
                    f'border-radius:12px;padding:14px 16px;height:100%;">'
                    f'<div style="font-size:1.3rem;margin-bottom:6px;">{action["icon"]}</div>'
                    f'<div style="font-size:0.68rem;color:#D85A30;font-weight:700;letter-spacing:0.7px;'
                    f'text-transform:uppercase;font-family:\'Inter\',sans-serif;margin-bottom:4px;">'
                    f'{action["label"]}</div>'
                    f'<div style="font-size:0.85rem;color:#1A1735;font-family:\'Inter\',sans-serif;'
                    f'margin-bottom:6px;line-height:1.4;">{action["title"]}</div>'
                    f'<div style="font-size:0.78rem;color:rgba(26,23,53,0.55);'
                    f'font-family:\'Inter\',sans-serif;">{action["detail"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("→ Ask agent", key=f"action_{action['label']}", use_container_width=True):
                    st.session_state.pending_prompt = action["prompt"]
                    st.rerun()
        st.divider()

def _md(text: str) -> str:
    """Escape bare $ signs so Streamlit/KaTeX doesn't parse USD values as LaTeX math.
    A retail dashboard never emits real LaTeX, so blanket-escaping is safe and correct.
    """
    return text.replace("$", r"\$")


_AVATAR = {"user": "🧑‍💼", "assistant": "🌉"}

# Render history
for msg in st.session_state.get("messages", []):
    with st.chat_message(msg["role"], avatar=_AVATAR.get(msg["role"])):
        st.markdown(_md(msg["content"]))
        if msg["role"] == "assistant" and msg.get("sql"):
            with st.expander("Show SQL query", expanded=False):
                st.code(msg["sql"], language="sql")

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
        last_sql = ""

        # Capture the SQL that actually executes this turn. The real queries run
        # inside sub-agents (data_unifier etc.), so they never appear as
        # `query_warehouse` calls in the root event stream — instead every BQ
        # tool records its SQL via tools.bigquery_tools.EXECUTED_SQL. Clear it
        # here, read it after the run.
        reset_executed_sql()

        try:
            for event in runner.run(
                user_id=_get_user_id(),
                session_id=st.session_state.adk_session_id,
                new_message=Content(parts=[Part(text=prompt)], role="user"),
            ):
                # Surface tool calls as live status (which specialist is running)
                calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
                if calls:
                    tool_names = ", ".join(f"`{c.name}`" for c in calls)
                    status_slot.caption(f"⚙️ Calling {tool_names}…")

                # Stream partial text as it arrives
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            full_text += part.text
                            text_slot.markdown(_md(full_text) + " ▌")

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
        text_slot.markdown(_md(full_text) if full_text else "_(No response — try rephrasing your question.)_")

        # The actual queries that ran this turn (may be several across sub-agents).
        executed = get_executed_sql()
        last_sql = "\n\n".join(executed)

        if last_sql:
            label = "Show SQL query" if len(executed) == 1 else f"Show SQL ({len(executed)} queries)"
            with st.expander(label, expanded=False):
                st.code(last_sql, language="sql")

    st.session_state.messages.append({
        "role": "assistant",
        "content": full_text,
        "sql": last_sql,
    })

# Re-render SQL expanders for history messages that have SQL
for msg in st.session_state.get("messages", []):
    pass  # expanders are rendered inline above; history re-render is handled at top
