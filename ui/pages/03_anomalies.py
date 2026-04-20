"""
Page 3 — Anomaly Management & Approval Gate
"""

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Anomalies — CostSense AI", page_icon="⚡", layout="wide")

from ui.components.theme import inject_global_css, page_header, kpi_card, badge
from ui.components.api_client import (
    approve_anomaly,
    get_anomalies,
    get_health,
    get_pending_approval,
)

inject_global_css()

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding: 12px 4px 20px;">
        <div style="font-size:1.1rem; font-weight:800; color:#e8f0fe;">⚡ CostSense AI</div>
        <div style="font-size:10px; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-top:2px;">Anomaly Management</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    st.markdown('<div style="font-size:11px; font-weight:600; color:#4a6080; text-transform:uppercase; letter-spacing:0.1em; margin-bottom:8px;">Filters</div>', unsafe_allow_html=True)

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
    aps_threshold = st.slider("Min APS Score", 0.0, 10.0, 0.0, 0.5)
    st.divider()
    limit = st.number_input("Max records", 50, 1000, 200, step=50)

# ── Health check ───────────────────────────────────────────────
health = get_health()
if health is None:
    st.markdown('<div class="banner-error">Cannot reach API server.</div>', unsafe_allow_html=True)
    st.stop()

page_header("Anomaly Management", "Detected cost leakages ranked by Action Priority Score (APS).")

# ── Load data ──────────────────────────────────────────────────
status_param = status_filter[0] if len(status_filter) == 1 else None
resp = get_anomalies(status=status_param, limit=int(limit)) or {}
all_anomalies = resp.get("anomalies", [])

if status_filter and len(status_filter) > 1:
    all_anomalies = [a for a in all_anomalies if a.get("status") in status_filter]
if type_filter:
    all_anomalies = [a for a in all_anomalies if a.get("anomaly_type") in type_filter]
if aps_threshold > 0:
    all_anomalies = [a for a in all_anomalies if (a.get("aps_score") or 0) >= aps_threshold]

all_anomalies.sort(key=lambda x: x.get("aps_score") or 0, reverse=True)

# ── KPI row ────────────────────────────────────────────────────
total    = len(all_anomalies)
pending  = sum(1 for a in all_anomalies if a.get("status") == "pending_approval")
auto_ex  = sum(1 for a in all_anomalies if a.get("status") == "auto_executed")
approved = sum(1 for a in all_anomalies if a.get("status") == "approved")
exposure = resp.get("total_exposure_inr", 0)
recovered = resp.get("total_recovered_inr", 0)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(kpi_card("Total Anomalies", str(total), "in current filter", "red" if total > 0 else "default"), unsafe_allow_html=True)
with c2:
    st.markdown(kpi_card("Pending Approval", str(pending), "awaiting sign-off", "orange" if pending > 0 else "default"), unsafe_allow_html=True)
with c3:
    st.markdown(kpi_card("Auto-Executed", str(auto_ex), "resolved automatically", "green"), unsafe_allow_html=True)
with c4:
    st.markdown(kpi_card("Exposure", f"₹{exposure:,.0f}", "at risk", "red" if exposure > 0 else "default"), unsafe_allow_html=True)
with c5:
    st.markdown(kpi_card("Recovered", f"₹{recovered:,.0f}", "savings captured", "green" if recovered > 0 else "default"), unsafe_allow_html=True)

st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Approval Gate (top section if pending items exist) ─────────
pending_resp = get_pending_approval() or {}
pending_anomalies = pending_resp.get("anomalies", []) if pending_resp else []

