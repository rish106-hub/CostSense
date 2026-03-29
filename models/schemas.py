"""
Pydantic schemas for API request/response and inter-agent payload shapes.
These are separate from ORM models — they define the public contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Spend record schemas
# ---------------------------------------------------------------------------


class SpendRecordIn(BaseModel):
    """Input schema for POST /ingest/record and POST /ingest/batch."""

    vendor: str
    amount: float = Field(gt=0)
    currency: str = Field(default="INR", max_length=3)
    department: str
    category: str
    transaction_date: str  # ISO date string: YYYY-MM-DD
    source: str = Field(default="manual")
    invoice_number: Optional[str] = None
    description: Optional[str] = None


class SpendRecordOut(SpendRecordIn):
    """Output schema including DB-assigned fields."""

    record_id: str
    content_hash: str
    normalized_at: datetime


# ---------------------------------------------------------------------------
# Anomaly schemas
# ---------------------------------------------------------------------------


class AnomalyOut(BaseModel):
    """Full anomaly record returned by GET /anomalies."""

    anomaly_id: str
    record_id: Optional[str]
    process_id: str
    anomaly_type: str
    isolation_score: Optional[float]
    rule_flags: list[str]
    root_cause: Optional[str]
    confidence: Optional[float]
    suggested_action: Optional[str]
    model_used: Optional[str]
    as_score: Optional[float]
    aps_score: Optional[float]
    financial_impact: Optional[float]
    frequency_rank: Optional[float]
    recoverability_ease: Optional[float]
    severity_risk: Optional[float]
    complexity: Optional[int]
    approval_needed: bool
    status: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    approval_notes: Optional[str]
    detected_at: datetime
    updated_at: datetime

    # Flattened spend record fields for display convenience
    vendor: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    department: Optional[str] = None
    category: Optional[str] = None
    transaction_date: Optional[str] = None


class AnomalyListResponse(BaseModel):
    count: int
    total_exposure_inr: float
    total_recovered_inr: float
    anomalies: list[AnomalyOut]


class PendingApprovalResponse(BaseModel):
    pending: list[AnomalyOut]
    count: int


class ApproveAnomalyIn(BaseModel):
    approved_by: str = Field(default="CFO")
    notes: Optional[str] = None


class ApproveAnomalyOut(BaseModel):
    message: str
    anomaly: AnomalyOut


# ---------------------------------------------------------------------------
# Ingest schemas
# ---------------------------------------------------------------------------


class IngestDemoIn(BaseModel):
    n: int = Field(default=86, ge=10, le=500)
    seed: int = Field(default=42)
    include_anomalies: bool = Field(default=True)


class IngestDemoOut(BaseModel):
    message: str
    process_id: str
    records: int


class IngestRecordOut(BaseModel):
    message: str
    process_id: str
    record_id: str


class IngestBatchOut(BaseModel):
    message: str
    process_id: str
    records_submitted: int
    records_skipped: int


# ---------------------------------------------------------------------------
# Summary (CFO view)
# ---------------------------------------------------------------------------


class CFOSummaryOut(BaseModel):
    anomalies_detected: int
    resolved: int
    open: int
    pending_approval: int
    total_exposure_inr: float
    total_recovered_inr: float
    pending_exposure_inr: float = 0.0
    recovery_rate_pct: float
    top_anomaly: Optional[AnomalyOut]
    events_by_topic: dict[str, int]
    agents_active: int
    anomaly_breakdown: dict[str, int] = {}
    status_distribution: dict[str, int] = {}
    agent_stats: list[dict] = []
    source_stats: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    log_id: int
    event_id: str
    topic: str
    source_agent: str
    process_id: Optional[str]
    anomaly_id: Optional[str]
    record_id: Optional[str]
    payload_summary: dict[str, Any]
    logged_at: datetime


class AuditLogResponse(BaseModel):
    count: int
    log: list[AuditLogEntry]


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------


class BusEventOut(BaseModel):
    event_id: str
    topic: str
    source_agent: str
    process_id: str
    payload: dict[str, Any]
    timestamp: datetime


class BusEventsResponse(BaseModel):
    count: int
    events: list[BusEventOut]


# ---------------------------------------------------------------------------
# Process logs
# ---------------------------------------------------------------------------


class ProcessLogEntry(BaseModel):
    log_id: int
    process_id: str
    agent_name: str
    event_id: Optional[str]
    topic_in: Optional[str]
    topic_out: Optional[str]
    record_id: Optional[str]
    anomaly_id: Optional[str]
    input_payload: dict[str, Any]
    output_payload: Optional[dict[str, Any]]
    status: str
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]


class ProcessLogResponse(BaseModel):
    count: int
    logs: list[ProcessLogEntry]


class ProcessSummaryEntry(BaseModel):
    process_id: str
    started_at: datetime
    record_count: int
    anomaly_count: int
    agent_count: int
    has_errors: bool


class ProcessListResponse(BaseModel):
    count: int
    processes: list[ProcessSummaryEntry]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: str
    version: str
    environment: str
    events_processed: int
    topics: dict[str, int]
    agents_registered: int


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------


class SyntheticDataResponse(BaseModel):
    count: int
    seed: int
    include_anomalies: bool
    records: list[dict[str, Any]]
