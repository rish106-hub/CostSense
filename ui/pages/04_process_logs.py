"""
Page 4 — Process Trace Viewer

Select a process run, see a Gantt-style waterfall of agent durations,
browse the full log table, and inspect input/output JSON per log entry.
"""

import json

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components.api_client import get_health, get_process_logs, get_process_trace, list_processes

st.set_page_config(page_title="Process Logs — CostSense AI", page_icon="🔍", layout="wide")

st.title("🔍 Process Trace Viewer")
st.caption("Full input/output trace for every agent, per pipeline run.")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
health = get_health()
if health is None:
    st.error("⚠️ Cannot reach API server.")
    st.stop()

# ---------------------------------------------------------------------------
# Process selector
# ---------------------------------------------------------------------------
processes_resp = list_processes(limit=50)
processes = processes_resp.get("processes", []) if processes_resp else []

if not processes:
    st.info("No pipeline runs found yet. Go to **Data Input** and run a pipeline first.")
    st.stop()

process_options = {}
for p in processes:
    pid = p["process_id"]
    ts = (p.get("started_at") or "")[:19].replace("T", " ")
    label = f"{ts} — {pid[:12]}… ({p.get('record_count', '?')} steps)"
    process_options[label] = pid

selected_label = st.selectbox("Select a process run", list(process_options.keys()))
selected_pid = process_options[selected_label]

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    status_filter = st.multiselect(
        "Status", ["success", "error", "skipped"], default=[]
    )
    agent_filter = st.multiselect(
        "Agent",
        [
            "agent_01_data_connector",
            "agent_02_normalization",
            "agent_03_anomaly_detection",
            "agent_04_root_cause",
            "agent_05_prioritization",
            "agent_06_merge",
            "agent_07_action_dispatcher",
            "agent_08_workflow_executor",
            "agent_09_audit_trail",
        ],
        default=[],
    )

# ---------------------------------------------------------------------------
# Load trace
# ---------------------------------------------------------------------------
trace_resp = get_process_trace(selected_pid)
logs = trace_resp.get("logs", []) if trace_resp else []

# Apply filters
if status_filter:
    logs = [l for l in logs if l.get("status") in status_filter]
if agent_filter:
    logs = [l for l in logs if l.get("agent_name") in agent_filter]

if not logs:
    st.warning("No log entries found for this process run with current filters.")
    st.stop()

# ---------------------------------------------------------------------------
# Summary KPIs
# ---------------------------------------------------------------------------
total_steps = len(logs)
errors = sum(1 for l in logs if l.get("status") == "error")
total_ms = sum(l.get("duration_ms") or 0 for l in logs)
agents_involved = len({l.get("agent_name") for l in logs})

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Steps", total_steps)
k2.metric("Errors", errors)
k3.metric("Agents Involved", agents_involved)
k4.metric("Total Duration", f"{total_ms:,}ms")

st.divider()

# ---------------------------------------------------------------------------
# Gantt / Waterfall Chart
# ---------------------------------------------------------------------------
st.subheader("⏱️ Agent Execution Waterfall")

gantt_data = []
for log in logs:
    if log.get("started_at"):
        gantt_data.append(
            {
                "Agent": log["agent_name"].replace("agent_0", "A").replace("agent_", "A"),
                "Start": log["started_at"],
                "Finish": log.get("completed_at") or log["started_at"],
                "Status": log.get("status", "success"),
                "Duration (ms)": log.get("duration_ms") or 0,
            }
        )

if gantt_data:
    df_gantt = pd.DataFrame(gantt_data)
    color_map = {"success": "#22c55e", "error": "#ef4444", "skipped": "#6b7280"}
    fig = px.timeline(
        df_gantt,
        x_start="Start",
        x_end="Finish",
        y="Agent",
        color="Status",
        color_discrete_map=color_map,
        hover_data=["Duration (ms)"],
    )
    fig.update_layout(height=350, margin=dict(l=0, r=0, t=10, b=0))
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Timestamps not available for Gantt chart — showing table only.")

st.divider()

# ---------------------------------------------------------------------------
# Log table
# ---------------------------------------------------------------------------
st.subheader("📋 Step-by-Step Log")

table_data = []
for i, log in enumerate(logs):
    table_data.append(
        {
            "#": i + 1,
            "Agent": log.get("agent_name", ""),
            "Topic In": log.get("topic_in") or "—",
            "Topic Out": log.get("topic_out") or "—",
            "Status": log.get("status", ""),
            "Duration (ms)": log.get("duration_ms") or 0,
            "Started": (log.get("started_at") or "")[:19].replace("T", " "),
            "Error": (log.get("error_message") or "")[:80],
        }
    )

df_table = pd.DataFrame(table_data)
selected_rows = st.dataframe(
    df_table,
    use_container_width=True,
    height=300,
    on_select="rerun",
    selection_mode="single-row",
)

# ---------------------------------------------------------------------------
# Input / Output JSON Inspector
# ---------------------------------------------------------------------------
st.divider()
st.subheader("🔎 Payload Inspector")

selected_indices = (
    selected_rows.selection.get("rows", []) if hasattr(selected_rows, "selection") else []
)

if selected_indices:
    row_idx = selected_indices[0]
    log = logs[row_idx]

    st.markdown(f"**Agent:** `{log.get('agent_name', '')}` | **Status:** `{log.get('status', '')}` | **Duration:** `{log.get('duration_ms') or 0}ms`")
    if log.get("error_message"):
        st.error(f"Error: {log['error_message']}")

    inp_col, out_col = st.columns(2)

    with inp_col:
        st.markdown("**Input Payload**")
        input_payload = log.get("input_payload") or {}
        try:
            st.json(input_payload)
        except Exception:
            st.code(str(input_payload), language="json")

    with out_col:
        st.markdown("**Output Payload**")
        output_payload = log.get("output_payload")
        if output_payload:
            try:
                st.json(output_payload)
            except Exception:
                st.code(str(output_payload), language="json")
        else:
            st.caption("No output payload (agent did not publish an event).")
else:
    st.info("Click a row in the table above to inspect its input/output payloads.")
