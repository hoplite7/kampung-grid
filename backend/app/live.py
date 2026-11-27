"""The live update hub.

Every screen (dashboard, phones, control panel) opens a WebSocket to /ws.
When anything changes, call `await hub.broadcast({...})` and every screen
receives the message within a second.

Message shape: {"type": "<kind>", ...details}. The agreed types are listed in docs/api.md.
"""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import WebSocket


class LiveHub:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        # Other places that want every message too (e.g. the Telegram bot).
        self.listeners: list = []
        self._jobs: set = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.connections.discard(ws)

    async def broadcast(self, message: dict) -> None:
        message = {**message, "at": datetime.now(timezone.utc).isoformat()}
        text = json.dumps(message, default=str)
        dead = []
        for ws in list(self.connections):
            try:
                await ws.send_text(text)
            except Exception:  # screen closed or lost connection
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        for listener in self.listeners:
            job = asyncio.create_task(listener(message))
            self._jobs.add(job)
            job.add_done_callback(self._jobs.discard)


hub = LiveHub()
