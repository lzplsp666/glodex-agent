from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """Route AGUI events from thread_id to the active WebSocket."""

    def __init__(self) -> None:
        self.active: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        """Accept and register the active WebSocket for a thread."""
        await websocket.accept()
        async with self._lock:
            self.active[thread_id] = websocket

    async def disconnect(self, websocket: WebSocket, thread_id: str) -> None:
        """Unregister a WebSocket, without deleting a newer reconnect."""
        async with self._lock:
            if self.active.get(thread_id) is websocket:
                del self.active[thread_id]

    async def send_to_thread(self, payload: dict[str, Any], thread_id: str) -> None:
        """Send a payload to the active WebSocket for a thread."""
        websocket = self.active.get(thread_id)
        if websocket is None:
            return

        try:
            await websocket.send_json(payload)
        except Exception:
            await self.disconnect(websocket, thread_id)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Send a payload to every active thread WebSocket."""
        for thread_id in list(self.active):
            await self.send_to_thread(payload, thread_id)


manager = ConnectionManager()
