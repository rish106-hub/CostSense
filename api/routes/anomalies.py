"""
GET    /anomalies                    — all anomalies ranked by APS
GET    /anomalies/pending-approval   — anomalies awaiting human sign-off
POST   /anomalies/{id}/approve       — approve a pending anomaly
POST   /anomalies/{id}/reject        — reject a pending anomaly
PATCH  /anomalies/{id}/assign        — assign anomaly to a reviewer
POST   /anomalies/bulk-approve       — approve multiple anomalies at once
POST   /anomalies/bulk-reject        — reject multiple anomalies at once
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import (
    assign_anomaly,
    bulk_approve_anomalies,
    bulk_reject_anomalies,
    get_anomalies,
    get_anomaly_by_id,
    get_session,
    reject_anomaly,
)
from models.schemas import (
    AnomalyListResponse,
    AnomalyOut,
    ApproveAnomalyIn,
    ApproveAnomalyOut,
    AssignAnomalyIn,
    AssignAnomalyOut,
    BulkApproveIn,
    BulkApproveOut,
    BulkRejectIn,
    BulkRejectOut,
    PendingApprovalResponse,
    RejectAnomalyIn,
    RejectAnomalyOut,
)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


def _orm_to_schema(row) -> AnomalyOut:
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
        assigned_to=row.assigned_to,
        rejected_by=row.rejected_by,
        rejection_reason=row.rejection_reason,
        rejected_at=row.rejected_at,
        detected_at=row.detected_at,
        updated_at=row.updated_at,
        vendor=None,
        amount=None,
        currency=None,
        department=None,
        category=None,
        transaction_date=None,
    )


@router.get("", response_model=AnomalyListResponse)
async def list_anomalies(
    status: Optional[str] = Query(default=None),
    process_id: Optional[str] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    rows = await get_anomalies(session, status=status, process_id=process_id, assigned_to=assigned_to, limit=limit)
    anomalies = [_orm_to_schema(r) for r in rows]

    total_exposure = sum(
        (a.as_score or 0) * 10000
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
    assigned_to: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    rows = await get_anomalies(session, status="pending_approval", assigned_to=assigned_to)
    anomalies = [_orm_to_schema(r) for r in rows]
    return PendingApprovalResponse(pending=anomalies, count=len(anomalies))


@router.post("/bulk-approve", response_model=BulkApproveOut)
async def bulk_approve(
    body: BulkApproveIn,
    session: AsyncSession = Depends(get_session),
):
    approved, skipped = await bulk_approve_anomalies(
        session,
        anomaly_ids=body.anomaly_ids,
        approved_by=body.approved_by,
        notes=body.notes,
    )
    return BulkApproveOut(
        approved=approved,
        skipped=skipped,
        message=f"Approved {approved} anomalies, skipped {skipped}.",
    )


@router.post("/bulk-reject", response_model=BulkRejectOut)
async def bulk_reject(
    body: BulkRejectIn,
    session: AsyncSession = Depends(get_session),
):
    rejected, skipped = await bulk_reject_anomalies(
        session,
        anomaly_ids=body.anomaly_ids,
        rejected_by=body.rejected_by,
        reason=body.reason,
    )
    return BulkRejectOut(
        rejected=rejected,
        skipped=skipped,
        message=f"Rejected {rejected} anomalies, skipped {skipped}.",
    )


@router.post("/{anomaly_id}/approve", response_model=ApproveAnomalyOut)
async def approve_anomaly_endpoint(
    anomaly_id: str,
    body: ApproveAnomalyIn,
    session: AsyncSession = Depends(get_session),
):
    row = await get_anomaly_by_id(session, anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")
    if row.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Status is '{row.status}', not pending_approval")

    from agents.agent_08_workflow_executor import WorkflowExecutorAgent
    from core.bus import bus
    executor = WorkflowExecutorAgent.__new__(WorkflowExecutorAgent)
    executor._bus = bus

    await executor.execute_approved(
        anomaly_id=anomaly_id,
        approved_by=body.approved_by,
        notes=body.notes,
    )

    updated = await get_anomaly_by_id(session, anomaly_id)
    return ApproveAnomalyOut(
        message=f"Anomaly {anomaly_id} approved and execution triggered.",
        anomaly=_orm_to_schema(updated),
    )


@router.post("/{anomaly_id}/reject", response_model=RejectAnomalyOut)
async def reject_anomaly_endpoint(
    anomaly_id: str,
    body: RejectAnomalyIn,
    session: AsyncSession = Depends(get_session),
):
    row = await get_anomaly_by_id(session, anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")
    if row.status != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Status is '{row.status}', not pending_approval")

    updated = await reject_anomaly(session, anomaly_id, rejected_by=body.rejected_by, reason=body.reason)
    return RejectAnomalyOut(
        message=f"Anomaly {anomaly_id} rejected.",
        anomaly=_orm_to_schema(updated),
    )


@router.patch("/{anomaly_id}/assign", response_model=AssignAnomalyOut)
async def assign_anomaly_endpoint(
    anomaly_id: str,
    body: AssignAnomalyIn,
    session: AsyncSession = Depends(get_session),
):
    row = await get_anomaly_by_id(session, anomaly_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Anomaly {anomaly_id} not found")

    updated = await assign_anomaly(session, anomaly_id, assigned_to=body.assigned_to)
    return AssignAnomalyOut(
        message=f"Anomaly {anomaly_id} assigned to {body.assigned_to}.",
        anomaly=_orm_to_schema(updated),
    )
