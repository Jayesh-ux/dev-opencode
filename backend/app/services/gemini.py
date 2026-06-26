import json
import logging
import random
import time

import requests

from app.core import GEMINI_API_KEY, GEMINI_MODEL_VERSION
from app.services.types import (
    ConversationFrame,
    GeminiResult,
    MAX_INPUT_TOKENS,
    _estimate_tokens,
    token_usage_pct,
)

logger = logging.getLogger(__name__)

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_VERSION}:generateContent"
TOKEN_WARNING_THRESHOLD = 0.7
MAX_RETRIES = 3
BASE_DELAY = 1.0

ROLE_MAP = {
    "user": "user",
    "model": "model",
    "assistant": "model",
    "tool": "user",
    "system": "user",
}


def _build_contents(frame: ConversationFrame, new_message: str) -> list:
    contents = []
    for entry in frame.history:
        role = entry.get("role", "user")
        mapped = ROLE_MAP.get(role, "user")
        contents.append({"role": mapped, "parts": [{"text": entry.get("text", "")}]})
    contents.append({"role": "user", "parts": [{"text": new_message}]})
    return contents


def _call_gemini(contents: list) -> GeminiResult:
    last_error: GeminiResult | None = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={"contents": contents},
                timeout=30,
            )
        except requests.exceptions.ConnectionError:
            return GeminiResult(text="", error_code=503, error_message="Cannot reach Gemini API — check network connection")
        except requests.exceptions.Timeout:
            return GeminiResult(text="", error_code=504, error_message="Gemini API request timed out")
        except Exception as e:
            return GeminiResult(text="", error_code=500, error_message=f"Gemini API request failed: {str(e)}")

        if resp.ok:
            data = resp.json()
            usage = data.get("usageMetadata", {})
            return GeminiResult(
                text=data["candidates"][0]["content"]["parts"][0]["text"],
                prompt_tokens=usage.get("promptTokenCount", _estimate_tokens(str(contents))),
                candidates_tokens=usage.get("candidatesTokenCount", _estimate_tokens(str(data))),
                total_tokens=usage.get("totalTokenCount", 0),
            )

        if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
            delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning("Gemini 429 on attempt %d/%d — retrying in %.1fs", attempt + 1, MAX_RETRIES, delay)
            time.sleep(delay)
            last_error = GeminiResult(
                text="",
                error_code=429,
                error_message=f"Gemini API error 429: {resp.text[:300]}",
            )
            continue

        return GeminiResult(
            text="",
            error_code=resp.status_code,
            error_message=f"Gemini API error {resp.status_code}: {resp.text[:300]}",
        )

    return last_error or GeminiResult(
        text="",
        error_code=429,
        error_message="Gemini API rate limit exceeded after all retries",
    )


def chat(frame: ConversationFrame, message: str) -> GeminiResult:
    contents = _build_contents(frame, message)
    result = _call_gemini(contents)

    if result.error_code:
        return result

    frame.total_prompt_tokens += result.prompt_tokens
    frame.total_candidates_tokens += result.candidates_tokens
    frame.total_tokens += result.total_tokens
    frame.history.append({"role": "user", "text": message})
    frame.history.append({"role": "model", "text": result.text})

    return result


class StreamError(Exception):
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(msg)


SSE_PREFIX = "data: "


def _parse_sse_chunk(line: str) -> str | None:
    """Parse an SSE line from streamGenerateContent?alt=sse."""
    if not line.startswith(SSE_PREFIX):
        return None
    payload = line[len(SSE_PREFIX):].strip()
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    candidates = data.get("candidates", [])
    if candidates and candidates[0].get("content", {}).get("parts"):
        text = candidates[0]["content"]["parts"][0].get("text", "")
        return text if text else None
    return None


GEMINI_STREAM_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_VERSION}:streamGenerateContent"


def stream_chat(frame: ConversationFrame, message: str):
    """Stream from Gemini's SSE streaming endpoint, yielding incremental text chunks."""
    contents = _build_contents(frame, message)
    url = f"{GEMINI_STREAM_URL}?alt=sse&key={GEMINI_API_KEY}"
    last_error: str | None = None

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(url, json={"contents": contents}, stream=True, timeout=30)
        except requests.exceptions.ConnectionError:
            raise StreamError(503, "Cannot reach Gemini API — check network connection")
        except requests.exceptions.Timeout:
            raise StreamError(504, "Gemini API request timed out")
        except Exception as e:
            raise StreamError(500, f"Gemini API request failed: {str(e)}")

        if not resp.ok:
            if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning("Stream 429 on attempt %d/%d — retrying in %.1fs", attempt + 1, MAX_RETRIES, delay)
                time.sleep(delay)
                last_error = f"Gemini API error 429: {resp.text[:200]}"
                continue
            raise StreamError(resp.status_code, f"Gemini API error {resp.status_code}: {resp.text[:200]}")

        full_text = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            text = _parse_sse_chunk(line)
            if text is not None:
                full_text += text
                yield text

        if full_text:
            frame.history.append({"role": "user", "text": message})
            frame.history.append({"role": "model", "text": full_text})
        return

    raise StreamError(429, last_error or "Stream quota exhausted after retries")


def is_near_token_limit(frame: ConversationFrame) -> float:
    return token_usage_pct(frame) >= TOKEN_WARNING_THRESHOLD
