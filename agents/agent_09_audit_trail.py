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
from core.db import get_session_factory, insert_audit_log
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
        # Subscribe to every topic in the pipeline
        for topic in ALL_TOPICS:
            bus.subscribe(topic, self.handle)

    async def handle(self, event: Event) -> None:
        """Write one audit log entry for any incoming event."""
        try:
            payload_summary = self._extract_summary(event.payload)

            factory = get_session_factory()
            async with factory() as session:
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

            logger.debug(
                "agent09.logged",
                topic=event.topic,
                event_id=event.event_id,
                anomaly_id=event.payload.get("anomaly_id"),
            )

        except Exception as exc:
            # Audit trail errors must never crash the pipeline
            logger.error(
                "agent09.log_failed",
                event_id=event.event_id,
                topic=event.topic,
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
