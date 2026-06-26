from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GeminiResult:
    text: str
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    total_tokens: int = 0
    error_code: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class ConversationFrame:
    history: list = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_candidates_tokens: int = 0
    total_tokens: int = 0


MAX_INPUT_TOKENS = 1_000_000
TOKEN_WARNING_THRESHOLD = 0.7


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4.0))


def token_usage_pct(frame: ConversationFrame) -> float:
    if MAX_INPUT_TOKENS == 0:
        return 0.0
    return frame.total_tokens / MAX_INPUT_TOKENS
