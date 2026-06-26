"""Test Phase 5: Memory Manager + Self-Prompting Task Tracker."""
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.gemini import ConversationFrame, MAX_INPUT_TOKENS
from app.services.memory import MemoryManager, ROTATION_THRESHOLD, MEMORY_DIR
from app.services.prompter import TaskTracker
from app.orchestrator import Orchestrator, LoopState


# Clean slate for all memory tests
if MEMORY_DIR.exists():
    shutil.rmtree(MEMORY_DIR)


def test_memory_rotation_detection():
    print("=== 1. Rotation Detection ===")
    frame = ConversationFrame()
    mem = MemoryManager(frame)
    assert not mem.needs_rotation(), "Empty frame should not need rotation"

    frame.total_tokens = int(MAX_INPUT_TOKENS * ROTATION_THRESHOLD) - 1
    assert not mem.needs_rotation(), "Just below threshold should not trigger"

    frame.total_tokens = int(MAX_INPUT_TOKENS * ROTATION_THRESHOLD) + 1
    assert mem.needs_rotation(), "Above threshold should trigger"
    print("  Detection logic: correct")
    print("  PASS\n")


def test_context_rotation():
    print("=== 2. Full Context Rotation ===")
    frame = ConversationFrame()
    for i in range(20):
        frame.history.append({"role": "user", "text": f"Query number {i}"})
        frame.history.append({"role": "model", "text": f"Response for query {i} with extra padding"})
    frame.total_tokens = int(MAX_INPUT_TOKENS * 0.8)

    mem = MemoryManager(frame)
    assert mem.needs_rotation()

    summary = mem.rotate_context()
    print(f"  Summary: {summary[:100]}...")
    print(f"  History length: {len(frame.history)} (expected ≤14)")
    print(f"  Rotation count: {mem.rotation_count}")
    print(f"  Archives: {len(mem.archives)}")

    assert len(frame.history) <= 14, f"History too long: {len(frame.history)}"
    assert mem.rotation_count == 1
    assert len(mem.archives) == 1
    assert mem.archives[0].message_count == 28  # 20 pairs - 12 kept = 28 archived
    assert frame.history[0]["role"] == "system"
    print("  PASS\n")


def test_double_rotation():
    print("=== 3. Double Rotation (archives accumulate) ===")
    import shutil
    if MEMORY_DIR.exists():
        shutil.rmtree(MEMORY_DIR)
    frame = ConversationFrame()
    for i in range(20):
        frame.history.append({"role": "user", "text": f"Q{i}"})
        frame.history.append({"role": "model", "text": f"A{i}"})
    frame.total_tokens = int(MAX_INPUT_TOKENS * 0.8)

    mem = MemoryManager(frame)
    mem.rotate_context()

    for i in range(20):
        frame.history.append({"role": "user", "text": f"Second batch Q{i}"})
        frame.history.append({"role": "model", "text": f"Second batch A{i}"})
    frame.total_tokens = int(MAX_INPUT_TOKENS * 0.8)

    mem.rotate_context()
    print(f"  Rotation count: {mem.rotation_count}")
    print(f"  Archives: {len(mem.archives)}")
    assert mem.rotation_count == 2
    assert len(mem.archives) == 2
    print("  PASS\n")


def test_task_extraction():
    print("=== 4. Task Extraction from Response ===")
    tracker = TaskTracker()
    response = """Here is my plan:
1. First step - create the file
2. Second step - write content
3. Third step - verify it"""
    tasks = tracker.extract_tasks(response)
    print(f"  Extracted: {len(tasks)} tasks")
    assert len(tasks) == 3
    tracker.create_task_list(tasks)
    assert tracker.current_list is not None
    assert len(tracker.current_list.tasks) == 3
    print("  PASS\n")


