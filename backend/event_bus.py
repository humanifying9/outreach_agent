"""Async event bus used to stream agent activity to WebSocket clients."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class AgentEvent:
    type: str  # "log" | "status" | "lead_found" | "draft_created" | "done" | "error"
    message: str
    data: Optional[dict] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "message": self.message,
            "data": self.data or {},
            "timestamp": self.timestamp,
        }


class EventBus:
    """Broadcasts AgentEvents to all subscribed asyncio.Queues."""

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def emit(self, event: AgentEvent):
        for q in list(self._subscribers):
            await q.put(event)

    async def log(self, message: str, **data: Any):
        await self.emit(AgentEvent(type="log", message=message, data=data or None))

    async def status(self, message: str, **data: Any):
        await self.emit(AgentEvent(type="status", message=message, data=data or None))

    async def error(self, message: str, **data: Any):
        await self.emit(AgentEvent(type="error", message=message, data=data or None))
