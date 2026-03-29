"""
Page 2 — Live Pipeline Visualization

Shows real-time agent activity, event bus feed, and pipeline topology.
Auto-refreshes every 3 seconds using st.rerun().
"""

import time
from collections import defaultdict

import pandas as pd
import streamlit as st

from ui.components.agent_status_card import render_agent_grid
from ui.components.api_client import (
    get_bus_events,
    get_health,
    get_process_logs,
    list_processes,
)

st.set_page_config(page_title="Pipeline — CostSense AI", page_icon="🔄", layout="wide")

# Initialize session state for process selection
if "pipeline_selected_process_id" not in st.session_state:
    st.session_state.pipeline_selected_process_id = None

st.title("Live Pipeline")
st.caption("Watch agents process spend data in real time.")

# ---------------------------------------------------------------------------
# API health check
# ---------------------------------------------------------------------------
health = get_health()
if health is None:
    st.error("Cannot reach API server.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Controls")
    auto_refresh = st.checkbox("Auto-refresh (3s)", value=False)
    refresh_interval = st.slider("Refresh interval (s)", 1, 10, 3)

    st.divider()
    st.header("Filter by Process")
    processes_resp = list_processes(limit=20)
    processes = processes_resp.get("processes", []) if processes_resp else []

    process_options = {"All processes": None}
    first_process_id = None
    for p in processes:
        label = f"{p['process_id'][:8]}… ({p.get('record_count', '?')} records)"
        process_options[label] = p["process_id"]
        if first_process_id is None:
            first_process_id = p["process_id"]

    # Determine default: use stored selection, or fall back to most recent/current process
    default_process_id = st.session_state.pipeline_selected_process_id
    if default_process_id is None and first_process_id is not None:
        default_process_id = first_process_id
    
    # Find index for default value
    default_index = 0
    if default_process_id is not None:
        options_list = list(process_options.items())
        for idx, (label, pid) in enumerate(options_list):
            if pid == default_process_id:
                default_index = idx
                break
    
    selected_label = st.selectbox("Process run", list(process_options.keys()), index=default_index)
    selected_process_id = process_options[selected_label]
    # Store selection in session state
    st.session_state.pipeline_selected_process_id = selected_process_id

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
logs_resp = get_process_logs(process_id=selected_process_id, limit=500)
process_logs = logs_resp.get("logs", []) if logs_resp else []

events_resp = get_bus_events(limit=100)
bus_events = events_resp.get("events", []) if events_resp else []

# Debug: Show what agents we have logs for
st.sidebar.caption("DEBUG: Agent logs in response")
agent_names_in_logs = set()
for log in process_logs:
    agent_names_in_logs.add(log.get("agent_name", "unknown"))
st.sidebar.write(f"Agents with logs: {sorted(agent_names_in_logs)}")
st.sidebar.write(f"Total logs returned: {len(process_logs)}")

# Compute event counts per topic
event_counts: dict[str, int] = defaultdict(int)
for ev in bus_events:
    topic = ev.get("topic", "unknown")
    event_counts[topic] += 1

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
total_events = health.get("events_processed", 0)
error_count = sum(1 for log in process_logs if log.get("status") == "error")
success_count = sum(1 for log in process_logs if log.get("status") == "success")
avg_duration = (
    round(
        sum(log.get("duration_ms", 0) or 0 for log in process_logs) / len(process_logs)
    )
    if process_logs
    else 0
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Events Processed", total_events)
k2.metric("Log Entries (current filter)", len(process_logs))
k3.metric("Errors", error_count, delta=None if error_count == 0 else f"⚠️ {error_count}")
k4.metric("Avg Agent Latency", f"{avg_duration}ms")

st.divider()

# ---------------------------------------------------------------------------
# Agent Activity Grid
# ---------------------------------------------------------------------------
st.subheader("Agent Activity")
render_agent_grid(process_logs, dict(event_counts))

st.divider()

# ---------------------------------------------------------------------------
# Pipeline Topology (static Mermaid-style using markdown + badges)
# ---------------------------------------------------------------------------
with st.expander("Pipeline Topology", expanded=False):
    topics = [
        ("raw.spend", "Agent 01 → raw.spend"),
        ("normalized.spend", "Agent 02 → normalized.spend"),
        ("anomaly.detected", "Agent 03 → anomaly.detected"),
        ("anomaly.enriched", "Agent 04 → anomaly.enriched"),
        ("anomaly.scored", "Agent 05 → anomaly.scored"),
        ("anomaly.ready", "Agent 06 → anomaly.ready"),
        ("action.approval_needed", "Agent 07 → action.approval_needed"),
        ("action.auto_execute", "Agent 07 → action.auto_execute"),
    ]

    cols = st.columns(4)
    for i, (topic, label) in enumerate(topics):
        count = event_counts.get(topic, 0)
        color = "#22c55e" if count > 0 else "#374151"
        with cols[i % 4]:
            st.markdown(
                f"""<div style="border:1px solid {color}; border-radius:6px; padding:8px;
                              margin-bottom:8px; background:#1e1e2e; font-size:12px;">
                    <div style="color:#aaa;">{label}</div>
                    <div style="font-size:20px; font-weight:bold; color:{color};">{count}</div>
                    <div style="font-size:10px; color:#666;">events</div>
                    </div>""",
                unsafe_allow_html=True,
            )

st.divider()

# ---------------------------------------------------------------------------
# Event Feed
# ---------------------------------------------------------------------------
st.subheader("Recent Event Bus Activity")

if bus_events:
    feed_data = []
    for ev in bus_events[:50]:
        feed_data.append(
            {
                "Time": ev.get("timestamp", "")[:19].replace("T", " "),
                "Topic": ev.get("topic", ""),
                "Source Agent": ev.get("source_agent", ""),
                "Process ID": (ev.get("process_id") or "")[:8] + "…"
                if ev.get("process_id")
                else "—",
                "Event ID": (ev.get("event_id") or "")[:8] + "…",
            }
        )
    df_feed = pd.DataFrame(feed_data)
    st.dataframe(df_feed, use_container_width=True, height=250)
else:
    st.info("No events in bus history. Run a pipeline to see activity here.")

st.divider()

# ---------------------------------------------------------------------------
# Process Log Table (for selected process)
# ---------------------------------------------------------------------------
st.subheader("📋 Agent Execution Log")

if process_logs:
    log_data = []
    for log in process_logs:
        log_data.append(
            {
                "Agent": log.get("agent_name", "").replace("agent_0", "A").replace("agent_", "A"),
                "Topic In": log.get("topic_in") or "—",
                "Topic Out": log.get("topic_out") or "—",
                "Status": log.get("status", ""),
                "Duration (ms)": log.get("duration_ms") or 0,
                "Started": (log.get("started_at") or "")[:19].replace("T", " "),
                "Error": log.get("error_message") or "",
            }
        )
    df_logs = pd.DataFrame(log_data)

    # Color-code status
    def highlight_status(row):
        if row["Status"] == "error":
            return ["background-color: #3b1a1a"] * len(row)
        elif row["Status"] == "success":
            return ["background-color: #1a2e1a"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df_logs.style.apply(highlight_status, axis=1),
        use_container_width=True,
        height=350,
    )
else:
    if selected_process_id:
        st.info("No log entries found for this process run.")
    else:
        st.info("Run a pipeline from the **Data Input** page to see execution logs here.")

# ---------------------------------------------------------------------------
# Auto-refresh
# ---------------------------------------------------------------------------
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
