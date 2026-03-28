"""
Page 5 — CFO Summary

High-level executive view: recovery metrics, top anomaly, agent health,
and spend data source breakdown.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components.anomaly_card import render_anomaly_card
from ui.components.api_client import get_anomalies, get_health, get_summary

st.set_page_config(page_title="CFO Summary — CostSense AI", page_icon="💼", layout="wide")

st.title("💼 CFO Summary")
st.caption("Executive overview of cost intelligence findings and recovery impact.")

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
health = get_health()
if health is None:
    st.error("⚠️ Cannot reach API server.")
    st.stop()

# ---------------------------------------------------------------------------
# Load summary data
# ---------------------------------------------------------------------------
summary = get_summary()
if not summary:
    st.warning("Summary data unavailable. Run a pipeline first.")
    st.stop()

# ---------------------------------------------------------------------------
# Recovery Metrics
# ---------------------------------------------------------------------------
st.subheader("💰 Recovery Impact")

total_exposure = summary.get("total_exposure", 0)
total_recovered = summary.get("total_recovered", 0)
pending_exposure = summary.get("pending_exposure", 0)
recovery_rate = (total_recovered / total_exposure * 100) if total_exposure > 0 else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Exposure Detected", f"₹{total_exposure:,.0f}")
k2.metric("Recovered / Resolved", f"₹{total_recovered:,.0f}", delta=f"+₹{total_recovered:,.0f}")
k3.metric("Still Pending", f"₹{pending_exposure:,.0f}")
k4.metric("Recovery Rate", f"{recovery_rate:.1f}%")

st.divider()

# ---------------------------------------------------------------------------
# Anomaly breakdown
# ---------------------------------------------------------------------------
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("📊 Anomaly Breakdown")
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
    st.subheader("📈 Status Distribution")
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
st.subheader("🔥 Highest Priority Anomaly")
top_anomaly = summary.get("top_anomaly")
if top_anomaly:
    render_anomaly_card(top_anomaly, show_approve_button=False)
else:
    st.info("No anomalies detected yet.")

st.divider()

# ---------------------------------------------------------------------------
# Agent health table
# ---------------------------------------------------------------------------
st.subheader("🤖 Agent Health")
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
st.subheader("🗃️ Data Sources")
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
    if st.button("🔄 Refresh Summary"):
        st.rerun()
