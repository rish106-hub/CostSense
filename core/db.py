"""
PostgreSQL database layer using SQLAlchemy async engine.

Provides:
  - Async engine + session factory
  - init_db()  — creates all tables (including pgvector extension)
  - CRUD helpers used by agents and API routes
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.orm import (
    Anomaly,
    AnomalyEmbedding,
    AuditLog,
    Base,
    ProcessLog,
    SpendRecord,
    Watermark,
)

logger = structlog.get_logger(__name__)

# Module-level engine and session factory — initialized once by init_db()
_engine = None
_session_factory: Optional[async_sessionmaker] = None


async def init_db(database_url: str) -> None:
    """
    Create the async engine, enable the pgvector extension, and create all tables.
    Call this once at application startup.
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        # Enable pgvector extension — no-op if already enabled
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create all tables defined in ORM
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database.initialized", url=database_url.split("@")[-1])


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session per request."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker:
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


# ---------------------------------------------------------------------------
# SpendRecord helpers
# ---------------------------------------------------------------------------


async def insert_spend_record(session: AsyncSession, record: dict) -> SpendRecord:
    """Insert a normalized spend record. Silently skips duplicates (by content_hash)."""
    row = SpendRecord(**record)
    session.add(row)
    try:
        await session.commit()
        await session.refresh(row)
    except Exception:
        await session.rollback()
        # Return existing row on duplicate
        result = await session.execute(
            select(SpendRecord).where(SpendRecord.content_hash == record["content_hash"])
        )
        row = result.scalar_one()
    return row


