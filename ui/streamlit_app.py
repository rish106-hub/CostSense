"""
CostSense AI — Main Streamlit Application

Entry point for the multi-page Streamlit UI.
Streamlit's native multi-page routing auto-discovers pages/ directory.
This file provides the landing page / home screen.
"""

import streamlit as st

from ui.components.api_client import get_health, get_summary

st.set_page_config(
    page_title="CostSense AI",
    page_icon="�",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("CostSense AI")
st.subheader("Autonomous Cost Intelligence Platform")
st.caption(
    "Multi-agent system that detects enterprise cost leakage, scores anomalies by financial "
    "impact, and either auto-executes resolutions or routes them to a human approver."
)

st.divider()

# ---------------------------------------------------------------------------
# API status
# ---------------------------------------------------------------------------
health = get_health()

col_status, col_nav = st.columns([1, 2])

with col_status:
    if health:
        st.success(f"API Online — v{health.get('version', '?')}")
        st.metric("Events Processed", health.get("events_processed", 0))
    else:
        st.error("API Offline — start `python run.py` on port 8000")

with col_nav:
    st.markdown("""
    ### Navigation
    Use the sidebar to switch between pages:

    | Page | Description |
    |------|-------------|
    | **Data Input** | Generate synthetic data or upload your own CSV |
    | **Pipeline** | Watch agents process data in real time |
    | **Anomalies** | Review detected anomalies + approve actions |
    | **Process Logs** | Deep-dive into per-agent input/output trace |
    | **CFO Summary** | Executive recovery metrics and top findings |
    """)

st.divider()

# ---------------------------------------------------------------------------
# Quick stats (if data exists)
# ---------------------------------------------------------------------------
if health:
    summary = get_summary()
    if summary and summary.get("total_anomalies", 0) > 0:
        st.subheader("Quick Stats")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Total Anomalies", summary.get("total_anomalies", 0))
        q2.metric(
            "Total Exposure",
            f"₹{summary.get('total_exposure', 0):,.0f}",
        )
        q3.metric("Pending Approval", summary.get("pending_approval_count", 0))
        q4.metric(
            "Recovery Rate",
            f"{summary.get('recovery_rate', 0):.1f}%",
        )
    else:
        st.info("No pipeline data yet — go to **📥 Data Input** to get started.")

# ---------------------------------------------------------------------------
# Architecture diagram
# ---------------------------------------------------------------------------
with st.expander("System Architecture", expanded=False):
    st.markdown("""
    ### Multi-Agent Event Bus Architecture

    ```
    POST /ingest/* ──► Agent 01 (Data Connector) ──► raw.spend
                                                          │
                                               Agent 02 (Normalization) ──► normalized.spend
                                                          │
                                          Agent 03 (Anomaly Detection) ──► anomaly.detected
                                                      ╱         ╲
                             Agent 04 (Root Cause LLM)           Agent 05 (Prioritization)
                             anomaly.enriched ───────────────────── anomaly.scored
                                                      ╲         ╱
                                               Agent 06 (Merge) ──► anomaly.ready
                                                          │
                                           Agent 07 (Action Dispatcher)
                                                ╱                   ╲
                              action.approval_needed        action.auto_execute
                                                ╲                   ╱
                                           Agent 08 (Workflow Executor)

    Agent 09 (Audit Trail) ── listens to ALL 8 topics passively
    ```

    **Scoring Engine:**
    - `AS = (FI × 0.40) + (FR × 0.25) + (RE × 0.20) + (SR × 0.15)` → range 1–10
    - `APS = AS × confidence / complexity` → range 0–10
    - Route to approval if: `APS ≥ 4.0 AND complexity ≥ 2`
    """)
