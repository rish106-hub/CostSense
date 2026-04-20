"""
Page 4 — Process Trace Viewer
Gantt waterfall + step-by-step log with payload inspector.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Process Logs — CostSense AI", page_icon="⚡", layout="wide")

from ui.components.theme import inject_global_css, page_header, kpi_card
from ui.components.api_client import get_health, get_process_logs, get_process_trace, list_processes

inject_global_css()

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 12px 4px 20px;">
        <div style="font-size:1.1rem; font-weight:800; color:#e8f0fe;">⚡ CostSense AI</div>
        <div style="font-size:10px; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-top:2px;">Process Logs</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.markdown('<div style="font-size:11px; font-weight:600; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">Filters</div>', unsafe_allow_html=True)

    status_filter = st.multiselect("Status", ["success", "error", "skipped"], default=[])
    agent_filter  = st.multiselect("Agent", [
        "agent_01_data_connector", "agent_02_normalization",
        "agent_03_anomaly_detection", "agent_04_root_cause",
        "agent_05_prioritization", "agent_06_merge",
        "agent_07_action_dispatcher", "agent_08_workflow_executor",
        "agent_09_audit_trail",
    ], default=[])

# ── Health ─────────────────────────────────────────────────────
health = get_health()
if health is None:
    st.markdown('<div class="banner-error">Cannot reach API server.</div>', unsafe_allow_html=True)
    st.stop()

page_header("Process Trace", "Full step-by-step execution log for each pipeline run.")

# ── Process selector ───────────────────────────────────────────
processes_resp = list_processes(limit=50) or {}
processes = processes_resp.get("processes", [])

if not processes:
    st.markdown(
        '<div class="banner-info">No pipeline runs found yet — go to <strong>Data Ingestion</strong> to run your first analysis.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

process_options = {}
for p in processes:
    pid = p.get("process_id")
    ts  = (p.get("started_at") or "Unknown")[:19].replace("T", " ")
    cnt = p.get("agent_count", p.get("record_count", "?"))
    if pid:
        process_options[f"{ts}  ·  {pid[:14]}…  ({cnt} steps)"] = pid

if not process_options:
    st.error("Could not parse process list.")
    st.stop()

col_sel, col_ref = st.columns([5, 1])
with col_sel:
    selected_label = st.selectbox("Pipeline run", list(process_options.keys()), label_visibility="collapsed")
    selected_pid = process_options[selected_label]
with col_ref:
    if st.button("Refresh", use_container_width=True):
        st.rerun()

# ── Load trace ─────────────────────────────────────────────────
trace_resp = get_process_trace(selected_pid) or {}
if isinstance(trace_resp, dict) and "error" in trace_resp:
    st.error(f"API Error: {trace_resp['error']}")
    st.stop()

logs = trace_resp.get("logs", [])

if status_filter:
    logs = [l for l in logs if l.get("status") in status_filter]
if agent_filter:
    logs = [l for l in logs if l.get("agent_name") in agent_filter]

# ── KPIs ───────────────────────────────────────────────────────
total_steps = len(logs)
errors = sum(1 for l in logs if l.get("status") == "error")
total_ms = sum(l.get("duration_ms") or 0 for l in logs)
agents_inv = len({l.get("agent_name") for l in logs})

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(kpi_card("Steps Executed", str(total_steps), "in selected run", "blue"), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card("Errors", str(errors), "in selected run", "red" if errors > 0 else "green"), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card("Agents Involved", str(agents_inv), "unique agents", "purple"), unsafe_allow_html=True)
with c4:
    st.markdown(kpi_card("Total Duration", f"{total_ms:,}ms", "wall-clock time", "default"), unsafe_allow_html=True)

if not logs:
    st.markdown(
        '<div class="banner-info">No log entries found for this run with the current filters.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Gantt chart ────────────────────────────────────────────────
st.markdown('<div class="section-title">Execution Waterfall</div>', unsafe_allow_html=True)

gantt_data = []
for log in logs:
    if log.get("started_at"):
        gantt_data.append({
            "Agent":       log["agent_name"].replace("agent_0", "A").replace("agent_", "A"),
            "Start":       log["started_at"],
            "Finish":      log.get("completed_at") or log["started_at"],
            "Status":      log.get("status", "success"),
            "Duration ms": log.get("duration_ms") or 0,
        })

if gantt_data:
    df_gantt = pd.DataFrame(gantt_data)
    color_map = {"success": "#22c55e", "error": "#ef4444", "skipped": "#334155"}
    fig = px.timeline(
        df_gantt, x_start="Start", x_end="Finish", y="Agent",
        color="Status", color_discrete_map=color_map,
        hover_data=["Duration ms"],
    )
    fig.update_layout(
        height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#8098b8",
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Timestamps not available for waterfall — showing log table only.")

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Log table ──────────────────────────────────────────────────
st.markdown('<div class="section-title">Step-by-Step Log — Click a row to inspect payloads</div>', unsafe_allow_html=True)

table_data = []
for i, log in enumerate(logs):
    table_data.append({
        "#":            i + 1,
        "Agent":        log.get("agent_name", ""),
        "Topic In":     log.get("topic_in") or "—",
        "Topic Out":    log.get("topic_out") or "—",
        "Status":       log.get("status", ""),
        "Duration ms":  log.get("duration_ms") or 0,
        "Started":      (log.get("started_at") or "")[:19].replace("T", " "),
        "Error":        (log.get("error_message") or "")[:80],
    })

selected_rows = st.dataframe(
    pd.DataFrame(table_data),
    use_container_width=True,
    height=280,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# ── Payload inspector ──────────────────────────────────────────
st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">Payload Inspector</div>', unsafe_allow_html=True)

selected_indices = (
    selected_rows.selection.get("rows", []) if hasattr(selected_rows, "selection") else []
)

if selected_indices:
    row_idx = selected_indices[0]
    log = logs[row_idx]
    status = log.get("status", "")
    status_color = "#22c55e" if status == "success" else "#ef4444"

    st.markdown(
        f"""<div class="anomaly-card" style="margin-bottom:12px;">
            <span class="badge badge-{'green' if status == 'success' else 'red'}" style="margin-right:8px;">{status.upper()}</span>
            <span style="font-size:12px;color:#8098b8;">{log.get('agent_name','')}</span>
            <span style="font-size:12px;color:#4a6080;margin-left:12px;">·  {log.get('duration_ms') or 0}ms</span>
        </div>""",
        unsafe_allow_html=True,
    )

    if log.get("error_message"):
        st.markdown(
            f'<div class="banner-error">{log["error_message"]}</div>',
            unsafe_allow_html=True,
        )

    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown("**Input Payload**")
        st.json(log.get("input_payload") or {})
    with col_out:
        st.markdown("**Output Payload**")
        out = log.get("output_payload")
        if out:
            st.json(out)
        else:
            st.markdown('<div class="banner-info">No output payload — agent did not publish an event.</div>', unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="banner-info">Click any row in the table above to inspect its input/output payloads.</div>',
        unsafe_allow_html=True,
    )
