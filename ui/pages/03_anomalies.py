"""
Page 3 — Anomaly Dashboard + Approval Gate

KPI row, filterable anomaly table, charts, and a dedicated approval gate
for anomalies awaiting CFO sign-off.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from ui.components.anomaly_card import render_anomaly_card
from ui.components.api_client import (
    approve_anomaly,
    get_anomalies,
    get_health,
    get_pending_approval,
)

st.set_page_config(page_title="Anomalies — CostSense AI", page_icon="�", layout="wide")

st.title("Anomaly Dashboard")
st.caption("All detected anomalies, ranked by Action Priority Score (APS).")

# ---------------------------------------------------------------------------
# API health check
# ---------------------------------------------------------------------------
health = get_health()
if health is None:
    st.error("Cannot reach API server.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    status_filter = st.multiselect(
        "Status",
        ["detected", "pending_approval", "approved", "auto_executed", "rejected"],
        default=[],
        help="Leave empty to show all",
    )
    type_filter = st.multiselect(
        "Anomaly Type",
        ["duplicate_payment", "cloud_waste", "unused_saas", "vendor_rate_anomaly", "sla_penalty_risk"],
        default=[],
    )
    aps_threshold = st.slider("Minimum APS", 0.0, 10.0, 0.0, 0.5)
    st.divider()
    limit = st.number_input("Max records to load", 50, 500, 200, step=50)

# ---------------------------------------------------------------------------
# Load anomalies
# ---------------------------------------------------------------------------
status_param = status_filter[0] if len(status_filter) == 1 else None
resp = get_anomalies(status=status_param, limit=int(limit))
all_anomalies = resp.get("anomalies", []) if resp else []

# Client-side filtering
if status_filter:
    all_anomalies = [a for a in all_anomalies if a.get("status") in status_filter]
if type_filter:
    all_anomalies = [a for a in all_anomalies if a.get("anomaly_type") in type_filter]
if aps_threshold > 0:
    all_anomalies = [a for a in all_anomalies if (a.get("aps_score") or 0) >= aps_threshold]

# Sort by APS descending
all_anomalies.sort(key=lambda x: x.get("aps_score") or 0, reverse=True)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
total = len(all_anomalies)
pending = sum(1 for a in all_anomalies if a.get("status") == "pending_approval")
auto_exec = sum(1 for a in all_anomalies if a.get("status") == "auto_executed")
approved = sum(1 for a in all_anomalies if a.get("status") == "approved")
exposure = sum(a.get("amount") or 0 for a in all_anomalies)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Anomalies", total)
k2.metric("Pending Approval", pending)
k3.metric("Auto-Executed", auto_exec)
k4.metric("Approved", approved)
k5.metric("Total Exposure (₹)", f"₹{exposure:,.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Charts row
# ---------------------------------------------------------------------------
if all_anomalies:
    df = pd.DataFrame(all_anomalies)

    col_chart1, col_chart2, col_chart3 = st.columns(3)

    with col_chart1:
        st.subheader("By Type")
        type_counts = df["anomaly_type"].value_counts().reset_index()
        type_counts.columns = ["type", "count"]
        fig = px.bar(
            type_counts,
            x="count",
            y="type",
            orientation="h",
            color="count",
            color_continuous_scale="Reds",
            labels={"count": "Count", "type": ""},
        )
        fig.update_layout(showlegend=False, height=250, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

    with col_chart2:
        st.subheader("Exposure by Type")
        if "amount" in df.columns:
            exp_by_type = df.groupby("anomaly_type")["amount"].sum().reset_index()
            exp_by_type.columns = ["type", "amount"]
            fig2 = px.pie(
                exp_by_type,
                values="amount",
                names="type",
                color_discrete_sequence=px.colors.sequential.RdBu,
            )
            fig2.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig2, use_container_width=True)

    with col_chart3:
        st.subheader("APS Distribution")
        if "aps_score" in df.columns:
            fig3 = px.histogram(
                df,
                x="aps_score",
                nbins=15,
                color_discrete_sequence=["#f59e0b"],
                labels={"aps_score": "APS Score"},
            )
            fig3.update_layout(height=250, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig3, use_container_width=True)

    st.divider()

# ---------------------------------------------------------------------------
# Anomaly Table
# ---------------------------------------------------------------------------
st.subheader("Anomaly Table")

if all_anomalies:
    df = pd.DataFrame(all_anomalies)
    table_cols = [
        "anomaly_type", "vendor", "amount", "department",
        "as_score", "aps_score", "confidence", "complexity", "status",
    ]
    table_cols = [c for c in table_cols if c in df.columns]
    df_display = df[table_cols].copy()

    if "amount" in df_display.columns:
        df_display["amount"] = df_display["amount"].apply(
            lambda x: f"₹{x:,.0f}" if pd.notna(x) else "—"
        )
    if "confidence" in df_display.columns:
        df_display["confidence"] = df_display["confidence"].apply(
            lambda x: f"{x:.0%}" if pd.notna(x) else "—"
        )
    for score_col in ["as_score", "aps_score"]:
        if score_col in df_display.columns:
            df_display[score_col] = df_display[score_col].apply(
                lambda x: f"{x:.2f}" if pd.notna(x) else "—"
            )

    st.dataframe(df_display, use_container_width=True, height=300)
else:
    st.info("No anomalies match the current filters. Run a pipeline to generate anomalies.")

st.divider()

# ---------------------------------------------------------------------------
# Detailed Anomaly Cards
# ---------------------------------------------------------------------------
st.subheader("Anomaly Detail Cards")
if not all_anomalies:
    st.info("No anomalies to display.")
else:
    for anomaly in all_anomalies[:20]:
        if render_anomaly_card(anomaly, show_approve_button=False):
            pass  # approval handled separately below

st.divider()

# ---------------------------------------------------------------------------
# Approval Gate
# ---------------------------------------------------------------------------
st.subheader("Approval Gate")
st.caption("Anomalies awaiting CFO sign-off before automated action is taken.")

pending_resp = get_pending_approval()
pending_anomalies = pending_resp.get("anomalies", []) if pending_resp else []

if not pending_anomalies:
    st.success("No anomalies pending approval.")
else:
    st.warning(f"{len(pending_anomalies)} anomaly(s) require your approval.")

    for anomaly in pending_anomalies:
        approved_clicked = render_anomaly_card(anomaly, show_approve_button=True)
        if approved_clicked:
            anomaly_id = anomaly.get("anomaly_id", "")
            approved_by = st.session_state.get(f"approved_by_{anomaly_id}", "CFO")
            notes = st.session_state.get(f"notes_{anomaly_id}", "")
            with st.spinner("Submitting approval…"):
                result = approve_anomaly(anomaly_id, approved_by=approved_by, notes=notes or None)
            if result and "anomaly_id" in result:
                st.success(f"Anomaly `{anomaly_id[:8]}…` approved!")
                st.rerun()
            else:
                st.error(f"Approval failed: {result}")
