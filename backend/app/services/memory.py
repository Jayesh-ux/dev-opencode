import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.gemini import ConversationFrame, MAX_INPUT_TOKENS
from app.snapshotter import save_snapshot

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".ai" / "MEMORY"
ROTATION_THRESHOLD = 0.7
KEEP_RECENT = 6
TOKEN_ESTIMATE_RATIO = 4.0


@dataclass
class ArchivedFrame:
    id: str
    summary: str
    message_count: int
    token_count: int
    timestamp: str
    path: str


class MemoryManager:
    def __init__(self, frame: ConversationFrame):
        self.frame = frame
        self.archives: list[ArchivedFrame] = []
        self.rotation_count = 0
        self._load_archives()

    def _load_archives(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        for f in sorted(MEMORY_DIR.glob("archive_*.json"), reverse=True):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                self.archives.append(ArchivedFrame(
                    id=data["id"],
                    summary=data["summary"],
                    message_count=data["message_count"],
                    token_count=data["token_count"],
                    timestamp=data["timestamp"],
                    path=str(f),
                ))
            except (json.JSONDecodeError, KeyError):
                continue

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text) / TOKEN_ESTIMATE_RATIO) + 1

    def needs_rotation(self) -> bool:
        if MAX_INPUT_TOKENS == 0:
            return False
        return (self.frame.total_tokens / MAX_INPUT_TOKENS) >= ROTATION_THRESHOLD

    def rotate_context(self) -> str:
        save_snapshot(self.frame, "ROTATION", "CONTEXT_ROTATION")

        old_messages = self.frame.history[:-KEEP_RECENT * 2] if len(self.frame.history) > KEEP_RECENT * 2 else []
        recent_messages = self.frame.history[-(KEEP_RECENT * 2):] if len(self.frame.history) > KEEP_RECENT * 2 else list(self.frame.history)

        summary = self._summarize(old_messages)

        summary_prompt = (
            f"[Context Summary from previous {len(old_messages)} messages]: {summary}"
        )

        self._archive(old_messages, summary)

        self.frame.history = (
            [{"role": "system", "text": summary_prompt}]
            + recent_messages
        )

        estimated = self._estimate_tokens(summary_prompt)
        recent_tokens = sum(self._estimate_tokens(m.get("text", "")) for m in recent_messages)
        self.frame.total_prompt_tokens = estimated
        self.frame.total_candidates_tokens = 0
        self.frame.total_tokens = estimated + recent_tokens

        self.rotation_count += 1
        return summary

    def _summarize(self, messages: list[dict]) -> str:
        if not messages:
            return "No prior context."

        topics: dict[str, int] = {}
        tool_calls = 0
        total = len(messages)

        for m in messages:
            role = m.get("role", "")
            text = m.get("text", "")
            if role == "tool":
                tool_calls += 1
            elif role in ("user", "model"):
                words = text.lower().split()[:20]
                for w in words:
                    if len(w) > 4:
                        topics[w] = topics.get(w, 0) + 1

        top_topics = sorted(topics, key=topics.get, reverse=True)[:8]
        topic_str = ", ".join(top_topics) if top_topics else "general conversation"

        return (
            f"{total} messages covering: {topic_str}. "
            f"{tool_calls} tool calls executed. "
            f"Archived for full recovery."
        )

    def _archive(self, messages: list[dict], summary: str):
        if not messages:
            return
        os.makedirs(MEMORY_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archive_id = f"archive_{ts}_{self.rotation_count}"
        path = MEMORY_DIR / f"{archive_id}.json"

        data = {
            "id": archive_id,
            "summary": summary,
            "message_count": len(messages),
            "token_count": self._estimate_tokens(json.dumps(messages)),
            "timestamp": ts,
            "messages": messages,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        self.archives.insert(0, ArchivedFrame(
            id=archive_id,
            summary=summary,
            message_count=len(messages),
            token_count=data["token_count"],
            timestamp=ts,
            path=str(path),
        ))

    def _find_recent_archives(self, n: int = 3) -> list[ArchivedFrame]:
        return self.archives[:n]

    def build_system_context(self) -> list[dict]:
        parts = []
        for arch in self._find_recent_archives(2):
            parts.append({
                "role": "system",
                "text": f"[Archived Context {arch.id}]: {arch.summary} ({arch.message_count} messages, {arch.token_count} tokens)",
            })
        return parts

    def get_memory_stats(self) -> dict:
        return {
            "rotation_count": self.rotation_count,
            "archives_count": len(self.archives),
            "current_history_length": len(self.frame.history),
            "current_tokens": self.frame.total_tokens,
        }
