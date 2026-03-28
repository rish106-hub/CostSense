"""
Agent 6 — Merge

Subscribes to BOTH anomaly.enriched (from Agent 4) AND anomaly.scored (from Agent 5).
Waits for both halves of the same anomaly_id to arrive, merges them into a complete
record, persists to the anomalies table, generates an embedding, then publishes anomaly.ready.

Key design:
  - Two in-memory buffers (enriched_buffer, scored_buffer) keyed by anomaly_id
  - Protected by asyncio.Lock to prevent race conditions
  - 30-second TTL cleanup for anomalies where one half never arrives
  - Net latency = max(LLM time, scoring time) ≈ 2–4 seconds, not sum

Subscribes to: anomaly.enriched AND anomaly.scored
Publishes to:  anomaly.ready
Uses LLM:      No
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_process_log, upsert_anomaly
from core.vector_store import store_anomaly_embedding
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_06_merge"
TOPIC_IN_ENRICHED = "anomaly.enriched"
TOPIC_IN_SCORED = "anomaly.scored"
TOPIC_OUT = "anomaly.ready"

MERGE_TIMEOUT_SECONDS = 30  # Publish with partial data after this timeout


class MergeAgent:
    """
    Waits for both Agent 4 and Agent 5 results for the same anomaly,
    merges them into a complete record, and persists + publishes downstream.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._enriched_buffer: dict[str, dict] = {}
        self._scored_buffer: dict[str, dict] = {}
        self._timestamps: dict[str, datetime] = {}  # When first half arrived
        self._lock = asyncio.Lock()

        bus.subscribe(TOPIC_IN_ENRICHED, self.handle_enriched)
        bus.subscribe(TOPIC_IN_SCORED, self.handle_scored)

        # Start TTL cleanup task
        asyncio.create_task(self._cleanup_stale_entries(), name="merge-ttl-cleanup")

    async def handle_enriched(self, event: Event) -> None:
        """Called when Agent 4 publishes an enriched anomaly."""
        anomaly_id = event.payload.get("anomaly_id")
        if not anomaly_id:
            return
        async with self._lock:
            self._enriched_buffer[anomaly_id] = event.payload
            if anomaly_id not in self._timestamps:
                self._timestamps[anomaly_id] = datetime.now(timezone.utc)
            await self._try_merge(anomaly_id, event.process_id)

    async def handle_scored(self, event: Event) -> None:
        """Called when Agent 5 publishes a scored anomaly."""
        anomaly_id = event.payload.get("anomaly_id")
        if not anomaly_id:
            return
        async with self._lock:
            self._scored_buffer[anomaly_id] = event.payload
            if anomaly_id not in self._timestamps:
                self._timestamps[anomaly_id] = datetime.now(timezone.utc)
            await self._try_merge(anomaly_id, event.process_id)

    async def _try_merge(self, anomaly_id: str, process_id: str) -> None:
        """
        Attempt to merge if both halves are present.
        Called while holding self._lock.
        """
        enriched = self._enriched_buffer.get(anomaly_id)
        scored = self._scored_buffer.get(anomaly_id)

        if enriched is None or scored is None:
            return  # Wait for the other half

        started_at = datetime.now(timezone.utc)

        # Merge: scored fields + LLM fields from enriched
        merged = dict(scored)
        merged.update({
            "root_cause": enriched.get("root_cause"),
            "confidence": enriched.get("confidence", scored.get("confidence")),
            "suggested_action": enriched.get("suggested_action"),
            "model_used": enriched.get("model_used"),
        })
        merged["status"] = "detected"
        merged["process_id"] = process_id

        # Clean up buffers
        del self._enriched_buffer[anomaly_id]
        del self._scored_buffer[anomaly_id]
        self._timestamps.pop(anomaly_id, None)

        # Persist to DB
        try:
            factory = get_session_factory()
            async with factory() as session:
                await upsert_anomaly(session, merged)

                # Generate and store embedding for similarity search
                await store_anomaly_embedding(session, anomaly_id, merged)

        except Exception as exc:
            logger.error("agent06.persist_failed", anomaly_id=anomaly_id, error=str(exc))

        # Publish fully merged anomaly downstream
        try:
            published_event = await self._bus.publish(
                topic=TOPIC_OUT,
                source_agent=AGENT_NAME,
                process_id=process_id,
                payload=merged,
            )

            logger.info(
                "agent06.merged",
                anomaly_id=anomaly_id,
                aps_score=merged.get("aps_score"),
                approval_needed=merged.get("approval_needed"),
            )

            await self._log_process(
                process_id=process_id,
                event_id=published_event.event_id,
                anomaly_id=anomaly_id,
                record_id=merged.get("record_id"),
                input_payload={"enriched": enriched, "scored": scored},
                output_payload=merged,
                status="success",
                started_at=started_at,
            )
        except Exception as exc:
            logger.error("agent06.publish_failed", anomaly_id=anomaly_id, error=str(exc))

    async def _cleanup_stale_entries(self) -> None:
        """Background task: publish partial records for anomalies that time out."""
        while True:
            await asyncio.sleep(MERGE_TIMEOUT_SECONDS)
            try:
                now = datetime.now(timezone.utc)
                stale_ids = [
                    aid
                    for aid, ts in list(self._timestamps.items())
                    if (now - ts).total_seconds() > MERGE_TIMEOUT_SECONDS
                ]
                for anomaly_id in stale_ids:
                    logger.warning(
                        "agent06.partial_merge_timeout", anomaly_id=anomaly_id
                    )
                    async with self._lock:
                        enriched = self._enriched_buffer.pop(anomaly_id, {})
                        scored = self._scored_buffer.pop(anomaly_id, {})
                        self._timestamps.pop(anomaly_id, None)

                    # Publish with whatever data is available
                    partial = dict(scored or enriched)
                    if partial:
                        partial["status"] = "detected"
                        partial["_partial_merge"] = True
                        await self._bus.publish(
                            topic=TOPIC_OUT,
                            source_agent=AGENT_NAME,
                            process_id=partial.get("process_id", "unknown"),
                            payload=partial,
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("agent06.cleanup_error", error=str(exc))

    async def _log_process(
        self,
        process_id: str,
        event_id: str,
        anomaly_id: str,
        record_id: Optional[str],
        input_payload: dict,
        output_payload: dict,
        status: str,
        started_at: datetime,
        error_message: Optional[str] = None,
    ) -> None:
        try:
            completed_at = datetime.now(timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            factory = get_session_factory()
            async with factory() as session:
                await insert_process_log(session, {
                    "process_id": process_id,
                    "agent_name": AGENT_NAME,
                    "event_id": event_id,
                    "topic_in": f"{TOPIC_IN_ENRICHED} + {TOPIC_IN_SCORED}",
                    "topic_out": TOPIC_OUT,
                    "record_id": record_id,
                    "anomaly_id": anomaly_id,
                    "input_payload": input_payload,
                    "output_payload": output_payload,
                    "status": status,
                    "error_message": error_message,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                })
        except Exception as log_exc:
            logger.warning("agent06.log_failed", error=str(log_exc))
