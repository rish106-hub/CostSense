"""
Agent 4 — Root Cause Analysis (LLM)

Subscribes to anomaly.detected. Calls the LangChain fallback chain
(Llama → Mistral → Gemma via OpenRouter) to explain the root cause
and generate an actionable recommendation.

Runs CONCURRENTLY with Agent 5 (Prioritization) — both subscribe to
anomaly.detected independently. Net latency = max(LLM time, scoring time).

Subscribes to: anomaly.detected
Publishes to:  anomaly.enriched
Uses LLM:      Yes (primary: Llama 3.1 8B → fallback: Mistral 7B → Gemma 2 9B)
Latency:       2–4 seconds per anomaly (LLM call)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from core.bus import EventBus
from core.db import get_session_factory, insert_process_log
from core.llm import (
    RootCauseResult,
    build_root_cause_chain,
    get_default_root_cause_result,
    invoke_root_cause,
)
from core.vector_store import find_similar_anomalies
from models.events import Event

logger = structlog.get_logger(__name__)

AGENT_NAME = "agent_04_root_cause"
TOPIC_IN = "anomaly.detected"
TOPIC_OUT = "anomaly.enriched"


class RootCauseAgent:
    """
    Calls the LLM to explain each detected anomaly.
    Uses similar past anomalies from pgvector as context.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._chain = build_root_cause_chain()
        bus.subscribe(TOPIC_IN, self.handle)

    async def handle(self, event: Event) -> None:
        """Process one anomaly.detected event."""
        started_at = datetime.now(timezone.utc)
        anomaly = event.payload

        try:
            # Retrieve similar past anomalies for LLM context
            similar = await self._get_similar_anomalies(anomaly)

            # Build context dict for the LLM prompt
            context = dict(anomaly)
            context["similar_anomalies"] = similar

            # Invoke LLM chain with tenacity retry
            try:
                result: RootCauseResult = await invoke_root_cause(
                    chain=self._chain,
                    anomaly_context=context,
                    model_id=self._get_model_id(),
                )
            except Exception as llm_exc:
                logger.warning("agent04.llm_failed", error=str(llm_exc))
                result = get_default_root_cause_result()

            # Build enriched payload = all anomaly fields + LLM outputs
            enriched_payload = dict(anomaly)
            enriched_payload.update({
                "root_cause": result.explanation,
                "confidence": result.confidence,
                "suggested_action": result.suggested_action,
                "model_used": result.model_used,
            })

            published_event = await self._bus.publish(
                topic=TOPIC_OUT,
                source_agent=AGENT_NAME,
                process_id=event.process_id,
                payload=enriched_payload,
            )

            logger.info(
                "agent04.enriched",
                anomaly_id=anomaly.get("anomaly_id"),
                model_used=result.model_used,
                confidence=result.confidence,
            )

            await self._log(event, published_event, "success", None, started_at, enriched_payload)

        except Exception as exc:
            logger.error("agent04.error", event_id=event.event_id, error=str(exc))
            await self._log(event, None, "error", str(exc), started_at)

    async def _get_similar_anomalies(self, anomaly: dict) -> list[dict]:
        """Query pgvector for similar past anomalies."""
        try:
            from core.vector_store import build_anomaly_source_text
            query_text = build_anomaly_source_text(anomaly)
            factory = get_session_factory()
            async with factory() as session:
                return await find_similar_anomalies(session, query_text, top_k=3)
        except Exception as exc:
            logger.debug("agent04.similar_anomalies_failed", error=str(exc))
            return []

    @staticmethod
    def _get_model_id() -> str:
        """Return the primary model ID for labeling in the result."""
        import os
        return os.getenv("LLM_MODEL_PRIMARY", "meta-llama/llama-3.1-8b-instruct:free")

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
            logger.warning("agent04.log_failed", error=str(log_exc))
