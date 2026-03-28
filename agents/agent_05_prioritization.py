"""
Agent 5 — Prioritization (Scoring Engine)

Subscribes to anomaly.detected — runs CONCURRENTLY with Agent 4.
Computes AS (Anomaly Score) and APS (Action Priority Score) deterministically
using the scoring engine in core/scoring.py.

No LLM calls. Latency < 1ms per record.

Subscribes to: anomaly.detected
Publishes to:  anomaly.scored
Uses LLM:      No
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_process_log
from core.scoring import score_anomaly
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_05_prioritization"
TOPIC_IN = "anomaly.detected"
TOPIC_OUT = "anomaly.scored"

# Default monthly operational expenditure (INR) — used to normalize FI scores
DEFAULT_MONTHLY_OPEX_INR = 5_000_000  # Rs 50L


class PrioritizationAgent:
    """
    Scores each anomaly using the AS/APS framework.
    Tracks per-vendor occurrence counts for the Frequency (FR) component.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        # Per-vendor occurrence counter for FR scoring
        self._vendor_occurrences: dict[str, int] = defaultdict(int)
        bus.subscribe(TOPIC_IN, self.handle)

    async def handle(self, event: Event) -> None:
        """Process one anomaly.detected event."""
        started_at = datetime.now(timezone.utc)
        anomaly = event.payload

        try:
            vendor = anomaly.get("vendor", "unknown")
            amount = float(anomaly.get("amount", 0))
            anomaly_type = anomaly.get("anomaly_type", "unknown")
            confidence = float(anomaly.get("confidence", 0.70))

            # Update vendor occurrence count
            self._vendor_occurrences[vendor] += 1
            occurrence_count = self._vendor_occurrences[vendor]

            # Affected records: duplicate_payment affects 2, others affect 1
            affected_records = 2 if anomaly_type == "duplicate_payment" else 1

            # Run the full scoring pipeline
            scores = score_anomaly(
                amount=amount,
                anomaly_type=anomaly_type,
                confidence=confidence,
                occurrence_count=occurrence_count,
                affected_record_count=affected_records,
                monthly_opex=DEFAULT_MONTHLY_OPEX_INR,
            )

            # Build scored payload = all anomaly fields + scores
            scored_payload = dict(anomaly)
            scored_payload.update(scores)

            published_event = await self._bus.publish(
                topic=TOPIC_OUT,
                source_agent=AGENT_NAME,
                process_id=event.process_id,
                payload=scored_payload,
            )

            logger.info(
                "agent05.scored",
                anomaly_id=anomaly.get("anomaly_id"),
                as_score=scores["as_score"],
                aps_score=scores["aps_score"],
                complexity=scores["complexity"],
                approval_needed=scores["approval_needed"],
            )

            await self._log(event, published_event, "success", None, started_at, scored_payload)

        except Exception as exc:
            logger.error("agent05.error", event_id=event.event_id, error=str(exc))
            await self._log(event, None, "error", str(exc), started_at)

    async def _log(
        self,
        event: Event,
        published_event,
        status: str,
        error_message: Optional[str],
        started_at: datetime,
        output_payload: Optional[dict] = None,
    ) -> None:
        try:
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            factory = get_session_factory()
            async with factory() as session:
                await insert_process_log(session, {
                    "process_id": event.process_id,
                    "agent_name": AGENT_NAME,
                    "event_id": event.event_id,
                    "topic_in": TOPIC_IN,
                    "topic_out": TOPIC_OUT if status == "success" else None,
                    "record_id": event.payload.get("record_id"),
                    "anomaly_id": event.payload.get("anomaly_id"),
                    "input_payload": event.payload,
                    "output_payload": output_payload,
                    "status": status,
                    "error_message": error_message,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                })
        except Exception as log_exc:
            logger.warning("agent05.log_failed", error=str(log_exc))
