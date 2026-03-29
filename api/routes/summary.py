"""GET /summary — CFO one-screen summary of the platform state."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from core.bus import bus
from core.db import get_anomalies, get_session
from models.orm import ProcessLog
from models.schemas import AnomalyOut, CFOSummaryOut

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=CFOSummaryOut)
async def get_cfo_summary(
    session: AsyncSession = Depends(get_session),
    process_id: Optional[str] = Query(None, description="Filter by specific process run"),
):
    """Return a CFO-level dashboard summary of all activity or filtered by process."""
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info("summary.request", process_id=process_id)
    
    all_anomalies = await get_anomalies(session, limit=10000, process_id=process_id)
    
    logger.info("summary.anomalies_fetched", count=len(all_anomalies), process_id=process_id)

    total = len(all_anomalies)
    resolved = sum(1 for a in all_anomalies if a.status in ("auto_executed", "approved"))
    pending = sum(1 for a in all_anomalies if a.status == "pending_approval")
    open_count = total - resolved - pending

    # Approximate financial exposure from AS scores
    total_exposure = sum(
        float(a.as_score or 0) * 10000
        for a in all_anomalies
        if a.status not in ("auto_executed", "approved")
    )
    total_recovered = sum(
        float(a.as_score or 0) * 8500
        for a in all_anomalies
        if a.status in ("auto_executed", "approved")
    )
    pending_exposure = sum(
        float(a.as_score or 0) * 10000
        for a in all_anomalies
        if a.status == "pending_approval"
    )
    recovery_rate = (
        round(total_recovered / (total_exposure + total_recovered) * 100, 1)
        if (total_exposure + total_recovered) > 0
        else 0.0
    )

    # Top anomaly = highest APS
    top_anomaly = None
    if all_anomalies:
        sorted_by_aps = sorted(
            all_anomalies,
            key=lambda a: float(a.aps_score or 0),
            reverse=True,
        )
        top = sorted_by_aps[0]
        top_anomaly = AnomalyOut(
            anomaly_id=str(top.anomaly_id),
            record_id=str(top.record_id) if top.record_id else None,
            process_id=str(top.process_id),
            anomaly_type=top.anomaly_type,
            isolation_score=top.isolation_score,
            rule_flags=top.rule_flags or [],
            root_cause=top.root_cause,
            confidence=top.confidence,
            suggested_action=top.suggested_action,
            model_used=top.model_used,
            as_score=top.as_score,
            aps_score=top.aps_score,
            financial_impact=top.financial_impact,
            frequency_rank=top.frequency_rank,
            recoverability_ease=top.recoverability_ease,
            severity_risk=top.severity_risk,
            complexity=top.complexity,
            approval_needed=top.approval_needed,
            status=top.status,
            approved_by=top.approved_by,
            approved_at=top.approved_at,
            approval_notes=top.approval_notes,
            detected_at=top.detected_at,
            updated_at=top.updated_at,
        )

    # Build anomaly breakdown by type
    anomaly_breakdown = {}
    for anomaly in all_anomalies:
        atype = anomaly.anomaly_type or "unknown"
        anomaly_breakdown[atype] = anomaly_breakdown.get(atype, 0) + 1

    # Build status distribution
    status_distribution = {}
    for anomaly in all_anomalies:
        status = anomaly.status or "unknown"
        status_distribution[status] = status_distribution.get(status, 0) + 1

    # Get agent stats from process_logs table
    agent_stats = []
    
    # Define all agent names
    all_agent_names = [
        "agent_01_data_connector",
        "agent_02_normalization",
        "agent_03_anomaly_detection",
        "agent_04_root_cause",
        "agent_05_prioritization",
        "agent_06_merge",
        "agent_07_action_dispatcher",
        "agent_08_workflow_executor",
        "agent_09_audit_trail",
    ]
    
    for agent_name in all_agent_names:
        # Query stats for this agent
        stmt = select(
            func.count(ProcessLog.log_id).label("events_processed"),
            func.count(ProcessLog.error_message).label("errors"),
            func.avg(ProcessLog.duration_ms).label("avg_duration_ms"),
            func.max(ProcessLog.started_at).label("last_seen"),
        ).where(ProcessLog.agent_name == agent_name)
        
        result = await session.execute(stmt)
        row = result.one_or_none()
        
        if row:
            events_processed = row.events_processed or 0
            errors = row.errors or 0
            avg_duration = round(float(row.avg_duration_ms or 0), 1)
            last_seen = row.last_seen.isoformat() if row.last_seen else None
        else:
            events_processed = 0
            errors = 0
            avg_duration = 0
            last_seen = None
        
        agent_stats.append({
            "agent_name": agent_name,
            "events_processed": events_processed,
            "errors": errors,
            "avg_duration_ms": avg_duration,
            "last_seen": last_seen,
        })

    # Source stats (default)
    source_stats = {}

    return CFOSummaryOut(
        anomalies_detected=total,
        resolved=resolved,
        open=open_count,
        pending_approval=pending,
        total_exposure_inr=round(total_exposure, 2),
        total_recovered_inr=round(total_recovered, 2),
        pending_exposure_inr=round(pending_exposure, 2),
        recovery_rate_pct=recovery_rate,
        top_anomaly=top_anomaly,
        events_by_topic=bus.get_event_counts(),
        agents_active=9,
        anomaly_breakdown=anomaly_breakdown,
        status_distribution=status_distribution,
        agent_stats=agent_stats,
        source_stats=source_stats,
    )
