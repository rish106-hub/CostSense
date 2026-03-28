"""GET / and GET /health — service status and pipeline metrics."""

from __future__ import annotations

import os

from fastapi import APIRouter

from core.bus import bus
from models.schemas import HealthOut

router = APIRouter(tags=["health"])

VERSION = "1.0.0"


@router.get("/", response_model=HealthOut)
async def root():
    """Basic health check — confirms the server is running."""
    return HealthOut(
        status="ok",
        version=VERSION,
        environment=os.getenv("ENVIRONMENT", "development"),
        events_processed=bus.get_total_events(),
        topics=bus.get_event_counts(),
        agents_registered=9,
    )


@router.get("/health", response_model=HealthOut)
async def health():
    """Pipeline health — event counts per topic."""
    return HealthOut(
        status="ok",
        version=VERSION,
        environment=os.getenv("ENVIRONMENT", "development"),
        events_processed=bus.get_total_events(),
        topics=bus.get_event_counts(),
        agents_registered=9,
    )
