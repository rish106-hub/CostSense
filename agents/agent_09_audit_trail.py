"""
Agent 9 — Audit Trail

Passive listener on ALL 8 event bus topics.
Writes an append-only record of every event that flows through the system.
No downstream publishing — this is the terminal forensic observer.

Every row is an INSERT. No UPDATE. No DELETE.
This table is the immutable audit record for enterprise compliance.

Subscribes to: ALL 8 topics
Publishes to:  (none)
Uses LLM:      No
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_audit_log, insert_process_log
from models.events import ALL_TOPICS, Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_09_audit_trail"

# Fields to include in the payload_summary (keep it concise)
SUMMARY_FIELDS = [
    "anomaly_id", "record_id", "vendor", "amount", "currency",
    "anomaly_type", "status", "aps_score", "as_score",
    "confidence", "approval_needed", "complexity",
]


class AuditTrailAgent:
    """
    Subscribes to all topics and writes append-only audit records to PostgreSQL.
    Runs as a passive observer — never modifies or re-routes events.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._event_count = 0
        # Subscribe to every topic in the pipeline
        for topic in ALL_TOPICS:
            bus.subscribe(topic, self.handle)
        logger.info("agent09.initialized", topics=ALL_TOPICS)

    async def handle(self, event: Event) -> None:
        """Write one audit log entry for any incoming event."""
        self._event_count += 1
        started_at = datetime.now(timezone.utc)
        try:
            if not event or not event.event_id:
                logger.warning("agent09.invalid_event", event=event)
                return

            payload_summary = self._extract_summary(event.payload)
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            # Use separate sessions - don't try to reuse one for multiple operations
            factory = get_session_factory()
            
            # Insert to audit log
            async with factory() as session:
                try:
                    await insert_audit_log(session, {
                        "event_id": event.event_id,
                        "topic": event.topic,
                        "source_agent": event.source_agent,
                        "process_id": event.process_id,
                        "anomaly_id": event.payload.get("anomaly_id"),
                        "record_id": event.payload.get("record_id"),
                        "payload_summary": payload_summary,
                        "logged_at": datetime.now(timezone.utc),
                    })
                    logger.debug(f"agent09.audit_logged", event_id=event.event_id, count=self._event_count)
                except Exception as db_exc:
                    logger.error(
                        "agent09.audit_insert_failed",
                        event_id=event.event_id,
                        topic=event.topic,
                        error=str(db_exc),
                    )
                    # Don't re-raise - audit trail should not crash the pipeline
            
            # Insert to process logs (separate session)
            async with factory() as session:
                try:
                    await insert_process_log(session, {
                        "process_id": event.process_id,
                        "agent_name": AGENT_NAME,
                        "event_id": event.event_id,
                        "topic_in": event.topic,
                        "topic_out": None,
                        "record_id": event.payload.get("record_id"),
                        "anomaly_id": event.payload.get("anomaly_id"),
                        "input_payload": event.payload,
                        "output_payload": None,
                        "status": "success",
                        "error_message": None,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "duration_ms": duration_ms,
                    })
                    logger.debug(f"agent09.process_logged", event_id=event.event_id, count=self._event_count)
                except Exception as db_exc:
                    logger.error(
                        "agent09.process_log_insert_failed",
                        event_id=event.event_id,
                        topic=event.topic,
                        error=str(db_exc),
                    )
                    # Don't re-raise - audit trail should not crash the pipeline

            logger.debug(
                "agent09.handled",
                topic=event.topic,
                event_id=event.event_id,
                total_count=self._event_count,
            )

        except Exception as exc:
            # Audit trail errors must never crash the pipeline
            logger.error(
                "agent09.handle_failed",
                event_id=event.event_id if event else "unknown",
                topic=event.topic if event else "unknown",
                error=str(exc),
            )

    @staticmethod
    def _extract_summary(payload: dict) -> dict:
        """Extract the most useful fields for the audit summary."""
        summary = {}
        for field in SUMMARY_FIELDS:
            value = payload.get(field)
            if value is not None:
                summary[field] = value
        return summary
