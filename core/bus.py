"""
In-process event bus backed by asyncio.Queue.

Features:
  - Multiple subscribers per topic (fan-out)
  - Ring-buffer history per topic (for GET /bus/events)
  - Event count tracking per topic
  - Graceful start/stop lifecycle
  - Redis-swappable: expose the same interface in core/bus_redis.py

Usage:
    bus = EventBus()
    bus.subscribe("raw.spend", my_handler)
    await bus.start()
    await bus.publish("raw.spend", source_agent="agent_01", process_id="...", payload={...})
    await bus.stop()
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Awaitable, Callable

import structlog

from models.events import Event, make_event

logger = structlog.get_logger(__name__)

HandlerFn = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    Pub/sub event bus using one asyncio.Queue per topic.
    Handlers registered via subscribe() are called concurrently when an event arrives.
    """

    def __init__(self, history_size: int = 2000) -> None:
        self._history_size = history_size
        # One queue per topic — created lazily
        self._queues: dict[str, asyncio.Queue[Event]] = defaultdict(asyncio.Queue)
        # List of handlers per topic
        self._handlers: dict[str, list[HandlerFn]] = defaultdict(list)
        # Ring buffer history per topic
        self._history: dict[str, deque[Event]] = defaultdict(
            lambda: deque(maxlen=history_size)
        )
        # Event counts per topic
        self._counts: dict[str, int] = defaultdict(int)
        # Background drain tasks
        self._tasks: list[asyncio.Task] = []
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, topic: str, handler: HandlerFn) -> None:
        """Register a handler for a topic. Can be called before start()."""
        self._handlers[topic].append(handler)
        logger.debug("bus.subscribe", topic=topic, handler=handler.__qualname__)

    async def publish(
        self,
        topic: str,
        source_agent: str,
        process_id: str,
        payload: dict,
    ) -> Event:
        """Create an Event and enqueue it for all subscribers of the topic."""
        event = make_event(
            topic=topic,
            source_agent=source_agent,
            process_id=process_id,
            payload=payload,
        )
        self._history[topic].append(event)
        self._counts[topic] += 1
        await self._queues[topic].put(event)
        logger.debug("bus.published", topic=topic, event_id=event.event_id)
        return event

    def get_history(
        self, topic: str | None = None, limit: int = 100
    ) -> list[Event]:
        """Return recent events, optionally filtered by topic."""
        if topic:
            return list(self._history.get(topic, deque()))[-limit:]
        all_events: list[Event] = []
        for events in self._history.values():
            all_events.extend(events)
        all_events.sort(key=lambda e: e.timestamp)
        return all_events[-limit:]

    def get_event_counts(self) -> dict[str, int]:
        return dict(self._counts)

    def get_total_events(self) -> int:
        return sum(self._counts.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn one drain task per topic that has at least one subscriber."""
        if self._running:
            return
        self._running = True
        for topic, handlers in self._handlers.items():
            task = asyncio.create_task(
                self._drain_topic(topic, handlers),
                name=f"bus-drain-{topic}",
            )
            self._tasks.append(task)
        logger.info("bus.started", topics=list(self._handlers.keys()))

    async def stop(self) -> None:
        """Cancel all drain tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("bus.stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _drain_topic(self, topic: str, handlers: list[HandlerFn]) -> None:
        """Continuously dequeue events and fan out to all registered handlers."""
        queue = self._queues[topic]
        while self._running:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
                # Run all handlers concurrently for this event
                await asyncio.gather(
                    *[self._safe_call(handler, event) for handler in handlers],
                    return_exceptions=True,
                )
                queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    @staticmethod
    async def _safe_call(handler: HandlerFn, event: Event) -> None:
        """Call a handler, logging any exceptions without crashing the drain loop."""
        try:
            await handler(event)
        except Exception as exc:
            logger.error(
                "bus.handler_error",
                handler=handler.__qualname__,
                event_id=event.event_id,
                topic=event.topic,
                error=str(exc),
            )


# Module-level singleton — shared across all agents and API routes
bus = EventBus()