def test_task_status_updates():
    print("=== 5. Status Updates from Response ===")
    tracker = TaskTracker()
    tracker.create_task_list(["Create file", "Write content", "Verify"])

    response = "- [IN_PROGRESS] Create file"
    updates = tracker.extract_status_updates(response)
    tracker.apply_updates(updates)
    assert tracker.current_list.tasks[0].status == "IN_PROGRESS"

    response = "- [DONE] Create file\n- [IN_PROGRESS] Write content"
    updates = tracker.extract_status_updates(response)
    tracker.apply_updates(updates)
    assert tracker.current_list.tasks[0].status == "DONE"
    assert tracker.current_list.tasks[1].status == "IN_PROGRESS"

    response = "- [DONE] Write content\n- [DONE] Verify"
    updates = tracker.extract_status_updates(response)
    tracker.apply_updates(updates)
    assert tracker.current_list.tasks[2].status == "DONE"

    summary = tracker.get_summary()
    print(f"  Progress: {summary['progress_pct']}%")
    assert summary["progress_pct"] == 100.0
    print("  PASS\n")


def test_self_prompt_generation():
    print("=== 6. Self-Prompt Generation ===")
    tracker = TaskTracker()
    prompt = tracker.get_self_prompt()
    assert "autonomous" in prompt.lower()
    assert "!execute_command" in prompt

    tracker.create_task_list(["Step one", "Step two"])
    prompt2 = tracker.get_self_prompt()
    assert "Step one" in prompt2
    assert "Step two" in prompt2
    assert "TODO" in prompt2
    print("  Prompt contains system instructions: YES")
    print("  Prompt contains task list: YES")
    print("  PASS\n")


def test_inject_system_prompt():
    print("=== 7. System Prompt Injection ===")
    from app.services.prompter import inject_system_prompt
    frame = ConversationFrame()
    frame.history.append({"role": "user", "text": "hello"})
    inject_system_prompt(frame, "System prompt here")
    assert frame.history[0]["role"] == "system"
    assert frame.history[0]["text"] == "System prompt here"
    assert len(frame.history) == 2

    inject_system_prompt(frame, "Updated prompt")
    assert frame.history[0]["text"] == "Updated prompt"
    assert len(frame.history) == 2
    print("  System prompt injected and updated: YES")
    print("  PASS\n")


def test_orchestrator_status_includes_memory_and_tasks():
    print("=== 8. Orchestrator Status Fields ===")
    orch = Orchestrator()
    status = orch.get_status()
    assert "memory" in status
    assert "tasks" in status
    assert status["memory"]["rotation_count"] >= 0
    assert status["tasks"]["active"] is False
    print(f"  memory: {status['memory']}")
    print(f"  tasks: {status['tasks']}")
    print("  PASS\n")


def test_orchestrator_injects_self_prompt():
    print("=== 9. Self-Prompt Injected Before Chat ===")
    orch = Orchestrator()
    orch.frame.history = []
    orch._inject_self_prompt()
    assert len(orch.frame.history) > 0
    assert orch.frame.history[0]["role"] == "system"
    assert "autonomous" in orch.frame.history[0]["text"]
    print("  Self-prompt present in frame: YES")
    print("  PASS\n")


def test_archive_persistence():
    print("=== 10. Archive Persistence ===")
    import shutil
    if MEMORY_DIR.exists():
        shutil.rmtree(MEMORY_DIR)

    frame = ConversationFrame()
    for i in range(20):
        frame.history.append({"role": "user", "text": f"Q{i}"})
        frame.history.append({"role": "model", "text": f"A{i}"})
    frame.total_tokens = int(MAX_INPUT_TOKENS * 0.8)

    mem1 = MemoryManager(frame)
    mem1.rotate_context()
    assert MEMORY_DIR.exists()
    files = list(MEMORY_DIR.glob("archive_*.json"))
    assert len(files) == 1

    mem2 = MemoryManager(ConversationFrame())
    assert len(mem2.archives) == 1
    print(f"  Archive files: {len(files)}")
    print(f"  Reloaded archives: {len(mem2.archives)}")
    print("  PASS\n")


if __name__ == "__main__":
    test_memory_rotation_detection()
    test_context_rotation()
    test_double_rotation()
    test_task_extraction()
    test_task_status_updates()
    test_self_prompt_generation()
    test_inject_system_prompt()
    test_orchestrator_status_includes_memory_and_tasks()
    test_orchestrator_injects_self_prompt()
    test_archive_persistence()
    print("=== ALL 10 PHASE 5 TESTS PASSED ===")
