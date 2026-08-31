"""
Two kinds of raw WebSocket peers connect to this server:

  * Dashboard clients  -> GET /ws/dashboard
    Receive-only: every event the backend produces is broadcast to all of
    them as {"type": ..., "data": {...}}.

  * ESP32 terminals     -> GET /ws/terminal/{device_id}
    Send card-scan/mode/feedback/ration/tap/heartbeat frames; the backend
    validates them and re-broadcasts the resulting dashboard event.

Kept as one manager so REST calls can broadcast to dashboards the same way
terminal events do.
"""
import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger("vidyarthi.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self.dashboard_clients: Set[WebSocket] = set()
        self.terminal_clients: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    # ---------------- Dashboard clients ----------------
    async def connect_dashboard(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.dashboard_clients.add(ws)
        logger.info("dashboard client connected (%d total)", len(self.dashboard_clients))

    async def disconnect_dashboard(self, ws: WebSocket) -> None:
        async with self._lock:
            self.dashboard_clients.discard(ws)
        logger.info("dashboard client disconnected (%d total)", len(self.dashboard_clients))

    async def broadcast(self, message_type: str, data: dict) -> None:
        """Send {"type": message_type, "data": data} to every dashboard client."""
        payload = json.dumps({"type": message_type, "data": data})
        dead = []
        async with self._lock:
            targets = list(self.dashboard_clients)
        for client in targets:
            try:
                await client.send_text(payload)
            except Exception:
                dead.append(client)
        if dead:
            async with self._lock:
                for d in dead:
                    self.dashboard_clients.discard(d)

    # ---------------- ESP32 terminals ----------------
    async def connect_terminal(self, device_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.terminal_clients[device_id] = ws
        logger.info("terminal '%s' connected (%d total)", device_id, len(self.terminal_clients))

    async def disconnect_terminal(self, device_id: str) -> None:
        async with self._lock:
            self.terminal_clients.pop(device_id, None)
        logger.info("terminal '%s' disconnected", device_id)

    async def send_to_terminal(self, device_id: str, message: dict) -> bool:
        ws = self.terminal_clients.get(device_id)
        if not ws:
            return False
        try:
            await ws.send_text(json.dumps(message))
            return True
        except Exception:
            return False


manager = ConnectionManager()
