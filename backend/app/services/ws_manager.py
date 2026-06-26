import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

SESSION_TTL = 1800.0
CLEANUP_INTERVAL = 300.0


class ConnectionPool:
    def __init__(self):
        self._research: dict[str, WebSocket] = {}
        self._opencode: dict[str, WebSocket] = {}
        self._research_replaced: set[str] = set()
        self._opencode_replaced: set[str] = set()

    def add_research(self, session_id: str, ws: WebSocket):
        old = self._research.get(session_id)
        self._research[session_id] = ws
        if old:
            self._research_replaced.add(session_id)
            logger.info("Research WS replaced: %s", session_id)
        else:
            logger.info("Research WS connected: %s", session_id)

    def add_opencode(self, session_id: str, ws: WebSocket):
        old = self._opencode.get(session_id)
        self._opencode[session_id] = ws
        if old:
            self._opencode_replaced.add(session_id)
            logger.info("OpenCode WS replaced: %s", session_id)
        else:
            logger.info("OpenCode WS connected: %s", session_id)

    def remove_research(self, session_id: str):
        if session_id in self._research_replaced:
            self._research_replaced.discard(session_id)
            logger.info("Research WS remove skipped (was replaced): %s", session_id)
            return
        self._research.pop(session_id, None)
        logger.info("Research WS disconnected: %s", session_id)

    def remove_opencode(self, session_id: str):
        if session_id in self._opencode_replaced:
            self._opencode_replaced.discard(session_id)
            logger.info("OpenCode WS remove skipped (was replaced): %s", session_id)
            return
        self._opencode.pop(session_id, None)
        logger.info("OpenCode WS disconnected: %s", session_id)

    def get_research(self, session_id: str) -> WebSocket | None:
        return self._research.get(session_id)

    def get_opencode(self, session_id: str) -> WebSocket | None:
        return self._opencode.get(session_id)

    async def broadcast_research(self, session_id: str, data: dict):
        ws = self.get_research(session_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.remove_research(session_id)

    async def broadcast_opencode(self, session_id: str, data: dict):
        ws = self.get_opencode(session_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                self.remove_opencode(session_id)


pool = ConnectionPool()


class SessionStore:
    def __init__(self):
        self._history: dict[str, list[dict]] = {}
        self._context: dict[str, dict] = {}
        self._created: dict[str, float] = {}

    def ensure(self, session_id: str):
        if session_id not in self._history:
            self._history[session_id] = []
            self._context[session_id] = {"todos": [], "state": "research"}
            self._created[session_id] = time.time()

    def add_message(self, session_id: str, role: str, text: str):
        self.ensure(session_id)
        self._history[session_id].append({"role": role, "text": text, "ts": time.time()})

    def get_history(self, session_id: str, max_len: int = 50) -> list[dict]:
        self.ensure(session_id)
        return self._history[session_id][-max_len:]

    def get_formatted_history(self, session_id: str, max_len: int = 50) -> str:
        entries = self.get_history(session_id, max_len)
        return "\n".join(f"{e['role']}: {e['text']}" for e in entries)

    def set_context(self, session_id: str, key: str, value: Any):
        self.ensure(session_id)
        self._context[session_id][key] = value

    def get_context(self, session_id: str) -> dict:
        self.ensure(session_id)
        return self._context[session_id]

    def clear(self, session_id: str):
        self._history.pop(session_id, None)
        self._context.pop(session_id, None)
        self._created.pop(session_id, None)

    def evict_stale(self, max_age: float = SESSION_TTL) -> int:
        now = time.time()
        stale = [sid for sid, ts in self._created.items() if now - ts > max_age]
        for sid in stale:
            self.clear(sid)
        if stale:
            logger.info("Evicted %d stale session(s)", len(stale))
        return len(stale)

    def active_sessions(self) -> list[str]:
        return list(self._created.keys())

    def active_count(self) -> int:
        return len(self._created)

    async def run_cleanup_loop(self, interval: float = CLEANUP_INTERVAL):
        while True:
            await asyncio.sleep(interval)
            self.evict_stale()


sessions = SessionStore()
