"""
Page 2 — Live Pipeline Monitor
Dynamic real-time agent architecture visualization with color-coded status.
"""

import time
from collections import defaultdict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Live Pipeline — CostSense AI", page_icon="⚡", layout="wide")

from ui.components.theme import inject_global_css, page_header, kpi_card
from ui.components.api_client import (
    get_bus_events,
    get_health,
    get_process_logs,
    get_summary,
    list_processes,
)

inject_global_css()

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 12px 4px 20px;">
        <div style="font-size:1.1rem; font-weight:800; color:#e8f0fe;">⚡ CostSense AI</div>
        <div style="font-size:10px; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-top:2px;">Live Pipeline</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown('<div style="font-size:11px; font-weight:600; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">Refresh</div>', unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto-refresh", value=False)
    refresh_interval = st.select_slider("Interval", [2, 3, 5, 10], value=3, format_func=lambda x: f"{x}s")

    st.divider()
    st.markdown('<div style="font-size:11px; font-weight:600; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">Filter by Run</div>', unsafe_allow_html=True)

    processes_resp = list_processes(limit=20)
    processes = processes_resp.get("processes", []) if processes_resp else []
    process_options = {"All runs": None}
    for p in processes:
        pid = p["process_id"]
        ts  = (p.get("started_at") or "")[:16].replace("T", " ")
        process_options[f"{ts}  ·  {pid[:10]}…"] = pid

    selected_label = st.selectbox("Run", list(process_options.keys()), label_visibility="collapsed")
    selected_pid = process_options[selected_label]

# ── Health check ───────────────────────────────────────────────
health = get_health()
if health is None:
    st.markdown('<div class="banner-error">⚠️ Cannot reach API server.</div>', unsafe_allow_html=True)
    st.stop()

page_header("Live Pipeline Monitor", "Real-time view of agent execution — colour indicates health.")

# ── Load data ──────────────────────────────────────────────────
summary       = get_summary() or {}
agent_stats   = summary.get("agent_stats", [])
agent_map     = {a["agent_name"]: a for a in agent_stats}

logs_resp     = get_process_logs(process_id=selected_pid, limit=500)
process_logs  = logs_resp.get("logs", []) if logs_resp else []

events_resp   = get_bus_events(limit=100)
bus_events    = events_resp.get("events", []) if events_resp else []

event_counts: dict[str, int] = defaultdict(int)
for ev in bus_events:
    event_counts[ev.get("topic", "unknown")] += 1

# ── KPI row ────────────────────────────────────────────────────
total_events  = health.get("events_processed", 0)
error_count   = sum(1 for l in process_logs if l.get("status") == "error")
success_count = sum(1 for l in process_logs if l.get("status") == "success")
avg_dur = (
    round(sum(l.get("duration_ms") or 0 for l in process_logs) / len(process_logs))
    if process_logs else 0
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(kpi_card("Events Processed", f"{total_events:,}", "across all topics", "blue"), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card("Log Entries", str(len(process_logs)), "in selected run", "default"), unsafe_allow_html=True)
with c3:
    color = "red" if error_count > 0 else "green"
    st.markdown(kpi_card("Pipeline Errors", str(error_count), "in selected run", color), unsafe_allow_html=True)
with c4:
    st.markdown(kpi_card("Avg Agent Latency", f"{avg_dur}ms", "per log entry", "purple"), unsafe_allow_html=True)

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# DYNAMIC AGENT ARCHITECTURE
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="section-title">Agent Architecture — Live Status</div>', unsafe_allow_html=True)

LEGEND_HTML = """
<div style="display:flex; gap:16px; margin-bottom:16px; flex-wrap:wrap;">
    <span><span style="display:inline-block;width:10px;height:10px;background:#22c55e;border-radius:50%;margin-right:5px;"></span><span style="font-size:11px;color:#64748b;">Active &amp; Healthy</span></span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#f59e0b;border-radius:50%;margin-right:5px;"></span><span style="font-size:11px;color:#64748b;">Active with Warnings</span></span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#ef4444;border-radius:50%;margin-right:5px;"></span><span style="font-size:11px;color:#64748b;">Degraded / Errors</span></span>
    <span><span style="display:inline-block;width:10px;height:10px;background:#1e293b;border:1px solid #334155;border-radius:50%;margin-right:5px;"></span><span style="font-size:11px;color:#64748b;">Idle</span></span>
</div>
"""
st.markdown(LEGEND_HTML, unsafe_allow_html=True)


def _agent_html(num: str, name: str, key: str, override_events: int = None) -> str:
    stats  = agent_map.get(key, {})
    events = override_events if override_events is not None else stats.get("events_processed", 0)
    errors = stats.get("errors", 0)

    if events == 0:
        css, count_color = "agent-gray", "#334155"
    elif errors == 0:
        css, count_color = "agent-green", "#22c55e"
    elif errors / max(events, 1) < 0.25:
        css, count_color = "agent-orange", "#f59e0b"
    else:
        css, count_color = "agent-red", "#ef4444"

    err_label = f"· {errors} err" if errors > 0 else "· clean"
    return f"""
    <div class="agent-node {css}">
        <div class="agent-num">AGENT {num}</div>
        <div class="agent-name">{name}</div>
        <div class="agent-count" style="color:{count_color};">{events}</div>
        <div class="agent-errors">{err_label}</div>
    </div>
    """


ARROW_DOWN = '<div class="pipe-down">↓</div>'


# ── Row 1: Data Connector ──────────────────────────────────────
_, col_a01, _ = st.columns([3, 2, 3])
with col_a01:
    st.markdown(_agent_html("01", "Data Connector", "agent_01_data_connector"), unsafe_allow_html=True)
    st.markdown(ARROW_DOWN, unsafe_allow_html=True)

# ── Row 2: Normalization ───────────────────────────────────────
_, col_a02, _ = st.columns([3, 2, 3])
with col_a02:
    st.markdown(_agent_html("02", "Normalization", "agent_02_normalization"), unsafe_allow_html=True)
    st.markdown(ARROW_DOWN, unsafe_allow_html=True)

# ── Row 3: Anomaly Detection ───────────────────────────────────
_, col_a03, _ = st.columns([3, 2, 3])
with col_a03:
    st.markdown(_agent_html("03", "Anomaly Detection", "agent_03_anomaly_detection"), unsafe_allow_html=True)

# ── Split arrow ────────────────────────────────────────────────
_, split_l, _, split_r, _ = st.columns([3, 1, 2, 1, 3])
with split_l:
    st.markdown('<div style="text-align:right;font-size:18px;color:#1e3050;padding-right:10px;">↙</div>', unsafe_allow_html=True)
with split_r:
    st.markdown('<div style="text-align:left;font-size:18px;color:#1e3050;padding-left:10px;">↘</div>', unsafe_allow_html=True)

# ── Row 4: Root Cause + Prioritization (parallel) ─────────────
_, col_a04, col_spacer, col_a05, _ = st.columns([2, 2, 1, 2, 2])
with col_a04:
    st.markdown(_agent_html("04", "Root Cause (LLM)", "agent_04_root_cause"), unsafe_allow_html=True)
with col_a05:
    st.markdown(_agent_html("05", "Prioritization", "agent_05_prioritization"), unsafe_allow_html=True)

# ── Merge arrows ───────────────────────────────────────────────
_, merge_l, _, merge_r, _ = st.columns([2, 2, 1, 2, 2])
with merge_l:
    st.markdown('<div style="text-align:right;font-size:18px;color:#1e3050;padding-right:10px;">↘</div>', unsafe_allow_html=True)
with merge_r:
    st.markdown('<div style="text-align:left;font-size:18px;color:#1e3050;padding-left:10px;">↙</div>', unsafe_allow_html=True)

# ── Row 5: Merge ──────────────────────────────────────────────
_, col_a06, _ = st.columns([3, 2, 3])
with col_a06:
    st.markdown(_agent_html("06", "Merge & Enrich", "agent_06_merge"), unsafe_allow_html=True)
    st.markdown(ARROW_DOWN, unsafe_allow_html=True)

# ── Row 6: Action Dispatcher ───────────────────────────────────
_, col_a07, _ = st.columns([3, 2, 3])
with col_a07:
    st.markdown(_agent_html("07", "Action Dispatcher", "agent_07_action_dispatcher"), unsafe_allow_html=True)

# ── Dispatcher split ───────────────────────────────────────────
_, d_l, _, d_r, _ = st.columns([3, 1, 2, 1, 3])
with d_l:
    st.markdown('<div style="text-align:right;font-size:18px;color:#1e3050;padding-right:10px;">↙</div>', unsafe_allow_html=True)
with d_r:
    st.markdown('<div style="text-align:left;font-size:18px;color:#1e3050;padding-left:10px;">↘</div>', unsafe_allow_html=True)

# ── Action outcome labels ──────────────────────────────────────
_, col_auto_lbl, col_sp2, col_appr_lbl, _ = st.columns([2, 2, 1, 2, 2])
with col_auto_lbl:
    auto_count  = event_counts.get("action.auto_execute", 0)
    auto_color  = "#22c55e" if auto_count > 0 else "#1e3050"
    st.markdown(
        f'<div style="text-align:center;font-size:11px;color:{auto_color};font-weight:600;padding:4px 0;">AUTO-EXECUTE<br>{auto_count} actions</div>',
        unsafe_allow_html=True,
    )
with col_appr_lbl:
    appr_count  = event_counts.get("action.approval_needed", 0)
    appr_color  = "#f59e0b" if appr_count > 0 else "#1e3050"
    st.markdown(
        f'<div style="text-align:center;font-size:11px;color:{appr_color};font-weight:600;padding:4px 0;">NEEDS APPROVAL<br>{appr_count} actions</div>',
        unsafe_allow_html=True,
    )

# ── Row 7: Workflow Executor ───────────────────────────────────
_, col_a08, _ = st.columns([3, 2, 3])
with col_a08:
    st.markdown(ARROW_DOWN, unsafe_allow_html=True)
    st.markdown(_agent_html("08", "Workflow Executor", "agent_08_workflow_executor"), unsafe_allow_html=True)
    st.markdown(ARROW_DOWN, unsafe_allow_html=True)

# ── Row 8: Audit Trail ─────────────────────────────────────────
_, col_a09, _ = st.columns([3, 2, 3])
with col_a09:
    st.markdown(
        _agent_html("09", "Audit Trail", "agent_09_audit_trail")
        .replace("agent-node", "agent-node")
        + "",
        unsafe_allow_html=True,
    )

# ── Topic event counts ─────────────────────────────────────────
st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">Event Bus — Topic Throughput</div>', unsafe_allow_html=True)

TOPICS = [
    ("raw.spend",              "01 → raw.spend"),
    ("normalized.spend",       "02 → normalized.spend"),
    ("anomaly.detected",       "03 → anomaly.detected"),
    ("anomaly.enriched",       "04 → anomaly.enriched"),
    ("anomaly.scored",         "05 → anomaly.scored"),
    ("anomaly.ready",          "06 → anomaly.ready"),
    ("action.approval_needed", "07 → approval_needed"),
    ("action.auto_execute",    "07 → auto_execute"),
]
topic_cols = st.columns(len(TOPICS))
for i, (topic, label) in enumerate(TOPICS):
    count = event_counts.get(topic, 0)
    if count > 0:
        bg, border, vc = "#052e16", "#22c55e", "#22c55e"
    else:
        bg, border, vc = "#0c1525", "#1a2540", "#334155"
    with topic_cols[i]:
        st.markdown(
            f"""<div style="background:{bg};border:1.5px solid {border};border-radius:8px;padding:10px 8px;text-align:center;">
                <div style="font-size:9px;color:#4a6080;margin-bottom:4px;">{label}</div>
                <div style="font-size:1.4rem;font-weight:700;color:{vc};">{count}</div>
                <div style="font-size:9px;color:#334155;">events</div>
            </div>""",
            unsafe_allow_html=True,
        )

# ── Recent event feed ──────────────────────────────────────────
st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">Recent Event Feed</div>', unsafe_allow_html=True)

if bus_events:
    feed_rows = []
    for ev in bus_events[:40]:
        feed_rows.append({
            "Time":         (ev.get("timestamp") or "")[:19].replace("T", " "),
            "Topic":        ev.get("topic", ""),
            "Source Agent": ev.get("source_agent", ""),
            "Process":      ((ev.get("process_id") or "")[:8] + "…") if ev.get("process_id") else "—",
            "Event ID":     ((ev.get("event_id") or "")[:8] + "…"),
        })
    st.dataframe(pd.DataFrame(feed_rows), use_container_width=True, height=220, hide_index=True)
else:
    st.markdown(
        '<div class="banner-info">No events yet — run a pipeline from Data Ingestion to see activity here.</div>',
        unsafe_allow_html=True,
    )

# ── Execution log ──────────────────────────────────────────────
if process_logs:
    st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Agent Execution Log</div>', unsafe_allow_html=True)
    log_rows = []
    for log in process_logs:
        log_rows.append({
            "Agent":        log.get("agent_name", "").replace("agent_0", "A").replace("agent_", "A"),
            "Topic In":     log.get("topic_in") or "—",
            "Topic Out":    log.get("topic_out") or "—",
            "Status":       log.get("status", ""),
            "Duration ms":  log.get("duration_ms") or 0,
            "Started":      (log.get("started_at") or "")[:19].replace("T", " "),
            "Error":        (log.get("error_message") or "")[:60],
        })
    st.dataframe(pd.DataFrame(log_rows), use_container_width=True, height=280, hide_index=True)

# ── Auto-refresh ───────────────────────────────────────────────
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
