import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.services.gemini import ConversationFrame

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / ".ai" / "SNAPSHOTS"


def _ensure_dir():
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def save_snapshot(
    frame: ConversationFrame,
    state: str,
    reason: str,
) -> str:
    _ensure_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"snapshot_{timestamp}_{reason}.json"
    path = SNAPSHOTS_DIR / filename

    snapshot = {
        "timestamp": timestamp,
        "reason": reason,
        "state": state,
        "conversation_history": frame.history,
        "token_usage": {
            "total_prompt_tokens": frame.total_prompt_tokens,
            "total_candidates_tokens": frame.total_candidates_tokens,
            "total_tokens": frame.total_tokens,
        },
    }

    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)

    return str(path)


def load_latest_snapshot() -> Optional[dict]:
    _ensure_dir()
    files = sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        return json.load(f)


def restore_frame_from_snapshot(snapshot: dict) -> ConversationFrame:
    usage = snapshot.get("token_usage", {})
    return ConversationFrame(
        history=snapshot.get("conversation_history", []),
        total_prompt_tokens=usage.get("total_prompt_tokens", 0),
        total_candidates_tokens=usage.get("total_candidates_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )


def list_snapshots() -> list[dict]:
    _ensure_dir()
    results = []
    for path in sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), reverse=True):
        with open(path) as f:
            data = json.load(f)
        results.append(
            {
                "file": path.name,
                "timestamp": data.get("timestamp"),
                "reason": data.get("reason"),
                "state": data.get("state"),
                "tokens": data.get("token_usage", {}).get("total_tokens", 0),
            }
        )
    return results
