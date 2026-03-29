"""Reusable anomaly detail card for the Anomaly Dashboard."""

from __future__ import annotations

import streamlit as st

STATUS_BADGES = {
    "detected": ("[DETECTED]", "#6b7280"),
    "pending_approval": ("[PENDING]", "#f59e0b"),
    "approved": ("[APPROVED]", "#22c55e"),
    "auto_executed": ("[EXECUTED]", "#3b82f6"),
    "rejected": ("[REJECTED]", "#ef4444"),
    "queued_for_execution": ("[QUEUED]", "#8b5cf6"),
}

TYPE_ICONS = {
    "duplicate_payment": "[PAYMENT]",
    "cloud_waste": "[CLOUD]",
    "unused_saas": "[SAAS]",
    "vendor_rate_anomaly": "[RATE]",
    "sla_penalty_risk": "[SLA]",
    "unknown": "[UNKNOWN]",
}


def render_anomaly_card(anomaly: dict, show_approve_button: bool = False) -> bool:
    """
    Render a single anomaly detail card.

    Returns True if the approve button was clicked.
    """
    anomaly_id = anomaly.get("anomaly_id", "")
    anomaly_type = anomaly.get("anomaly_type", "unknown")
    status = anomaly.get("status", "detected")
    icon = TYPE_ICONS.get(anomaly_type, "❓")
    status_icon, status_color = STATUS_BADGES.get(status, ("●", "#6b7280"))

    aps = anomaly.get("aps_score") or 0
    as_score = anomaly.get("as_score") or 0
    confidence = anomaly.get("confidence") or 0
    complexity = anomaly.get("complexity") or 1

    approved = False

    with st.expander(
        f"{icon} {anomaly_type.replace('_', ' ').title()} — "
        f"APS: {aps:.2f} | {status_icon} {status.replace('_', ' ').upper()}",
        expanded=False,
    ):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("APS Score", f"{aps:.2f}")
        col2.metric("AS Score", f"{as_score:.2f}")
        col3.metric("Confidence", f"{confidence:.0%}")
        col4.metric("Complexity", str(complexity))

        st.markdown("---")
        info_col, score_col = st.columns(2)

        with info_col:
            st.markdown("**Detection Details**")
            if anomaly.get("vendor"):
                st.write(f"**Vendor:** {anomaly['vendor']}")
            if anomaly.get("amount"):
                st.write(f"**Amount:** ₹{anomaly['amount']:,.0f}")
            if anomaly.get("department"):
                st.write(f"**Department:** {anomaly['department']}")
            if anomaly.get("transaction_date"):
                st.write(f"**Date:** {anomaly['transaction_date']}")
            flags = anomaly.get("rule_flags") or []
            if flags:
                st.write(f"**Rule Flags:** `{', '.join(flags)}`")
            if anomaly.get("isolation_score") is not None:
                st.write(f"**Isolation Score:** `{anomaly['isolation_score']:.4f}`")

        with score_col:
            st.markdown("**Score Breakdown**")
            fi = anomaly.get("financial_impact") or 0
            fr = anomaly.get("frequency_rank") or 0
            re = anomaly.get("recoverability_ease") or 0
            sr = anomaly.get("severity_risk") or 0
            st.write(f"**FI (40%):** {fi:.2f}")
            st.write(f"**FR (25%):** {fr:.2f}")
            st.write(f"**RE (20%):** {re:.2f}")
            st.write(f"**SR (15%):** {sr:.2f}")
            if anomaly.get("model_used"):
                st.caption(f"LLM: `{anomaly['model_used']}`")

        if anomaly.get("root_cause"):
            st.markdown("**Root Cause Analysis**")
            st.info(anomaly["root_cause"])

        if anomaly.get("suggested_action"):
            st.markdown("**Recommended Action**")
            st.success(anomaly["suggested_action"])

        if show_approve_button and status == "pending_approval":
            approved_by = st.text_input(
                "Approved by", value="CFO", key=f"approved_by_{anomaly_id}"
            )
            notes = st.text_area("Notes (optional)", key=f"notes_{anomaly_id}", height=60)
            if st.button(f"Approve Action", key=f"approve_{anomaly_id}", type="primary"):
                approved = True

        st.caption(f"ID: `{anomaly_id}` | Detected: {anomaly.get('detected_at', 'N/A')}")

    return approved