if pending_anomalies:
    st.markdown(
        f'<div class="banner-warning">⚠ {len(pending_anomalies)} anomaly(s) require your approval before automated action is taken.</div>',
        unsafe_allow_html=True,
    )

    with st.expander(f"🔔  Approval Queue ({len(pending_anomalies)} pending)", expanded=True):
        for a in pending_anomalies:
            aid      = a.get("anomaly_id", "")
            atype    = a.get("anomaly_type", "unknown").replace("_", " ").title()
            aps      = a.get("aps_score") or 0
            conf     = a.get("confidence") or 0
            root     = a.get("root_cause") or "No root cause available."
            action   = a.get("suggested_action") or "Review and approve action."
            vendor   = a.get("vendor") or "—"
            dept     = a.get("department") or "—"
            severity = "HIGH" if aps > 7 else "MED" if aps > 4 else "LOW"
            sev_color = "red" if aps > 7 else "orange" if aps > 4 else "blue"

            with st.container():
                st.markdown(
                    f"""<div class="anomaly-card anomaly-card-pending">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                            <div>
                                <span class="badge badge-orange" style="margin-right:6px;">PENDING APPROVAL</span>
                                <span class="badge badge-{sev_color}">{severity} RISK</span>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:9px;color:#4a6080;">APS SCORE</div>
                                <div style="font-size:1.2rem;font-weight:700;color:#f59e0b;">{aps:.2f}</div>
                            </div>
                        </div>
                        <div style="font-size:12px;color:#8098b8;margin-bottom:8px;">
                            <strong style="color:#94a3b8;">Type:</strong> {atype}
                            &nbsp;·&nbsp; <strong style="color:#94a3b8;">Vendor:</strong> {vendor}
                            &nbsp;·&nbsp; <strong style="color:#94a3b8;">Dept:</strong> {dept}
                            &nbsp;·&nbsp; Confidence: {conf:.0%}
                        </div>
                        <div style="font-size:12px;color:#64748b;margin-bottom:4px;">
                            <strong style="color:#94a3b8;">Root Cause:</strong> {root[:200]}
                        </div>
                        <div style="font-size:12px;color:#64748b;">
                            <strong style="color:#94a3b8;">Suggested Action:</strong> {action[:200]}
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                col_by, col_notes, col_approve = st.columns([2, 3, 1])
                with col_by:
                    approved_by = st.text_input(
                        "Approved by", value="Operations Manager",
                        key=f"by_{aid}", label_visibility="collapsed",
                        placeholder="Your name / role",
                    )
                with col_notes:
                    notes = st.text_input(
                        "Notes", key=f"notes_{aid}", label_visibility="collapsed",
                        placeholder="Optional approval notes…",
                    )
                with col_approve:
                    if st.button("✓  Approve", key=f"approve_{aid}", type="primary", use_container_width=True):
                        with st.spinner("Approving…"):
                            result = approve_anomaly(aid, approved_by=approved_by or "Manager", notes=notes or None)
                        if result and "message" in result:
                            st.success(f"Approved!")
                            st.rerun()
                        else:
                            st.error(f"Failed: {result}")

                st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Charts row ─────────────────────────────────────────────────
if all_anomalies:
    df = pd.DataFrame(all_anomalies)

    st.markdown('<div class="section-title">Analysis</div>', unsafe_allow_html=True)
    ch1, ch2, ch3 = st.columns(3)

    with ch1:
        st.markdown("**By Type**")
        tc = df["anomaly_type"].value_counts().reset_index()
        tc.columns = ["type", "count"]
        tc["type"] = tc["type"].str.replace("_", " ").str.title()
        fig = px.bar(tc, x="count", y="type", orientation="h",
                     color="count", color_continuous_scale="Reds")
        fig.update_layout(showlegend=False, height=200,
                          margin=dict(l=0, r=0, t=0, b=0),
                          paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#8098b8",
                          coloraxis_showscale=False)
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True)

    with ch2:
        st.markdown("**APS Distribution**")
        if "aps_score" in df.columns:
            fig2 = px.histogram(df, x="aps_score", nbins=12,
                                color_discrete_sequence=["#f59e0b"],
                                labels={"aps_score": "APS Score"})
            fig2.update_layout(height=200, margin=dict(l=0, r=0, t=0, b=0),
                               paper_bgcolor="rgba(0,0,0,0)",
                               plot_bgcolor="rgba(0,0,0,0)",
                               font_color="#8098b8", showlegend=False)
            fig2.update_xaxes(showgrid=False)
            fig2.update_yaxes(showgrid=False)
            st.plotly_chart(fig2, use_container_width=True)

    with ch3:
        st.markdown("**Status Mix**")
        sd = df["status"].value_counts().reset_index()
        sd.columns = ["status", "count"]
        color_map = {
            "auto_executed": "#22c55e", "approved": "#22c55e",
            "pending_approval": "#f59e0b", "detected": "#3b82f6",
            "rejected": "#ef4444",
        }
        colors = [color_map.get(s, "#64748b") for s in sd["status"]]
        fig3 = px.pie(sd, values="count", names="status",
                      color_discrete_sequence=colors)
        fig3.update_layout(height=200, margin=dict(l=0, r=0, t=0, b=0),
                           paper_bgcolor="rgba(0,0,0,0)",
                           font_color="#8098b8",
                           legend=dict(font=dict(size=10)))
        st.plotly_chart(fig3, use_container_width=True)

    st.markdown('<div class="cs-divider"></div>', unsafe_allow_html=True)

# ── Anomaly Table ──────────────────────────────────────────────
st.markdown('<div class="section-title">All Anomalies</div>', unsafe_allow_html=True)

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

if all_anomalies:
    for a in all_anomalies:
        aid     = a.get("anomaly_id", "")
        atype   = a.get("anomaly_type", "unknown")
        status  = a.get("status", "detected")
        aps     = a.get("aps_score") or 0
        conf    = a.get("confidence") or 0
        vendor  = a.get("vendor") or "—"
        dept    = a.get("department") or "—"
        action  = a.get("suggested_action") or "Review required."
        sc      = STATUS_COLORS.get(status, "gray")
        tlabel  = TYPE_LABELS.get(atype, atype.replace("_", " ").title())
        bar_w   = int(aps * 10)
        bar_col = "#ef4444" if aps > 7 else "#f59e0b" if aps > 4 else "#3b82f6"

        with st.container():
            col_main, col_action = st.columns([7, 1])
            with col_main:
                st.markdown(
                    f"""<div class="anomaly-card">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">
                            <div>
                                <span class="badge badge-{sc}" style="margin-right:5px;">{status.replace('_', ' ').upper()}</span>
                                <span class="badge badge-gray">{tlabel}</span>
                            </div>
                            <div style="text-align:right;">
                                <span style="font-size:9px;color:#4a6080;">APS </span>
                                <span style="font-size:1rem;font-weight:700;color:{bar_col};">{aps:.2f}</span>
                                <span style="font-size:9px;color:#4a6080;">/10</span>
                            </div>
                        </div>
                        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">
                            Vendor: <span style="color:#8098b8;">{vendor}</span>
                            &nbsp;·&nbsp; {dept}
                            &nbsp;·&nbsp; Confidence: {conf:.0%}
                            &nbsp;·&nbsp; ID: {aid[:12]}…
                        </div>
                        <div style="font-size:12px;color:#64748b;">{action[:180]}</div>
                        <div class="score-bar-bg" style="margin-top:8px;">
                            <div class="score-bar" style="width:{bar_w}%;background:{bar_col};"></div>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )
            with col_action:
                if status == "pending_approval":
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    if st.button("Approve", key=f"qapprove_{aid}", type="primary", use_container_width=True):
                        with st.spinner():
                            res = approve_anomaly(aid, "Operations Manager")
                        if res and "message" in res:
                            st.success("Done!")
                            st.rerun()
                        else:
                            st.error("Failed")
else:
    st.markdown(
        '<div class="banner-info">No anomalies match the current filters. Run a pipeline from Data Ingestion to generate results.</div>',
        unsafe_allow_html=True,
    )
