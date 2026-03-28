"""
Agent 7 — Action Dispatcher

Subscribes to anomaly.ready. Routes each fully merged anomaly to either:
  - action.approval_needed  (APS >= 4.0 AND complexity >= 2)
  - action.auto_execute     (everything else)

Pure routing logic — no LLM calls, no DB writes.

Subscribes to: anomaly.ready
Publishes to:  action.approval_needed OR action.auto_execute
Uses LLM:      No
Latency:       < 1ms
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_process_log
from core.scoring import requires_approval
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_07_action_dispatcher"
TOPIC_IN = "anomaly.ready"
TOPIC_OUT_APPROVAL = "action.approval_needed"
TOPIC_OUT_AUTO = "action.auto_execute"


class ActionDispatcherAgent:
    """
    Reads the APS and complexity from each ready anomaly and routes to the
    appropriate action topic.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(TOPIC_IN, self.handle)

    async def handle(self, event: Event) -> None:
        """Route one anomaly.ready event."""
        started_at = datetime.now(timezone.utc)
        anomaly = event.payload

        try:
            aps_score = float(anomaly.get("aps_score") or 0.0)
            complexity = int(anomaly.get("complexity") or 1)
            approval_needed = anomaly.get("approval_needed", False)

            # Double-check routing using the scoring module
            if approval_needed or requires_approval(aps_score, complexity):
                topic_out = TOPIC_OUT_APPROVAL
                anomaly["status"] = "pending_approval"
            else:
                topic_out = TOPIC_OUT_AUTO
                anomaly["status"] = "queued_for_execution"

            published_event = await self._bus.publish(
                topic=topic_out,
                source_agent=AGENT_NAME,
                process_id=event.process_id,
                payload=anomaly,
            )

            logger.info(
                "agent07.dispatched",
                anomaly_id=anomaly.get("anomaly_id"),
                route=topic_out,
                aps_score=aps_score,
                complexity=complexity,
            )

            await self._log(event, published_event, topic_out, "success", None, started_at, anomaly)

        except Exception as exc:
            logger.error("agent07.error", event_id=event.event_id, error=str(exc))
            await self._log(event, None, None, "error", str(exc), started_at)

    async def _log(
        self,
        event: Event,
        published_event,
        topic_out: Optional[str],
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
                    "topic_out": topic_out,
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
            logger.warning("agent07.log_failed", error=str(log_exc))
