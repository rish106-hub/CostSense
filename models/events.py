"""
Event envelope and topic constants for the CostSense event bus.
Every message flowing through the system is wrapped in an Event.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


# All valid topic names in the pipeline
TOPIC = Literal[
    "raw.spend",
    "normalized.spend",
    "anomaly.detected",
    "anomaly.enriched",
    "anomaly.scored",
    "anomaly.ready",
    "action.approval_needed",
    "action.auto_execute",
]

ALL_TOPICS: list[str] = [
    "raw.spend",
    "normalized.spend",
    "anomaly.detected",
    "anomaly.enriched",
    "anomaly.scored",
    "anomaly.ready",
    "action.approval_needed",
    "action.auto_execute",
]


class Event(BaseModel):
    """
    Universal event envelope. Every agent publishes and consumes Events.
    The payload carries the topic-specific data as a plain dict so agents
    can evolve their schemas independently.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic: str
    source_agent: str
    process_id: str  # Shared UUID for an entire ingestion batch run
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


def make_event(
    topic: str,
    source_agent: str,
    process_id: str,
    payload: dict[str, Any],
) -> Event:
    """Convenience factory — creates a new Event with a fresh event_id and timestamp."""
    return Event(
        topic=topic,
        source_agent=source_agent,
        process_id=process_id,
        payload=payload,
    )
