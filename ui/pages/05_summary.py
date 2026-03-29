"""
Page 5 — CFO Summary

High-level executive view: recovery metrics, top anomaly, agent health,
and spend data source breakdown.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components.anomaly_card import render_anomaly_card
from ui.components.api_client import get_anomalies, get_health, get_summary, list_processes

# Disable caching to force fresh API calls
st.set_page_config(page_title="CFO Summary — CostSense AI", page_icon="", layout="wide")

# Initialize session state for process selection
if "selected_process_id" not in st.session_state:
    st.session_state.selected_process_id = None
if "last_process_id" not in st.session_state:
    st.session_state.last_process_id = None

st.title("Summary")
st.caption("Executive overview of cost intelligence findings and recovery impact.")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
health = get_health()
if health is None:
    st.error("Cannot reach API server.")
    st.stop()

# ---------------------------------------------------------------------------
# Process selector
# ---------------------------------------------------------------------------
st.subheader("Select Process Run")
col1, col2 = st.columns([3, 1])

with col1:
    processes_resp = list_processes(limit=50)
    processes = processes_resp.get("processes", []) if processes_resp else []
    
    # Build dropdown options
    process_options = {"All Processes": None}
    first_process_id = None
    for p in processes:
        pid = p.get("process_id")
        ts = (p.get("started_at") or "Unknown")[:19].replace("T", " ")
        label = f"{ts} — {pid[:12] if pid else 'unknown'}…"
        if pid:
            process_options[label] = pid
            if first_process_id is None:
                first_process_id = pid
    
    # Determine default: use stored selection, or fall back to most recent/current process
    default_process_id = st.session_state.selected_process_id
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
    
    selected_label = st.selectbox(
        "View summary for:",
        list(process_options.keys()),
        index=default_index,
        key="process_selector",
    )
    selected_process_id = process_options[selected_label]
    # Store selection in session state
    st.session_state.selected_process_id = selected_process_id

with col2:
    if st.button("Refresh", key="refresh_summary"):
        st.session_state.selected_process_id = None
        st.session_state.last_process_id = None
        st.rerun()

# ---------------------------------------------------------------------------
# Load summary data
# ---------------------------------------------------------------------------
if selected_process_id != st.session_state.last_process_id:
    st.session_state.last_process_id = selected_process_id

# Also fetch raw anomalies for debugging
raw_response = get_anomalies(limit=10000, status=None, process_id=selected_process_id) if selected_process_id else None
raw_anomalies = raw_response.get("anomalies", []) if raw_response and isinstance(raw_response, dict) else []

summary = get_summary(process_id=selected_process_id)

# Debug info
with st.expander("Debug Info", expanded=False):
    st.write(f"Selected Process ID: {selected_process_id}")
    st.write(f"Raw anomalies fetched: {len(raw_anomalies) if raw_anomalies else 0}")
    if raw_anomalies and len(raw_anomalies) > 0:
        st.write("Sample anomalies (first 3):")
        for anomaly in raw_anomalies[:3]:
            st.json({
                "anomaly_id": anomaly.get("anomaly_id"),
                "process_id": anomaly.get("process_id"),
                "status": anomaly.get("status"),
                "amount": anomaly.get("amount"),
            })
    st.divider()
    st.write("Full Summary Response:")
    st.json(summary)
if not summary or summary is None:
    st.error("Unable to load summary data. Make sure the API is running and a pipeline has been executed.")
    st.stop()

# Handle error responses from API
if isinstance(summary, dict) and "error" in summary:
    st.error(f"API Error: {summary.get('error')}")
    st.stop()

# Check if we have valid data
total_anomalies = summary.get("anomalies_detected", 0)
if total_anomalies == 0:
    st.warning("Summary data is empty. Run a pipeline first to generate anomalies.")
    st.stop()

# ---------------------------------------------------------------------------
# Recovery Metrics
# ---------------------------------------------------------------------------
st.subheader("Recovery Impact")

total_exposure = summary.get("total_exposure_inr", 0)
total_recovered = summary.get("total_recovered_inr", 0)
pending_exposure = summary.get("pending_exposure_inr", 0)
recovery_rate = summary.get("recovery_rate_pct", 0)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Exposure Detected", f"₹{total_exposure:,.0f}")
k2.metric("Recovered / Resolved", f"₹{total_recovered:,.0f}", delta=f"+₹{total_recovered:,.0f}")
k3.metric("Pending Approval", f"₹{pending_exposure:,.0f}")
k4.metric("Recovery Rate", f"{recovery_rate:.1f}%")

st.divider()

# ---------------------------------------------------------------------------
# Anomaly breakdown
# ---------------------------------------------------------------------------
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("Anomaly Breakdown")
    breakdown = summary.get("anomaly_breakdown", {})
    if breakdown:
        df_breakdown = pd.DataFrame(
            list(breakdown.items()), columns=["Type", "Count"]
        ).sort_values("Count", ascending=False)
        fig = px.bar(
            df_breakdown,
            x="Count",
            y="Type",
            orientation="h",
            color="Count",
            color_continuous_scale="Oranges",
        )
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No anomaly breakdown data yet.")

with col_right:
    st.subheader("Status Distribution")
    status_dist = summary.get("status_distribution", {})
    if status_dist:
        df_status = pd.DataFrame(
            list(status_dist.items()), columns=["Status", "Count"]
        )
        fig2 = px.pie(
            df_status,
            values="Count",
            names="Status",
            color_discrete_sequence=["#22c55e", "#f59e0b", "#3b82f6", "#ef4444", "#6b7280"],
        )
        fig2.update_layout(height=280, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No status data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Top anomaly
# ---------------------------------------------------------------------------
st.subheader("Highest Priority Anomaly")
top_anomaly = summary.get("top_anomaly")
if top_anomaly:
    render_anomaly_card(top_anomaly, show_approve_button=False)
else:
    st.info("No anomalies detected yet.")

st.divider()

# ---------------------------------------------------------------------------
# Agent health table
# ---------------------------------------------------------------------------
st.subheader("Agent Health")
agent_stats = summary.get("agent_stats", [])
if agent_stats:
    df_agents = pd.DataFrame(agent_stats)
    display_cols = [c for c in ["agent_name", "events_processed", "errors", "avg_duration_ms", "last_seen"] if c in df_agents.columns]
    st.dataframe(df_agents[display_cols], use_container_width=True, height=300)
else:
    st.info("No agent activity recorded yet.")

st.divider()

# ---------------------------------------------------------------------------
# Data source breakdown
# ---------------------------------------------------------------------------
st.subheader("Data Sources")
source_stats = summary.get("source_stats", {})
if source_stats:
    df_sources = pd.DataFrame(
        list(source_stats.items()), columns=["Source", "Records Ingested"]
    ).sort_values("Records Ingested", ascending=False)
    fig3 = px.bar(
        df_sources,
        x="Source",
        y="Records Ingested",
        color="Records Ingested",
        color_continuous_scale="Blues",
    )
    fig3.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
    st.plotly_chart(fig3, use_container_width=True)
else:
    st.info("No source data yet.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
col_f1, col_f2 = st.columns(2)
with col_f1:
    st.caption(f"API version: {health.get('version', '?')} | Events on bus: {health.get('events_processed', 0)}")
with col_f2:
    if st.button("Refresh Summary"):
        st.rerun()
