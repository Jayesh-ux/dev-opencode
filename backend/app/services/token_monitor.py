import asyncio
import logging
from pathlib import Path

from app.services.types import MAX_INPUT_TOKENS, TOKEN_WARNING_THRESHOLD
from app.snapshotter import save_snapshot
from app.services.gemini import ConversationFrame
from app.services.ws_manager import pool, sessions

logger = logging.getLogger(__name__)

MONITOR_INTERVAL = 30
TOKEN_ESTIMATE_RATIO = 4.0


class TokenMonitor:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._snapshot_count = 0

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            logger.info(
                "TokenMonitor started (interval=%ds, threshold=%.0f%%)",
                MONITOR_INTERVAL, TOKEN_WARNING_THRESHOLD * 100,
            )

    async def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("TokenMonitor stopped")

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return max(1, int(len(text) / TOKEN_ESTIMATE_RATIO))

    def check_session(self, session_id: str) -> dict | None:
        history = sessions.get_history(session_id, max_len=200)
        if not history:
            return None

        total_tokens = sum(self.estimate_tokens(m.get("text", "")) for m in history)
        usage_pct = total_tokens / MAX_INPUT_TOKENS if MAX_INPUT_TOKENS > 0 else 0.0

        result = {
            "session_id": session_id,
            "total_tokens": total_tokens,
            "max_tokens": MAX_INPUT_TOKENS,
            "pct": round(usage_pct * 100, 1),
            "message_count": len(history),
            "triggered": False,
        }

        if usage_pct >= TOKEN_WARNING_THRESHOLD:
            conv_frame = ConversationFrame(
                history=[
                    {"role": m.get("role", "user"), "text": m.get("text", "")}
                    for m in history
                ],
                total_prompt_tokens=total_tokens,
                total_candidates_tokens=0,
                total_tokens=total_tokens,
            )
            snapshot_path = save_snapshot(conv_frame, "MONITOR", f"TOKEN_{int(usage_pct*100)}pct")
            self._snapshot_count += 1
            logger.warning(
                "TokenMonitor snapshot [%s]: %d tokens (%.1f%%) -> %s",
                session_id, total_tokens, usage_pct * 100, snapshot_path,
            )
            result["snapshot"] = str(snapshot_path)
            result["snapshot_file"] = Path(snapshot_path).name
            result["triggered"] = True

        pct_int = int(usage_pct * 100)
        if pct_int % 10 == 0 and pct_int > 0:
            logger.info(
                "TokenMonitor [%s]: %d tokens (%.1f%%) %d messages",
                session_id, total_tokens, usage_pct * 100, len(history),
            )

        return result

    async def _run_loop(self):
        while True:
            try:
                await asyncio.sleep(MONITOR_INTERVAL)
                active = sessions.active_sessions()
                for sid in active:
                    result = self.check_session(sid)
                    if result and result.get("triggered"):
                        ws = pool.get_research(sid)
                        if ws:
                            try:
                                await ws.send_json({
                                    "type": "token_warning",
                                    "pct": result["pct"],
                                    "total_tokens": result["total_tokens"],
                                    "max_tokens": result["max_tokens"],
                                    "snapshot": result.get("snapshot_file", ""),
                                })
                            except Exception:
                                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("TokenMonitor loop error: %s", e)


token_monitor = TokenMonitor()
