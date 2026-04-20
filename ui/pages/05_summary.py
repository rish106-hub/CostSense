"""
Page 5 — Executive Summary
CFO-level financial impact view with recovery metrics and agent health.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Executive Summary — CostSense AI", page_icon="⚡", layout="wide")

from ui.components.theme import inject_global_css, page_header, kpi_card, badge
from ui.components.api_client import get_anomalies, get_health, get_summary, list_processes

inject_global_css()

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 12px 4px 20px;">
        <div style="font-size:1.1rem; font-weight:800; color:#e8f0fe;">⚡ CostSense AI</div>
        <div style="font-size:10px; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-top:2px;">Executive Summary</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

# ── Health ─────────────────────────────────────────────────────
health = get_health()
if health is None:
    st.markdown('<div class="banner-error">Cannot reach API server.</div>', unsafe_allow_html=True)
    st.stop()

page_header("Executive Summary", "Financial impact overview for operations leadership.")

# ── Process selector ───────────────────────────────────────────
processes_resp = list_processes(limit=50) or {}
processes = processes_resp.get("processes", [])

process_options = {"All Pipeline Runs": None}
first_pid = None
for p in processes:
    pid = p.get("process_id")
    ts  = (p.get("started_at") or "")[:19].replace("T", " ")
    if pid:
        process_options[f"{ts}  ·  {pid[:14]}…"] = pid
        if first_pid is None:
            first_pid = pid

if "summary_pid" not in st.session_state:
    st.session_state.summary_pid = first_pid

col_sel, col_ref = st.columns([5, 1])
with col_sel:
    selected_label = st.selectbox(
        "View for run:",
        list(process_options.keys()),
        index=list(process_options.values()).index(st.session_state.summary_pid)
            if st.session_state.summary_pid in process_options.values() else 0,
        label_visibility="collapsed",
    )
    selected_pid = process_options[selected_label]
    st.session_state.summary_pid = selected_pid
with col_ref:
    if st.button("Refresh", use_container_width=True):
        st.rerun()

# ── Load summary ───────────────────────────────────────────────
summary = get_summary(process_id=selected_pid) or {}
if isinstance(summary, dict) and "error" in summary:
    st.error(f"API Error: {summary['error']}")
    st.stop()

if summary.get("anomalies_detected", 0) == 0:
    st.markdown(
        '<div class="banner-info">No pipeline data yet — go to <strong>Data Ingestion</strong> and run an analysis first.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── Financial Impact KPIs ──────────────────────────────────────
st.markdown('<div class="section-title">Financial Impact</div>', unsafe_allow_html=True)

total_exposure   = summary.get("total_exposure_inr", 0)
total_recovered  = summary.get("total_recovered_inr", 0)
pending_exposure = summary.get("pending_exposure_inr", 0)
recovery_rate    = summary.get("recovery_rate_pct", 0)
total_anomalies  = summary.get("anomalies_detected", 0)
pending_count    = summary.get("pending_approval", 0)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(kpi_card("Anomalies Detected", str(total_anomalies), "total across all categories", "red"), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card("Exposure at Risk", f"₹{total_exposure:,.0f}", "unresolved financial risk", "orange" if total_exposure > 0 else "default"), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card("Value Recovered", f"₹{total_recovered:,.0f}", "cost leakage stopped", "green"), unsafe_allow_html=True)
with c4:
    st.markdown(kpi_card("Recovery Rate", f"{recovery_rate:.1f}%", "of total exposure resolved", "green" if recovery_rate > 50 else "orange"), unsafe_allow_html=True)
with c5:
    st.markdown(kpi_card("Awaiting Approval", str(pending_count), f"₹{pending_exposure:,.0f} on hold", "orange" if pending_count > 0 else "default"), unsafe_allow_html=True)

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Charts ─────────────────────────────────────────────────────
st.markdown('<div class="section-title">Breakdown</div>', unsafe_allow_html=True)
ch1, ch2 = st.columns(2)

with ch1:
    st.markdown("**Anomaly Types**")
    breakdown = summary.get("anomaly_breakdown", {})
    if breakdown:
        df_b = pd.DataFrame(list(breakdown.items()), columns=["Type", "Count"])
        df_b["Type"] = df_b["Type"].str.replace("_", " ").str.title()
        df_b = df_b.sort_values("Count", ascending=True)
        fig = px.bar(df_b, x="Count", y="Type", orientation="h",
                     color="Count", color_continuous_scale="Oranges")
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#8098b8", showlegend=False, coloraxis_showscale=False)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True)

with ch2:
    st.markdown("**Status Distribution**")
    status_dist = summary.get("status_distribution", {})
    if status_dist:
        df_s = pd.DataFrame(list(status_dist.items()), columns=["Status", "Count"])
        df_s["Status"] = df_s["Status"].str.replace("_", " ").str.title()
        color_seq = ["#22c55e", "#f59e0b", "#3b82f6", "#ef4444", "#64748b"]
        fig2 = px.pie(df_s, values="Count", names="Status", color_discrete_sequence=color_seq)
        fig2.update_layout(height=260, margin=dict(l=0, r=0, t=0, b=0),
                           paper_bgcolor="rgba(0,0,0,0)", font_color="#8098b8",
                           legend=dict(font=dict(size=11)))
        st.plotly_chart(fig2, use_container_width=True)

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Top Priority Anomaly ───────────────────────────────────────
top = summary.get("top_anomaly")
if top:
    st.markdown('<div class="section-title">Highest Priority Finding</div>', unsafe_allow_html=True)
    aps     = top.get("aps_score") or 0
    atype   = top.get("anomaly_type", "unknown").replace("_", " ").title()
    status  = top.get("status", "detected")
    vendor  = top.get("vendor") or "—"
    conf    = top.get("confidence") or 0
    root    = top.get("root_cause") or "No root cause available."
    action  = top.get("suggested_action") or "Review required."
    bar_col = "#ef4444" if aps > 7 else "#f59e0b" if aps > 4 else "#3b82f6"

    STATUS_COLORS = {"pending_approval": "orange", "auto_executed": "green", "approved": "green", "detected": "blue"}
    sc = STATUS_COLORS.get(status, "gray")

    st.markdown(
        f"""<div class="anomaly-card" style="border-color:#334155;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px;">
                <div>
                    <span class="badge badge-{sc}" style="margin-right:6px;">{status.replace('_', ' ').upper()}</span>
                    <span class="badge badge-gray">{atype}</span>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:9px;color:#4a6080;">ACTION PRIORITY</div>
                    <div style="font-size:1.4rem;font-weight:700;color:{bar_col};">{aps:.2f}<span style="font-size:11px;color:#4a6080;">/10</span></div>
                </div>
            </div>
            <div style="font-size:12px;color:#64748b;margin-bottom:8px;">
                Vendor: <span style="color:#8098b8;">{vendor}</span> &nbsp;·&nbsp; Confidence: {conf:.0%}
            </div>
            <div style="margin-bottom:6px;">
                <div style="font-size:11px;color:#4a6080;margin-bottom:2px;">ROOT CAUSE</div>
                <div style="font-size:13px;color:#94a3b8;line-height:1.5;">{root[:300]}</div>
            </div>
            <div>
                <div style="font-size:11px;color:#4a6080;margin-bottom:2px;">SUGGESTED ACTION</div>
                <div style="font-size:13px;color:#94a3b8;line-height:1.5;">{action[:300]}</div>
            </div>
            <div class="score-bar-bg" style="margin-top:12px;">
                <div class="score-bar" style="width:{int(aps*10)}%;background:{bar_col};"></div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Agent Health Table ─────────────────────────────────────────
