"""GET /bus/events — raw event bus history for debugging."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from core.bus import bus
from models.schemas import BusEventOut, BusEventsResponse

router = APIRouter(prefix="/bus", tags=["bus"])


@router.get("/events", response_model=BusEventsResponse)
async def get_bus_events(
    topic: Optional[str] = Query(default=None, description="Filter by topic name"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return recent events from the event bus history buffer."""
    events = bus.get_history(topic=topic, limit=limit)
    out = [
        BusEventOut(
            event_id=e.event_id,
            topic=e.topic,
            source_agent=e.source_agent,
            process_id=e.process_id,
            payload=e.payload,
            timestamp=e.timestamp,
        )
        for e in events
    ]
    return BusEventsResponse(count=len(out), events=out)
