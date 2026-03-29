"""
GET  /anomalies                    — all anomalies ranked by APS
GET  /anomalies/pending-approval   — anomalies awaiting human sign-off
POST /anomalies/{id}/approve       — approve a pending anomaly
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import (
    get_anomaly_by_id,
    get_anomalies,
    get_session,
)
from models.schemas import (
    AnomalyListResponse,
    AnomalyOut,
    ApproveAnomalyIn,
    ApproveAnomalyOut,
    PendingApprovalResponse,
)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


def _orm_to_schema(row) -> AnomalyOut:
    """Convert an ORM Anomaly row to AnomalyOut schema."""
    return AnomalyOut(
        anomaly_id=str(row.anomaly_id),
        record_id=str(row.record_id) if row.record_id else None,
        process_id=str(row.process_id),
        anomaly_type=row.anomaly_type,
        isolation_score=row.isolation_score,
        rule_flags=row.rule_flags or [],
        root_cause=row.root_cause,
        confidence=row.confidence,
        suggested_action=row.suggested_action,
        model_used=row.model_used,
        as_score=row.as_score,
        aps_score=row.aps_score,
        financial_impact=row.financial_impact,
        frequency_rank=row.frequency_rank,
        recoverability_ease=row.recoverability_ease,
        severity_risk=row.severity_risk,
        complexity=row.complexity,
        approval_needed=row.approval_needed,
        status=row.status,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        approval_notes=row.approval_notes,
        detected_at=row.detected_at,
        updated_at=row.updated_at,
        # Flattened spend record fields (optional, denormalized from event payload)
        vendor=None,
        amount=None,
        currency=None,
        department=None,
        category=None,
        transaction_date=None,
    )


@router.get("", response_model=AnomalyListResponse)
async def list_anomalies(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    process_id: Optional[str] = Query(default=None, description="Filter by process run"),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Return all anomalies sorted by APS descending, optionally filtered by status or process."""
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info("list_anomalies.request", status=status, process_id=process_id, limit=limit)
    
    rows = await get_anomalies(session, status=status, process_id=process_id, limit=limit)
    
    logger.info("list_anomalies.fetched", count=len(rows), process_id=process_id)
    
    anomalies = [_orm_to_schema(r) for r in rows]

    # Compute exposure and recovery totals
    total_exposure = sum(
        (a.as_score or 0) * 10000  # Approximate INR exposure from AS score
        for a in anomalies
        if a.status not in ("auto_executed", "approved")
    )
    total_recovered = sum(
        (a.as_score or 0) * 8500
        for a in anomalies
        if a.status in ("auto_executed", "approved")
    )

    return AnomalyListResponse(
        count=len(anomalies),
        total_exposure_inr=round(total_exposure, 2),
        total_recovered_inr=round(total_recovered, 2),
        anomalies=anomalies,
    )


@router.get("/pending-approval", response_model=PendingApprovalResponse)
async def list_pending_approval(
    session: AsyncSession = Depends(get_session),
):
    """Return anomalies currently waiting for human approval."""
    rows = await get_anomalies(session, status="pending_approval")
    anomalies = [_orm_to_schema(r) for r in rows]
    return PendingApprovalResponse(pending=anomalies, count=len(anomalies))


@router.post("/{anomaly_id}/approve", response_model=ApproveAnomalyOut)
async def approve_anomaly_endpoint(
    anomaly_id: str,
    body: ApproveAnomalyIn,
    session: AsyncSession = Depends(get_session),
):
    """Approve a pending anomaly and trigger workflow execution."""
    row = await get_anomaly_by_id(session, anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")
    if row.status != "pending_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Anomaly is not pending approval (current status: {row.status})",
        )

    from agents.agent_08_workflow_executor import WorkflowExecutorAgent
    from core.bus import bus
    executor = WorkflowExecutorAgent.__new__(WorkflowExecutorAgent)
    executor._bus = bus

    await executor.execute_approved(
        anomaly_id=anomaly_id,
        approved_by=body.approved_by,
        notes=body.notes,
    )

    updated_row = await get_anomaly_by_id(session, anomaly_id)
    return ApproveAnomalyOut(
        message=f"Anomaly {anomaly_id} approved and execution triggered.",
        anomaly=_orm_to_schema(updated_row),
    )
