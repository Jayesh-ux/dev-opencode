import re
from enum import Enum

from app.services.gemini import (
    ConversationFrame,
    GeminiResult,
    chat,
    is_near_token_limit,
    token_usage_pct,
)
from app.services.memory import MemoryManager
from app.services.prompter import TaskTracker, inject_system_prompt
from app.snapshotter import save_snapshot, restore_frame_from_snapshot, load_latest_snapshot
from app.tools import TOOL_REGISTRY, list_tools
from app.tools.base import ToolResult


class LoopState(str, Enum):
    LISTEN = "LISTEN"
    THINK = "THINK"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    PAUSED = "PAUSED"


SNAPSHOT_REASON_429 = "429_ERROR"
SNAPSHOT_REASON_TOKEN = "TOKEN_THRESHOLD"
SNAPSHOT_REASON_RECOVERY = "SESSION_RECOVERY"
SNAPSHOT_REASON_ROTATION = "CONTEXT_ROTATION"
TOOL_CALL_PATTERN = re.compile(r"^!(\w+)\((.*)\)$", re.MULTILINE)
SHELL_PATTERN = re.compile(r"^```(?:bash|sh|shell)\s*\n(.+?)\n```", re.DOTALL)


class OrchestratorResult:
    def __init__(
        self,
        text: str = "",
        state: LoopState = LoopState.LISTEN,
        snapshot_path: str | None = None,
        error: str | None = None,
        token_pct: float = 0.0,
        tool_results: list[dict] | None = None,
        rotation: bool = False,
        tasks: dict | None = None,
    ):
        self.text = text
        self.state = state
        self.snapshot_path = snapshot_path
        self.error = error
        self.token_pct = token_pct
        self.tool_results = tool_results or []
        self.rotation = rotation
        self.tasks = tasks or {}


