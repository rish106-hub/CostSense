"""GET /audit — append-only audit log entries."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_audit_log, get_session
from models.schemas import AuditLogEntry, AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogResponse)
async def get_audit_trail(
    limit: int = Query(default=50, ge=1, le=500),
    process_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Return audit log entries, newest first."""
    rows = await get_audit_log(session, limit=limit, process_id=process_id)
    entries = [
        AuditLogEntry(
            log_id=row.log_id,
            event_id=str(row.event_id),
            topic=row.topic,
            source_agent=row.source_agent,
            process_id=str(row.process_id) if row.process_id else None,
            anomaly_id=str(row.anomaly_id) if row.anomaly_id else None,
            record_id=str(row.record_id) if row.record_id else None,
            payload_summary=row.payload_summary or {},
            logged_at=row.logged_at,
        )
        for row in rows
    ]
    return AuditLogResponse(count=len(entries), log=entries)
