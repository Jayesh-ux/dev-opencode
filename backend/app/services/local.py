import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.types import GeminiResult, ConversationFrame, _estimate_tokens


TOOL_CMD_PATTERN = re.compile(r"^!(?:(\w+)\((.+)\))$", re.MULTILINE)
SHELL_PATTERN = re.compile(r"^```(?:bash|sh|shell)\s*\n(.+?)\n```", re.DOTALL)


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4.0))


def local_chat(frame: ConversationFrame, message: str) -> GeminiResult:
    message_lower = message.strip().lower()
    history_text = "\n".join(
        f"{e.get('role','?')}: {e.get('text','')}" for e in frame.history[-6:]
    )

    response = _generate_response(message_lower, message, history_text, frame)

    prompt_tokens = _estimate_tokens(str(frame.history) + message)
    candidates_tokens = _estimate_tokens(response)
    total_tokens = prompt_tokens + candidates_tokens

    result = GeminiResult(
        text=response,
        prompt_tokens=prompt_tokens,
        candidates_tokens=candidates_tokens,
        total_tokens=total_tokens,
    )

    frame.total_prompt_tokens += result.prompt_tokens
    frame.total_candidates_tokens += result.candidates_tokens
    frame.total_tokens += result.total_tokens
    frame.history.append({"role": "user", "text": message})
    frame.history.append({"role": "model", "text": result.text})

    return result


def _generate_response(msg_lower: str, msg_original: str, history_text: str, frame: ConversationFrame) -> str:
    if msg_lower in ("hi", "hello", "hey", "yo", "hi there", "hello there"):
        num_previous = len(frame.history) // 2
        if num_previous > 0:
            return f"Hello again! You've sent {num_previous} message(s) so far. What would you like to do next?"
        return "Hello! I'm your local AI assistant. I can execute commands, read/write files, and list directories. What would you like me to do?"

    if msg_lower in ("help", "what can you do", "commands", "?"):
        return """I can help with these tasks using built-in tools:

- `!execute_command(command)` — Run any shell command
- `!read_file(path)` — Read the contents of a file
- `!write_file(path, content)` — Write content to a file
- `!list_directory(path)` — List files in a directory

Just tell me what you need, and I'll use the appropriate tool!"""

    ls_match = re.match(r"^(?:list|show|ls)\s+(.+)$", msg_lower)
    if ls_match:
        target = ls_match.group(1).strip()
        return f"I'll list that directory for you.\n\n!list_directory({target})"

    read_match = re.match(r"^(?:read|show|cat|open|view)\s+(.+)$", msg_lower)
    if read_match:
        target = read_match.group(1).strip()
        return f"Sure, let me read that file.\n\n!read_file({target})"

    write_match = re.match(r"^(?:write|create|save)\s+(.+?)(?:\s+(?:as|to)\s+(.+))?$", msg_lower)
    if write_match and write_match.group(2):
        content = write_match.group(1)
        path = write_match.group(2)
        return f"I'll write that content to the file.\n\n!write_file({path}, {content})"

    run_match = re.match(r"^(?:run|execute|do|bash|sh|shell)\s+(.+)$", msg_lower)
    if run_match:
        cmd = run_match.group(1).strip()
        return f"Running that command now.\n\n!execute_command({cmd})"

    if msg_lower.startswith("!execute_command("):
        return f"Executing the command as requested.\n\n{msg_original}"

    if msg_lower.startswith("!read_file("):
        return f"Reading the file as requested.\n\n{msg_original}"

    if msg_lower.startswith("!write_file("):
        return f"Writing the file as requested.\n\n{msg_original}"

    if msg_lower.startswith("!list_directory("):
        return f"Listing the directory as requested.\n\n{msg_original}"

    if re.search(r"(?:error|fail|bug|crash|wrong|issue)", msg_lower):
        file_match = re.search(r"(?:in|at|from|of)\s+(\S+\.\w+)", msg_lower)
        if file_match:
            target = file_match.group(1)
            return f"I'll look into that issue. Let me check the file first.\n\n!read_file({target})"
        return "I'll investigate that issue. What file or command should I start with?"

    if re.search(r"(?:install|setup|config|init)", msg_lower):
        return "I'll help with the setup. What would you like me to install or configure first?"

    for line in frame.history:
        text = line.get("text", "")
        if "[Tool:" in text and "FAIL" in text:
            tool_match = re.search(r"\[Tool:(\w+)\].*?-> FAIL:\s*(.+?)$", text)
            if tool_match:
                tool_name = tool_match.group(1)
                error_msg = tool_match.group(2)
                if "not found" in error_msg.lower() or "unknown" in error_msg.lower():
                    return f"That tool reported: {error_msg}.\n\nTry using a different approach or check the available tools with `!list_directory()`."

    if frame.history and any("[Tool:" in e.get("text", "") for e in frame.history[-4:]):
        last_tool_result = None
        for e in reversed(frame.history):
            if "[Tool:" in e.get("text", ""):
                last_tool_result = e.get("text", "")
                break
        if last_tool_result:
            return f"The previous operation completed. Here's what I know:\n\n{last_tool_result[:300]}\n\nWhat would you like to do next?"

    return f"I understand you want to: \"{msg_original}\". Could you clarify? You can say things like:\n- \"list the files in /root/dev\"\n- \"read the file run.sh\"\n- \"execute command ls -la\"\n- \"write 'hello world' to test.txt\""