async def get_spend_records_by_vendor(
    session: AsyncSession, vendor: str, limit: int = 50
) -> list[SpendRecord]:
    result = await session.execute(
        select(SpendRecord)
        .where(SpendRecord.vendor == vendor)
        .order_by(SpendRecord.normalized_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Anomaly helpers
# ---------------------------------------------------------------------------


async def upsert_anomaly(session: AsyncSession, data: dict) -> Anomaly:
    """
    Insert or update an anomaly record.
    If anomaly_id already exists, merges the new fields (agents enrich progressively).
    """
    anomaly_id = data.get("anomaly_id")
    existing = None

    if anomaly_id:
        result = await session.execute(
            select(Anomaly).where(Anomaly.anomaly_id == anomaly_id)
        )
        existing = result.scalar_one_or_none()

    if existing:
        for key, value in data.items():
            if value is not None and hasattr(existing, key):
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(existing)
        return existing
    else:
        row = Anomaly(**{k: v for k, v in data.items() if hasattr(Anomaly, k)})
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def get_anomalies(
    session: AsyncSession,
    status: Optional[str] = None,
    process_id: Optional[str] = None,
    limit: int = 200,
) -> list[Anomaly]:
    query = select(Anomaly)
    if status:
        query = query.where(Anomaly.status == status)
    if process_id:
        query = query.where(Anomaly.process_id == process_id)
    query = query.order_by(Anomaly.aps_score.desc().nullslast()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_anomaly_by_id(session: AsyncSession, anomaly_id: str) -> Optional[Anomaly]:
    result = await session.execute(
        select(Anomaly).where(Anomaly.anomaly_id == anomaly_id)
    )
    return result.scalar_one_or_none()


async def approve_anomaly(
    session: AsyncSession,
    anomaly_id: str,
    approved_by: str,
    notes: Optional[str] = None,
) -> Optional[Anomaly]:
    """Mark anomaly as approved and ready for execution."""
    now = datetime.now(timezone.utc)
    await session.execute(
        update(Anomaly)
        .where(Anomaly.anomaly_id == anomaly_id)
        .values(
            status="approved",
            approved_by=approved_by,
            approved_at=now,
            approval_notes=notes,
            updated_at=now,
        )
    )
    await session.commit()
    return await get_anomaly_by_id(session, anomaly_id)


async def get_anomaly_totals(session: AsyncSession) -> dict:
    result = await session.execute(
        select(
            func.count(Anomaly.anomaly_id).label("total"),
            func.sum(Anomaly.amount if hasattr(Anomaly, "amount") else 0).label("exposure"),
        )
    )
    # Compute totals from all anomalies
    all_anomalies = await get_anomalies(session, limit=10000)
    total = len(all_anomalies)
    resolved = sum(1 for a in all_anomalies if a.status in ("auto_executed", "approved"))
    pending = sum(1 for a in all_anomalies if a.status == "pending_approval")
    open_count = total - resolved - pending
    return {"total": total, "resolved": resolved, "pending": pending, "open": open_count}


# ---------------------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------------------


async def insert_audit_log(session: AsyncSession, entry: dict) -> AuditLog:
    """Append-only insert — never updates existing rows."""
    row = AuditLog(**entry)
    session.add(row)
    await session.commit()
    return row


async def get_audit_log(
    session: AsyncSession, limit: int = 50, process_id: Optional[str] = None
) -> list[AuditLog]:
    query = select(AuditLog)
    if process_id:
        query = query.where(AuditLog.process_id == process_id)
    query = query.order_by(AuditLog.logged_at.desc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Watermark helpers
# ---------------------------------------------------------------------------


async def get_watermark(session: AsyncSession, source_id: str) -> Optional[Watermark]:
    result = await session.execute(
        select(Watermark).where(Watermark.source_id == source_id)
    )
    return result.scalar_one_or_none()


async def update_watermark(
    session: AsyncSession, source_id: str, cursor: str, records_ingested: int = 0
) -> Watermark:
    existing = await get_watermark(session, source_id)
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_cursor = cursor
        existing.last_synced_at = now
        existing.records_ingested += records_ingested
        await session.commit()
        return existing
    else:
        row = Watermark(
            source_id=source_id,
            last_cursor=cursor,
            last_synced_at=now,
            records_ingested=records_ingested,
        )
        session.add(row)
        await session.commit()
        return row


# ---------------------------------------------------------------------------
# Process log helpers
# ---------------------------------------------------------------------------


async def insert_process_log(session: AsyncSession, entry: dict) -> ProcessLog:
    row = ProcessLog(**{k: v for k, v in entry.items() if hasattr(ProcessLog, k)})
    session.add(row)
    await session.commit()
    return row


async def get_process_logs(
    session: AsyncSession,
    process_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    limit: int = 200,
) -> list[ProcessLog]:
    query = select(ProcessLog)
    if process_id:
        query = query.where(ProcessLog.process_id == process_id)
    if agent_name:
        query = query.where(ProcessLog.agent_name == agent_name)
    query = query.order_by(ProcessLog.started_at.asc()).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_distinct_processes(session: AsyncSession, limit: int = 50) -> list[dict]:
    """Return a summary of recent process runs."""
    result = await session.execute(
        select(
            ProcessLog.process_id,
            func.min(ProcessLog.started_at).label("started_at"),
            func.count(ProcessLog.log_id).label("agent_count"),
        )
        .group_by(ProcessLog.process_id)
        .order_by(func.min(ProcessLog.started_at).desc())
        .limit(limit)
    )
    rows = result.all()
    processes = []
    for row in rows:
        # Count anomalies for this process
        anomaly_result = await session.execute(
            select(func.count(Anomaly.anomaly_id)).where(
                Anomaly.process_id == row.process_id
            )
        )
        anomaly_count = anomaly_result.scalar() or 0

        # Check for errors
        error_result = await session.execute(
            select(func.count(ProcessLog.log_id)).where(
                ProcessLog.process_id == row.process_id,
                ProcessLog.status == "error",
            )
        )
        has_errors = (error_result.scalar() or 0) > 0

        processes.append(
            {
                "process_id": row.process_id,
                "started_at": row.started_at,
                "record_count": row.agent_count,
                "anomaly_count": anomaly_count,
                "agent_count": row.agent_count,
                "has_errors": has_errors,
            }
        )
    return processes
