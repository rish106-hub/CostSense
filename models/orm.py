"""
SQLAlchemy ORM table definitions for CostSense AI.

Tables:
  - spend_records       : Normalized spend transactions
  - anomalies           : Detected + enriched + scored anomalies
  - audit_log           : Append-only event ledger (Agent 9)
  - watermarks          : Per-source sync state
  - anomaly_embeddings  : pgvector embeddings for similarity search
  - process_logs        : Per-agent input/output trace for each pipeline run
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class SpendRecord(Base):
    """Normalized spend transaction — one row per unique transaction."""

    __tablename__ = "spend_records"

    record_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    vendor = Column(String(255), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    department = Column(String(100), nullable=False)
    category = Column(String(100), nullable=False)
    transaction_date = Column(String(20), nullable=False)  # ISO date string
    source = Column(String(100), nullable=False)  # zoho_books/aws/gcp/tally/sap/manual/synthetic
    invoice_number = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=False)  # SHA256 for dedup
    normalized_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_spend_content_hash"),
        CheckConstraint("amount > 0", name="chk_spend_amount_positive"),
        Index("idx_spend_vendor", "vendor"),
        Index("idx_spend_date", "transaction_date"),
        Index("idx_spend_source", "source"),
    )


class Anomaly(Base):
    """
    Full lifecycle record for a detected anomaly.
    Populated progressively by Agents 3 → 4 → 5 → 6.
    """

    __tablename__ = "anomalies"

    anomaly_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    record_id = Column(UUID(as_uuid=False), nullable=True)  # FK in logic, not enforced for perf
    process_id = Column(UUID(as_uuid=False), nullable=False)

    # Detection fields (Agent 3)
    anomaly_type = Column(String(100), nullable=False)
    isolation_score = Column(Float, nullable=True)
    rule_flags = Column(JSONB, nullable=False, default=list)

    # Enrichment fields (Agent 4 — LLM)
    root_cause = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    suggested_action = Column(Text, nullable=True)
    model_used = Column(String(100), nullable=True)

    # Scoring fields (Agent 5)
    as_score = Column(Float, nullable=True)
    aps_score = Column(Float, nullable=True)
    financial_impact = Column(Float, nullable=True)
    frequency_rank = Column(Float, nullable=True)
    recoverability_ease = Column(Float, nullable=True)
    severity_risk = Column(Float, nullable=True)
    complexity = Column(Integer, nullable=True)

    # Routing + status (Agent 7 / 8)
    approval_needed = Column(Boolean, nullable=False, default=False)
    status = Column(String(50), nullable=False, default="detected")
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_notes = Column(Text, nullable=True)

    detected_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    __table_args__ = (
        CheckConstraint(
            "status IN ('detected','pending_approval','approved','auto_executed','rejected')",
            name="chk_anomaly_status",
        ),
        Index("idx_anomaly_status", "status"),
        Index("idx_anomaly_aps", "aps_score"),
        Index("idx_anomaly_process", "process_id"),
        Index("idx_anomaly_record", "record_id"),
    )


class AuditLog(Base):
    """
    Append-only ledger written by Agent 9.
    No UPDATE or DELETE should ever touch this table.
    """

    __tablename__ = "audit_log"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(UUID(as_uuid=False), nullable=False)
    topic = Column(String(100), nullable=False)
    source_agent = Column(String(100), nullable=False)
    process_id = Column(UUID(as_uuid=False), nullable=True)
    anomaly_id = Column(UUID(as_uuid=False), nullable=True)
    record_id = Column(UUID(as_uuid=False), nullable=True)
    payload_summary = Column(JSONB, nullable=False, default=dict)
    logged_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (
        UniqueConstraint("event_id", name="uq_audit_event_id"),
        Index("idx_audit_topic", "topic"),
        Index("idx_audit_logged_at", "logged_at"),
        Index("idx_audit_anomaly_id", "anomaly_id"),
        Index("idx_audit_process_id", "process_id"),
    )


class Watermark(Base):
    """Tracks the last-synced position per external data source."""

    __tablename__ = "watermarks"

    source_id = Column(String(100), primary_key=True)
    last_cursor = Column(Text, nullable=False, default="")
    last_synced_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    records_ingested = Column(Integer, nullable=False, default=0)


class AnomalyEmbedding(Base):
    """
    pgvector table for semantic similarity search over anomalies.
    Used by Agent 4 to retrieve similar past anomalies as context.
    """

    __tablename__ = "anomaly_embeddings"

    embedding_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    anomaly_id = Column(UUID(as_uuid=False), nullable=False)
    embedding = Column(Vector(1536), nullable=True)
    source_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    __table_args__ = (Index("idx_embedding_anomaly_id", "anomaly_id"),)


class ProcessLog(Base):
    """
    Per-agent input/output trace. All agents share the same process_id
    for a single ingestion batch, enabling full pipeline trace reconstruction.
    """

    __tablename__ = "process_logs"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    process_id = Column(UUID(as_uuid=False), nullable=False)
    agent_name = Column(String(100), nullable=False)
    event_id = Column(UUID(as_uuid=False), nullable=True)
    topic_in = Column(String(100), nullable=True)   # null for Agent 1 (no upstream)
    topic_out = Column(String(100), nullable=True)  # null for Agent 9 (no downstream)
    record_id = Column(UUID(as_uuid=False), nullable=True)
    anomaly_id = Column(UUID(as_uuid=False), nullable=True)
    input_payload = Column(JSONB, nullable=False, default=dict)
    output_payload = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default="success")  # success/error/skipped
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'error', 'skipped')",
            name="chk_process_log_status",
        ),
        Index("idx_plog_process_id", "process_id"),
        Index("idx_plog_agent_name", "agent_name"),
        Index("idx_plog_started_at", "started_at"),
        Index("idx_plog_process_agent", "process_id", "agent_name"),
        Index("idx_plog_status", "status"),
    )
