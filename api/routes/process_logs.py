"""
GET /logs              — process logs with optional filters
GET /logs/processes    — list of distinct process runs
GET /logs/{process_id} — full trace for a specific pipeline run
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_distinct_processes, get_process_logs, get_session
from models.schemas import (
    ProcessListResponse,
    ProcessLogEntry,
    ProcessLogResponse,
    ProcessSummaryEntry,
)

router = APIRouter(prefix="/logs", tags=["logs"])


def _orm_to_log_entry(row) -> ProcessLogEntry:
    return ProcessLogEntry(
        log_id=row.log_id,
        process_id=str(row.process_id),
        agent_name=row.agent_name,
        event_id=str(row.event_id) if row.event_id else None,
        topic_in=row.topic_in,
        topic_out=row.topic_out,
        record_id=str(row.record_id) if row.record_id else None,
        anomaly_id=str(row.anomaly_id) if row.anomaly_id else None,
        input_payload=row.input_payload or {},
        output_payload=row.output_payload,
        status=row.status,
        error_message=row.error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
    )


@router.get("/processes", response_model=ProcessListResponse)
async def list_processes(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """List recent pipeline runs with summary stats."""
    processes = await get_distinct_processes(session, limit=limit)
    entries = [
        ProcessSummaryEntry(
            process_id=str(p["process_id"]),
            started_at=p["started_at"],
            record_count=p["record_count"],
            anomaly_count=p["anomaly_count"],
            agent_count=p["agent_count"],
            has_errors=p["has_errors"],
        )
        for p in processes
    ]
    return ProcessListResponse(count=len(entries), processes=entries)


@router.get("/{process_id}", response_model=ProcessLogResponse)
async def get_process_trace(
    process_id: str,
    agent_name: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Return the full agent trace for a specific pipeline run."""
    rows = await get_process_logs(
        session, process_id=process_id, agent_name=agent_name, limit=1000
    )
    return ProcessLogResponse(
        count=len(rows),
        logs=[_orm_to_log_entry(r) for r in rows],
    )


@router.get("", response_model=ProcessLogResponse)
async def get_logs(
    process_id: Optional[str] = Query(default=None),
    agent_name: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
):
    """Return process logs with optional filters."""
    import structlog
    logger = structlog.get_logger(__name__)
    
    logger.info("get_logs.request", process_id=process_id, agent_name=agent_name, limit=limit)
    
    rows = await get_process_logs(
        session, process_id=process_id, agent_name=agent_name, limit=limit
    )
    
    logger.info("get_logs.result", count=len(rows), process_id=process_id)
    
    return ProcessLogResponse(
        count=len(rows),
        logs=[_orm_to_log_entry(r) for r in rows],
    )
