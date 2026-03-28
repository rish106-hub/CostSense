"""Reusable agent status card widget for the Pipeline page."""

from __future__ import annotations

import streamlit as st

AGENT_LABELS = {
    "agent_01_data_connector": ("01", "Data Connector", "raw.spend"),
    "agent_02_normalization": ("02", "Normalization", "normalized.spend"),
    "agent_03_anomaly_detection": ("03", "Anomaly Detection", "anomaly.detected"),
    "agent_04_root_cause": ("04", "Root Cause (LLM)", "anomaly.enriched"),
    "agent_05_prioritization": ("05", "Prioritization", "anomaly.scored"),
    "agent_06_merge": ("06", "Merge", "anomaly.ready"),
    "agent_07_action_dispatcher": ("07", "Action Dispatcher", "action.*"),
    "agent_08_workflow_executor": ("08", "Workflow Executor", "—"),
    "agent_09_audit_trail": ("09", "Audit Trail", "ALL topics"),
}

STATUS_COLORS = {
    "active": "#22c55e",    # green
    "processing": "#f59e0b",  # amber
    "idle": "#6b7280",       # gray
    "error": "#ef4444",      # red
}


def render_agent_grid(process_logs: list[dict], event_counts: dict[str, int]) -> None:
    """
    Render a 3-column grid of agent status cards.

    Args:
        process_logs: List of process log entries from the API
        event_counts: Dict of {topic: count} from the bus
    """
    # Compute per-agent stats from process logs
    agent_stats: dict[str, dict] = {}
    for log in process_logs:
        name = log.get("agent_name", "")
        if name not in agent_stats:
            agent_stats[name] = {
                "count": 0,
                "errors": 0,
                "total_ms": 0,
                "last_seen": None,
            }
        agent_stats[name]["count"] += 1
        if log.get("status") == "error":
            agent_stats[name]["errors"] += 1
        if log.get("duration_ms"):
            agent_stats[name]["total_ms"] += log["duration_ms"]
        if log.get("started_at"):
            agent_stats[name]["last_seen"] = log["started_at"]

    agents = list(AGENT_LABELS.keys())
    cols = st.columns(3)

    for idx, agent_key in enumerate(agents):
        col = cols[idx % 3]
        number, label, topic_out = AGENT_LABELS[agent_key]
        stats = agent_stats.get(agent_key, {})
        count = stats.get("count", 0)
        errors = stats.get("errors", 0)
        avg_ms = (
            round(stats["total_ms"] / count)
            if count > 0 and stats.get("total_ms")
            else 0
        )

        if errors > 0:
            status = "error"
        elif count > 0:
            status = "active"
        else:
            status = "idle"

        color = STATUS_COLORS[status]

        with col:
            st.markdown(
                f"""
                <div style="border:1px solid {color}; border-radius:8px; padding:12px;
                            margin-bottom:10px; background:#1e1e2e;">
                  <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:11px; color:#888;">AGENT {number}</span>
                    <span style="font-size:11px; color:{color}; font-weight:bold;">
                      {'● ' + status.upper()}
                    </span>
                  </div>
                  <div style="font-size:14px; font-weight:bold; margin:6px 0; color:#fff;">
                    {label}
                  </div>
                  <div style="font-size:11px; color:#aaa;">→ {topic_out}</div>
                  <div style="display:flex; gap:16px; margin-top:8px;">
                    <div>
                      <div style="font-size:18px; font-weight:bold; color:#fff;">{count}</div>
                      <div style="font-size:10px; color:#888;">processed</div>
                    </div>
                    <div>
                      <div style="font-size:18px; font-weight:bold; color:#{'ef4444' if errors > 0 else 'fff'};">{errors}</div>
                      <div style="font-size:10px; color:#888;">errors</div>
                    </div>
                    <div>
                      <div style="font-size:18px; font-weight:bold; color:#fff;">{avg_ms}ms</div>
                      <div style="font-size:10px; color:#888;">avg latency</div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
