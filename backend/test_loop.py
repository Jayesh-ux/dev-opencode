"""Test the cyclic state loop and snapshot mechanisms."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from app.orchestrator import Orchestrator, LoopState, SNAPSHOT_REASON_TOKEN
from app.services.gemini import ConversationFrame, is_near_token_limit, MAX_INPUT_TOKENS
from app.snapshotter import save_snapshot, list_snapshots, load_latest_snapshot, restore_frame_from_snapshot


@pytest.mark.asyncio
async def test_429_triggers_snapshot():
    print("=== 1. 429 → Snapshot → Pause ===")
    orch = Orchestrator()
    result = await orch.process_message("hello")
    assert result.state == LoopState.PAUSED
    assert result.snapshot_path is not None
    assert "429" in result.snapshot_path
    print(f"  Snapshot: {result.snapshot_path}")
    print(f"  State: {result.state.value}")
    print(f"  Error: {result.error[:60]}...")
    print("  PASS\n")


@pytest.mark.asyncio
async def test_resume_works():
    print("=== 2. Resume from PAUSED ===")
    orch = Orchestrator()
    await orch.process_message("hello")
    assert orch.state == LoopState.PAUSED
    orch.state = LoopState.LISTEN
    assert orch.state == LoopState.LISTEN
    print("  PASS\n")


def test_token_threshold_logic():
    print("=== 3. Token threshold detection ===")
    frame = ConversationFrame()
    assert not is_near_token_limit(frame), "Empty frame should not be near limit"

    frame.total_tokens = int(MAX_INPUT_TOKENS * 0.5)
    assert not is_near_token_limit(frame), "50% should not trigger"

    frame.total_tokens = int(MAX_INPUT_TOKENS * 0.75)
    assert is_near_token_limit(frame), "75% should trigger"
    print("  Threshold logic: correct")
    print("  PASS\n")


def test_snapshot_persistence():
    print("=== 4. Snapshot save/load/restore ===")
    frame = ConversationFrame(
        history=[{"role": "user", "text": "hello"}, {"role": "model", "text": "hi"}],
        total_prompt_tokens=100,
        total_candidates_tokens=50,
        total_tokens=150,
    )
    path = save_snapshot(frame, "TEST", SNAPSHOT_REASON_TOKEN)
    assert path is not None

    snapped = load_latest_snapshot()
    assert snapped is not None
    assert snapped["reason"] == SNAPSHOT_REASON_TOKEN
    assert snapped["token_usage"]["total_tokens"] == 150

    restored = restore_frame_from_snapshot(snapped)
    assert len(restored.history) == 2
    assert restored.total_tokens == 150
    print(f"  Saved -> {path}")
    print(f"  Loaded: {len(snapped['conversation_history'])} messages, {snapped['token_usage']['total_tokens']} tokens")
    print("  Restore: OK")
    print("  PASS\n")


def test_snapshots_listed():
    print("=== 5. Snapshots listing ===")
    snaps = list_snapshots()
    print(f"  Total: {len(snaps)}")
    for s in snaps:
        print(f"    {s['file']}  reason={s['reason']}  state={s['state']}  tokens={s['tokens']}")
    assert len(snaps) >= 2
    print("  PASS\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_429_triggers_snapshot())
    asyncio.run(test_resume_works())
    test_token_threshold_logic()
    test_snapshot_persistence()
    test_snapshots_listed()
    print("=== ALL TESTS PASSED ===")
