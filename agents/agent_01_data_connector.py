"""
Agent 1 — Data Connector

Validates incoming spend records and publishes them to the raw.spend topic.
Does NOT subscribe to any topic — it is the entry point of the pipeline.

Triggered by:
  - POST /ingest/record  (single record)
  - POST /ingest/demo    (86-record synthetic batch)
  - POST /ingest/batch   (user-uploaded CSV batch)

Publishes to: raw.spend
Uses LLM:     No
Latency:      < 1ms per record
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import insert_process_log, get_session_factory
from models.schemas import SpendRecordIn

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_01_data_connector"
TOPIC_OUT = "raw.spend"


class DataConnectorAgent:
    """
    Validates and publishes raw spend records to the event bus.
    Inter-record delay prevents flooding the downstream queue.
    """

    def __init__(self, bus: EventBus, inter_record_delay_ms: float = 10.0) -> None:
        self._bus = bus
        self._delay = inter_record_delay_ms / 1000.0  # Convert to seconds

    async def ingest_record(
        self,
        raw_record: dict,
        process_id: str,
    ) -> str:
        """
        Validate a single spend record and publish it to raw.spend.
        Returns the event_id of the published event.
        """
        started_at = datetime.now(timezone.utc)

        try:
            # Validate with Pydantic — raises ValidationError on bad data
            validated = SpendRecordIn(**{
                k: v for k, v in raw_record.items()
                if k in SpendRecordIn.model_fields
            })
            payload = validated.model_dump()
            # Pass through internal fields that aren't part of SpendRecordIn
            for field in ("record_id", "content_hash"):
                if field in raw_record:
                    payload[field] = raw_record[field]

            event = await self._bus.publish(
                topic=TOPIC_OUT,
                source_agent=AGENT_NAME,
                process_id=process_id,
                payload=payload,
            )

            await self._log_process(
                process_id=process_id,
                event_id=event.event_id,
                record_id=raw_record.get("record_id"),
                input_payload=raw_record,
                output_payload=payload,
                status="success",
                started_at=started_at,
            )

            logger.debug(
                "agent01.published",
                vendor=payload.get("vendor"),
                amount=payload.get("amount"),
                event_id=event.event_id,
            )
            return event.event_id

        except Exception as exc:
            await self._log_process(
                process_id=process_id,
                event_id=None,
                record_id=raw_record.get("record_id"),
                input_payload=raw_record,
                output_payload=None,
                status="error",
                error_message=str(exc),
                started_at=started_at,
            )
            logger.warning("agent01.validation_failed", error=str(exc), record=raw_record)
            raise

    async def ingest_batch(
        self,
        records: list[dict],
        process_id: str,
    ) -> tuple[int, int]:
        """
        Ingest a list of records with a short delay between each to avoid flooding.
        Returns (published_count, skipped_count).
        """
        published = 0
        skipped = 0

        for record in records:
            try:
                await self.ingest_record(record, process_id)
                published += 1
                if self._delay > 0:
                    await asyncio.sleep(self._delay)
            except Exception:
                skipped += 1

        logger.info(
            "agent01.batch_complete",
            process_id=process_id,
            published=published,
            skipped=skipped,
        )
        return published, skipped

    async def _log_process(
        self,
        process_id: str,
        event_id: Optional[str],
        record_id: Optional[str],
        input_payload: dict,
        output_payload: Optional[dict],
        status: str,
        started_at: datetime,
        error_message: Optional[str] = None,
    ) -> None:
        """Write a process log entry for this agent invocation."""
        try:
            completed_at = datetime.now(timezone.utc)
            duration_ms = int(
                (completed_at - started_at).total_seconds() * 1000
            )
            factory = get_session_factory()
            async with factory() as session:
                await insert_process_log(session, {
                    "process_id": process_id,
                    "agent_name": AGENT_NAME,
                    "event_id": event_id,
                    "topic_in": None,
                    "topic_out": TOPIC_OUT,
                    "record_id": record_id,
                    "anomaly_id": None,
                    "input_payload": input_payload,
                    "output_payload": output_payload,
                    "status": status,
                    "error_message": error_message,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                })
        except Exception as log_exc:
            logger.warning("agent01.log_failed", error=str(log_exc))