st.markdown('<div class="section-title">Agent Health</div>', unsafe_allow_html=True)

agent_stats = summary.get("agent_stats", [])
AGENT_LABELS = {
    "agent_01_data_connector":    "01 · Data Connector",
    "agent_02_normalization":     "02 · Normalization",
    "agent_03_anomaly_detection": "03 · Anomaly Detection",
    "agent_04_root_cause":        "04 · Root Cause (LLM)",
    "agent_05_prioritization":    "05 · Prioritization",
    "agent_06_merge":             "06 · Merge & Enrich",
    "agent_07_action_dispatcher": "07 · Action Dispatcher",
    "agent_08_workflow_executor": "08 · Workflow Executor",
    "agent_09_audit_trail":       "09 · Audit Trail",
}

if agent_stats:
    for a in agent_stats:
        key    = a.get("agent_name", "")
        label  = AGENT_LABELS.get(key, key)
        events = a.get("events_processed", 0)
        errors = a.get("errors", 0)
        avg_ms = a.get("avg_duration_ms", 0)
        seen   = (a.get("last_seen") or "")[:19].replace("T", " ")

        if events == 0:
            css, dot_color = "agent-gray", "#334155"
        elif errors == 0:
            css, dot_color = "agent-green", "#22c55e"
        elif errors / max(events, 1) < 0.25:
            css, dot_color = "agent-orange", "#f59e0b"
        else:
            css, dot_color = "agent-red", "#ef4444"

        col_agent, col_events, col_errors, col_latency, col_seen = st.columns([3, 1, 1, 1, 2])
        with col_agent:
            st.markdown(
                f'<div style="font-size:13px;color:#cbd5e1;padding:8px 0;font-weight:500;">'
                f'<span style="color:{dot_color};margin-right:6px;">●</span>{label}</div>',
                unsafe_allow_html=True,
            )
        with col_events:
            st.markdown(f'<div style="font-size:13px;color:#8098b8;padding:8px 0;text-align:right;">{events}</div>', unsafe_allow_html=True)
        with col_errors:
            ec = "#ef4444" if errors > 0 else "#334155"
            st.markdown(f'<div style="font-size:13px;color:{ec};padding:8px 0;text-align:right;">{errors}</div>', unsafe_allow_html=True)
        with col_latency:
            st.markdown(f'<div style="font-size:13px;color:#8098b8;padding:8px 0;text-align:right;">{avg_ms:.0f}ms</div>', unsafe_allow_html=True)
        with col_seen:
            st.markdown(f'<div style="font-size:12px;color:#4a6080;padding:8px 0;text-align:right;">{seen or "—"}</div>', unsafe_allow_html=True)

    # Header
    st.markdown(
        '<div style="display:flex;justify-content:flex-end;gap:4px;font-size:10px;color:#334155;text-transform:uppercase;letter-spacing:0.08em;margin-top:4px;">'
        '<span style="width:80px;text-align:right;">Events</span>'
        '<span style="width:60px;text-align:right;">Errors</span>'
        '<span style="width:70px;text-align:right;">Avg Lat</span>'
        '<span style="width:140px;text-align:right;">Last Active</span>'
        '</div>',
        unsafe_allow_html=True,
    )

# ── Footer ─────────────────────────────────────────────────────
st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)
st.markdown(
    f'<div style="text-align:center;color:#1e3050;font-size:11px;">'
    f'CostSense AI  ·  API v{health.get("version","?")}  ·  {health.get("events_processed",0):,} events on bus</div>',
    unsafe_allow_html=True,
)
