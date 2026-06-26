import os
import subprocess
from pathlib import Path

from app.tools.base import Tool, ToolResult

ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "echo", "pwd", "date",
    "whoami", "uname", "df", "du", "find", "grep", "wc",
    "which", "file", "stat", "mkdir", "touch", "cp",
}

FORBIDDEN_PATTERNS = [
    "rm ", "rmdir ", "dd ", "mkfs", "chmod", "chown",
    "sudo", "su ", "passwd", "kill", "shutdown", "reboot",
    ">", "|", "&&", "||", ";", "`", "$(",
]

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class ExecuteCommand(Tool):
    name = "execute_command"
    description = "Run a shell command (sandboxed: read-only allowed commands only)"
    parameters = {
        "command": {"type": "string", "description": "The command to run"},
    }

    async def execute(self, command: str = "", **kwargs) -> ToolResult:
        parts = command.strip().split()
        if not parts:
            return ToolResult(success=False, error="No command provided")

        base = parts[0]
        if base not in ALLOWED_COMMANDS:
            return ToolResult(
                success=False,
                error=f"Command '{base}' not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}",
            )

        for pat in FORBIDDEN_PATTERNS:
            if pat in command:
                return ToolResult(success=False, error=f"Forbidden pattern '{pat}' in command")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=WORKSPACE_ROOT,
            )
            output = result.stdout + result.stderr
            return ToolResult(
                success=result.returncode == 0,
                output=output.strip() or "(no output)",
                data={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="Command timed out (15s)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ReadFile(Tool):
    name = "read_file"
    description = "Read contents of a file within the project"
    parameters = {
        "path": {"type": "string", "description": "Relative path from project root"},
    }

    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        if not path:
            return ToolResult(success=False, error="No path provided")
        full = (WORKSPACE_ROOT / path).resolve()
        if not str(full).startswith(str(WORKSPACE_ROOT)):
            return ToolResult(success=False, error="Path outside workspace")
        if not full.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        try:
            text = full.read_text()
            return ToolResult(success=True, output=text, data={"size": len(text)})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WriteFile(Tool):
    name = "write_file"
    description = "Write content to a file within the project"
    parameters = {
        "path": {"type": "string", "description": "Relative path from project root"},
        "content": {"type": "string", "description": "Content to write"},
    }

    async def execute(self, path: str = "", content: str = "", **kwargs) -> ToolResult:
        if not path:
            return ToolResult(success=False, error="No path provided")
        full = (WORKSPACE_ROOT / path).resolve()
        if not str(full).startswith(str(WORKSPACE_ROOT)):
            return ToolResult(success=False, error="Path outside workspace")
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content)
            return ToolResult(success=True, output=f"Wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListDirectory(Tool):
    name = "list_directory"
    description = "List files and directories in a path"
    parameters = {
        "path": {"type": "string", "description": "Relative path from project root"},
    }

    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        if not path:
            path = "."
        full = (WORKSPACE_ROOT / path).resolve()
        if not str(full).startswith(str(WORKSPACE_ROOT)):
            return ToolResult(success=False, error="Path outside workspace")
        if not full.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")
        if not full.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {path}")
        try:
            entries = []
            for entry in sorted(full.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
            output = "\n".join(entries)
            return ToolResult(success=True, output=output, data={"entries": entries})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
