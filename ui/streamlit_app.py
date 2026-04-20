"""
CostSense AI — Command Center (Home)
"""

import streamlit as st

st.set_page_config(
    page_title="CostSense AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.components.theme import inject_global_css, page_header, kpi_card, badge
from ui.components.api_client import get_health, get_summary, get_pending_approval

inject_global_css()

# ── Sidebar brand ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 12px 4px 20px;">
        <div style="font-size:1.1rem; font-weight:800; color:#e8f0fe; letter-spacing:-0.02em;">
            ⚡ CostSense AI
        </div>
        <div style="font-size:10px; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-top:2px;">
            Cost Intelligence Platform
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

# ── API Status ─────────────────────────────────────────────────
health = get_health()

col_brand, col_status = st.columns([5, 1])
with col_brand:
    page_header(
        "Command Center",
        "Autonomous spend intelligence — detecting leakage, scoring risk, triggering action."
    )
with col_status:
    if health:
        st.markdown(
            f'<div style="padding-top:14px; text-align:right;">'
            f'<span class="api-badge api-online">'
            f'<span class="status-dot dot-green"></span>API Online</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="padding-top:14px; text-align:right;">'
            '<span class="api-badge api-offline">'
            '<span class="status-dot dot-red"></span>API Offline</span></div>',
            unsafe_allow_html=True,
        )

if not health:
    st.markdown(
        '<div class="banner-error">⚠️ Cannot reach backend API. '
        'Run <code>python run.py</code> on port 8000 to start the pipeline engine.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── Summary data ───────────────────────────────────────────────
summary = get_summary() or {}
pending_resp = get_pending_approval() or {}
pending_count = pending_resp.get("count", 0)

total_anomalies   = summary.get("anomalies_detected", 0)
total_exposure    = summary.get("total_exposure_inr", 0)
total_recovered   = summary.get("total_recovered_inr", 0)
recovery_rate     = summary.get("recovery_rate_pct", 0)
agents_active     = summary.get("agents_active", 0)
events_processed  = health.get("events_processed", 0)

# ── KPI Row ────────────────────────────────────────────────────
st.markdown('<div class="section-title">Pipeline Health</div>', unsafe_allow_html=True)

c1, c2, c3, c4, c5 = st.columns(5)
cards = [
    (c1, "Anomalies Detected", str(total_anomalies), "across all pipeline runs", "red" if total_anomalies > 0 else "default"),
    (c2, "Financial Exposure", f"₹{total_exposure:,.0f}", "at current risk", "orange" if total_exposure > 0 else "default"),
    (c3, "Recovered / Resolved", f"₹{total_recovered:,.0f}", "savings captured", "green" if total_recovered > 0 else "default"),
    (c4, "Recovery Rate", f"{recovery_rate:.1f}%", "of exposure resolved", "green" if recovery_rate > 50 else "orange"),
    (c5, "Pending Approval", str(pending_count), "actions awaiting sign-off", "orange" if pending_count > 0 else "default"),
]
for col, label, value, sub, color in cards:
    with col:
        st.markdown(kpi_card(label, value, sub, color), unsafe_allow_html=True)

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Quick Actions ──────────────────────────────────────────────
st.markdown('<div class="section-title">Quick Actions</div>', unsafe_allow_html=True)

qa1, qa2, qa3, qa4 = st.columns(4)
with qa1:
    if st.button("▶  Run Demo Analysis", use_container_width=True, type="primary"):
        st.switch_page("pages/01_input.py")
with qa2:
    if st.button("⚠  View Anomalies", use_container_width=True):
        st.switch_page("pages/03_anomalies.py")
with qa3:
    if st.button("✓  Approval Queue" + (f"  ({pending_count})" if pending_count else ""), use_container_width=True):
        st.switch_page("pages/03_anomalies.py")
with qa4:
    if st.button("📊  Executive Report", use_container_width=True):
        st.switch_page("pages/05_summary.py")

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Agent Health Mini-Grid ─────────────────────────────────────
st.markdown('<div class="section-title">Agent Status</div>', unsafe_allow_html=True)

agent_stats = summary.get("agent_stats", [])
agent_map = {a["agent_name"]: a for a in agent_stats}

AGENTS = [
    ("01", "Data Connector",      "agent_01_data_connector"),
    ("02", "Normalization",       "agent_02_normalization"),
    ("03", "Anomaly Detection",   "agent_03_anomaly_detection"),
    ("04", "Root Cause (LLM)",    "agent_04_root_cause"),
    ("05", "Prioritization",      "agent_05_prioritization"),
    ("06", "Merge & Enrich",      "agent_06_merge"),
    ("07", "Action Dispatcher",   "agent_07_action_dispatcher"),
    ("08", "Workflow Executor",   "agent_08_workflow_executor"),
    ("09", "Audit Trail",         "agent_09_audit_trail"),
]

cols = st.columns(9)
for i, (num, name, key) in enumerate(AGENTS):
    stats = agent_map.get(key, {})
    events = stats.get("events_processed", 0)
    errors = stats.get("errors", 0)

    if events == 0:
        css, count_color, dot = "agent-gray", "#334155", "●"
    elif errors == 0:
        css, count_color, dot = "agent-green", "#22c55e", "●"
    elif errors / max(events, 1) < 0.25:
        css, count_color, dot = "agent-orange", "#f59e0b", "●"
    else:
        css, count_color, dot = "agent-red", "#ef4444", "●"

    with cols[i]:
        st.markdown(
            f"""<div class="agent-node {css}" style="padding:10px 8px;">
                <div class="agent-num">A{num}</div>
                <div class="agent-name" style="font-size:10px; min-height:26px;">{name}</div>
                <div class="agent-count" style="font-size:1.3rem; color:{count_color};">{events}</div>
                <div class="agent-errors" style="font-size:9px;">events</div>
            </div>""",
            unsafe_allow_html=True,
        )

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Top Anomalies Snapshot ─────────────────────────────────────
from ui.components.api_client import get_anomalies

st.markdown('<div class="section-title">Top Priority Anomalies</div>', unsafe_allow_html=True)

anom_resp = get_anomalies(limit=5) or {}
anomalies = anom_resp.get("anomalies", [])
anomalies_sorted = sorted(anomalies, key=lambda x: x.get("aps_score") or 0, reverse=True)[:5]

if anomalies_sorted:
    STATUS_COLORS = {
        "pending_approval": "orange",
        "auto_executed": "green",
        "approved": "green",
        "detected": "blue",
        "rejected": "gray",
    }
    TYPE_LABELS = {
        "duplicate_payment":   "Duplicate Payment",
        "cloud_waste":         "Cloud Waste",
        "unused_saas":         "Unused SaaS",
        "vendor_rate_anomaly": "Vendor Rate Anomaly",
        "sla_penalty_risk":    "SLA Penalty Risk",
    }
    for a in anomalies_sorted:
        atype    = a.get("anomaly_type", "unknown")
        status   = a.get("status", "detected")
        aps      = a.get("aps_score") or 0
        conf     = a.get("confidence") or 0
        vendor   = a.get("vendor") or "—"
        dept     = a.get("department") or "—"
        action   = a.get("suggested_action") or "Review required"
        sc       = STATUS_COLORS.get(status, "gray")
        tlabel   = TYPE_LABELS.get(atype, atype.replace("_", " ").title())
        bar_w    = int(aps * 10)
        bar_col  = "#ef4444" if aps > 7 else "#f59e0b" if aps > 4 else "#3b82f6"

        st.markdown(
            f"""<div class="anomaly-card {'anomaly-card-pending' if status == 'pending_approval' else ''}">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <span class="badge badge-{sc}" style="margin-right:6px;">{status.replace('_', ' ').upper()}</span>
                        <span class="badge badge-gray">{tlabel}</span>
                    </div>
                    <div style="text-align:right;">
                        <div style="font-size:10px; color:#4a6080; margin-bottom:2px;">APS Score</div>
                        <div style="font-size:1.1rem; font-weight:700; color:{bar_col};">{aps:.2f}<span style="font-size:10px; color:#4a6080;">/10</span></div>
                    </div>
                </div>
                <div class="anomaly-meta" style="margin-top:8px;">
                    Vendor: <strong style="color:#8098b8;">{vendor}</strong>
                    &nbsp;·&nbsp; Dept: {dept}
                    &nbsp;·&nbsp; Confidence: {conf:.0%}
                </div>
                <div class="anomaly-detail">{action}</div>
                <div class="score-bar-bg"><div class="score-bar" style="width:{bar_w}%; background:{bar_col};"></div></div>
            </div>""",
            unsafe_allow_html=True,
        )
else:
    st.markdown(
        '<div class="banner-info">No anomalies yet — go to <strong>Data Input</strong> to run your first analysis.</div>',
        unsafe_allow_html=True,
    )

# ── Footer ─────────────────────────────────────────────────────
st.markdown(
    f'<div style="text-align:center; color:#1e3050; font-size:11px; margin-top:24px;">'
    f'CostSense AI · {events_processed:,} events processed · 9 agents active</div>',
    unsafe_allow_html=True,
)
