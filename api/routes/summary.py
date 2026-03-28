"""GET /summary — CFO one-screen summary of the platform state."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.bus import bus
from core.db import get_anomalies, get_session
from models.schemas import AnomalyOut, CFOSummaryOut

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=CFOSummaryOut)
async def get_cfo_summary(session: AsyncSession = Depends(get_session)):
    """Return a CFO-level dashboard summary of all activity."""
    all_anomalies = await get_anomalies(session, limit=10000)

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

    return CFOSummaryOut(
        anomalies_detected=total,
        resolved=resolved,
        open=open_count,
        pending_approval=pending,
        total_exposure_inr=round(total_exposure, 2),
        total_recovered_inr=round(total_recovered, 2),
        recovery_rate_pct=recovery_rate,
        top_anomaly=top_anomaly,
        events_by_topic=bus.get_event_counts(),
        agents_active=9,
    )