class Orchestrator:
    def __init__(self):
        self.frame = ConversationFrame()
        self.state = LoopState.LISTEN
        self._current_tool_results: list[dict] = []
        self.memory = MemoryManager(self.frame)
        self.tasks = TaskTracker()
        self._try_recover()

    def _try_recover(self):
        snapshot = load_latest_snapshot()
        if snapshot:
            self.frame = restore_frame_from_snapshot(snapshot)
            save_snapshot(self.frame, self.state.value, SNAPSHOT_REASON_RECOVERY)

    def _parse_tool_invocations(self, text: str) -> list[tuple[str, str]]:
        invocations = []
        for match in TOOL_CALL_PATTERN.finditer(text):
            name, args_raw = match.groups()
            invocations.append((name.strip(), args_raw.strip()))
        return invocations

    def _parse_shell_blocks(self, text: str) -> list[str]:
        blocks = []
        for match in SHELL_PATTERN.finditer(text):
            blocks.append(match.group(1).strip())
        return blocks

    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool '{tool_name}'. Available: {', '.join(TOOL_REGISTRY.keys())}",
            )
        return await tool.execute(**kwargs)

    def _inject_self_prompt(self):
        prompt = self.tasks.get_self_prompt()
        inject_system_prompt(self.frame, prompt)

    def _check_task_updates(self, response_text: str):
        tasks_found = self.tasks.extract_tasks(response_text)
        if tasks_found and not self.tasks.current_list:
            self.tasks.create_task_list(tasks_found)
        updates = self.tasks.extract_status_updates(response_text)
        if updates:
            self.tasks.apply_updates(updates)

    async def process_message(self, message: str) -> OrchestratorResult:
        self._current_tool_results = []

        try:
            return await self._process_message_inner(message)
        except Exception as e:
            path = save_snapshot(self.frame, self.state.value, "UNHANDLED_ERROR")
            self.state = LoopState.PAUSED
            return OrchestratorResult(
                text="",
                state=self.state,
                snapshot_path=path,
                error=f"Unexpected error: {str(e)}. Session snapshot saved. Resume when ready.",
                token_pct=token_usage_pct(self.frame),
                tasks=self.tasks.get_summary(),
            )

    async def _process_message_inner(self, message: str) -> OrchestratorResult:
        self._current_tool_results = []

        self._inject_self_prompt()
        self.memory.frame = self.frame

        if self.memory.needs_rotation():
            summary = self.memory.rotate_context()
            self.frame = self.memory.frame
            snapshot_path = None
            for s in self.memory.archives[:1]:
                snapshot_path = s.path

        self.state = LoopState.THINK
        result: GeminiResult = chat(self.frame, message)

        if result.error_code == 429:
            path = save_snapshot(self.frame, self.state.value, SNAPSHOT_REASON_429)
            self.state = LoopState.PAUSED
            return OrchestratorResult(
                text="",
                state=self.state,
                snapshot_path=path,
                error="Quota exceeded (429). Session snapshot saved. Resume when quota is available.",
                token_pct=token_usage_pct(self.frame),
                tasks=self.tasks.get_summary(),
            )

        if result.error_code:
            self.state = LoopState.LISTEN
            return OrchestratorResult(
                text="",
                state=self.state,
                error=result.error_message,
                token_pct=token_usage_pct(self.frame),
                tasks=self.tasks.get_summary(),
            )

        self._check_task_updates(result.text)

        self.state = LoopState.ACT
        tool_invocations = self._parse_tool_invocations(result.text)
        shell_blocks = self._parse_shell_blocks(result.text) if not tool_invocations else []

        tool_results_list = []
        if tool_invocations:
            for name, args_raw in tool_invocations:
                tr = await self.execute_tool(name, command=args_raw)
                tool_results_list.append({
                    "tool": name,
                    "args": args_raw,
                    "success": tr.success,
                    "output": tr.output[:500],
                    "error": tr.error,
                })
                entry = f"[Tool:{name}] args={args_raw} -> {'OK' if tr.success else 'FAIL'}: {(tr.output or tr.error)[:200]}"
                self.frame.history.append({"role": "tool", "text": entry})
        elif shell_blocks:
            for block in shell_blocks:
                tr = await self.execute_tool("execute_command", command=block)
                tool_results_list.append({
                    "tool": "execute_command",
                    "args": block,
                    "success": tr.success,
                    "output": tr.output[:500],
                    "error": tr.error,
                })
                entry = f"[Shell] -> {'OK' if tr.success else 'FAIL'}: {(tr.output or tr.error)[:200]}"
                self.frame.history.append({"role": "tool", "text": entry})

        self._current_tool_results = tool_results_list

        self.state = LoopState.OBSERVE
        if is_near_token_limit(self.frame):
            path = save_snapshot(self.frame, self.state.value, SNAPSHOT_REASON_TOKEN)
            self.state = LoopState.PAUSED
            return OrchestratorResult(
                text=result.text,
                state=self.state,
                snapshot_path=path,
                error=f"Token threshold reached ({token_usage_pct(self.frame):.0%}). Context rotated. Snapshot saved.",
                token_pct=token_usage_pct(self.frame),
                tool_results=tool_results_list,
                tasks=self.tasks.get_summary(),
            )

        self.memory.frame = self.frame
        if self.memory.needs_rotation():
            summary = self.memory.rotate_context()
            self.frame = self.memory.frame
            return OrchestratorResult(
                text=result.text,
                state=self.state,
                error=f"Context rotated. {summary}",
                token_pct=token_usage_pct(self.frame),
                tool_results=tool_results_list,
                rotation=True,
                tasks=self.tasks.get_summary(),
            )

        self.state = LoopState.LISTEN
        return OrchestratorResult(
            text=result.text,
            state=self.state,
            token_pct=token_usage_pct(self.frame),
            tool_results=tool_results_list,
            tasks=self.tasks.get_summary(),
        )

    def get_status(self) -> dict:
        return {
            "state": self.state.value,
            "total_tokens": self.frame.total_tokens,
            "token_usage_pct": round(token_usage_pct(self.frame) * 100, 1),
            "history_length": len(self.frame.history),
            "available_tools": list(TOOL_REGISTRY.keys()),
            "last_tool_results": self._current_tool_results,
            "memory": self.memory.get_memory_stats(),
            "tasks": self.tasks.get_summary(),
        }
