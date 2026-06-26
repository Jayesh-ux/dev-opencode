import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.gemini import ConversationFrame

TASK_PATTERN = re.compile(
    r"(?:^|\n)\s*[-*]\s*\[?(TODO|IN_PROGRESS|DONE|BLOCKED|CANCELLED)\]?\s+(.+)",
    re.MULTILINE,
)
STEP_PATTERN = re.compile(
    r"(?:^|\n)\s*(\d+)[.)]\s*(.+?)(?=\s*\n\s*\d+[.)]\s*|\s*$)",
    re.DOTALL,
)

SYSTEM_PROMPT = """You are an autonomous AI assistant with self-prompting capability.
You can track your own tasks, break down complex requests into steps, and execute them methodically.

Available tools:
- !execute_command(command) - Run shell commands
- !read_file(path) - Read file contents
- !write_file(path, content) - Write to files
- !list_directory(path) - List directory contents

When given a task:
1. Break it down into numbered steps
2. Work through them one at a time
3. Track progress with [TODO], [IN_PROGRESS], [DONE], [BLOCKED]
4. Use tools by writing !tool_name(args) on its own line
5. Report progress naturally as you complete steps"""


@dataclass
class Task:
    description: str
    status: str = "TODO"
    step_number: int = 0


@dataclass
class TaskList:
    tasks: list[Task] = field(default_factory=list)
    current_step: int = 0

    def add(self, description: str):
        self.tasks.append(Task(description=description, step_number=len(self.tasks) + 1))

    def mark_in_progress(self, step: int):
        for t in self.tasks:
            if t.step_number == step:
                t.status = "IN_PROGRESS"
                break

    def mark_done(self, step: int):
        for t in self.tasks:
            if t.step_number == step:
                t.status = "DONE"
                break

    def mark_blocked(self, step: int):
        for t in self.tasks:
            if t.step_number == step:
                t.status = "BLOCKED"
                break

    def next_pending(self) -> Optional[Task]:
        for t in self.tasks:
            if t.status == "TODO":
                return t
        return None

    def to_prompt(self) -> str:
        if not self.tasks:
            return ""
        lines = ["Current task plan:"]
        for t in self.tasks:
            lines.append(f"  [{t.status}] Step {t.step_number}: {t.description}")
        return "\n".join(lines)

    def progress_pct(self) -> float:
        if not self.tasks:
            return 0.0
        done = sum(1 for t in self.tasks if t.status == "DONE")
        return done / len(self.tasks)


class TaskTracker:
    def __init__(self):
        self.task_lists: list[TaskList] = []
        self.current_list: Optional[TaskList] = None

    def extract_tasks(self, response_text: str) -> list[str]:
        tasks = []
        for match in STEP_PATTERN.finditer(response_text):
            num, desc = match.groups()
            tasks.append(desc.strip())
        return tasks

    def extract_status_updates(self, response_text: str) -> list[tuple[str, str]]:
        updates = []
        for match in TASK_PATTERN.finditer(response_text):
            status, desc = match.groups()
            updates.append((status, desc.strip()))
        return updates

    def create_task_list(self, tasks: list[str]):
        tl = TaskList()
        for t in tasks:
            tl.add(t)
        self.task_lists.append(tl)
        self.current_list = tl

    def apply_updates(self, updates: list[tuple[str, str]]):
        if not self.current_list:
            return
        for status, desc in updates:
            for t in self.current_list.tasks:
                if desc.lower() in t.description.lower():
                    t.status = status
                    break

    def get_self_prompt(self) -> str:
        parts = [SYSTEM_PROMPT]
        if self.current_list:
            parts.append(self.current_list.to_prompt())
        return "\n\n".join(parts)

    def get_summary(self) -> dict:
        if not self.current_list:
            return {"active": False, "tasks": [], "progress": 0}
        return {
            "active": True,
            "tasks": [
                {"step": t.step_number, "status": t.status, "description": t.description}
                for t in self.current_list.tasks
            ],
            "progress_pct": round(self.current_list.progress_pct() * 100, 1),
        }


def inject_system_prompt(frame: ConversationFrame, prompt: str):
    system_entry = {"role": "system", "text": prompt}
    if frame.history and frame.history[0].get("role") == "system":
        frame.history[0] = system_entry
    else:
        frame.history.insert(0, system_entry)
