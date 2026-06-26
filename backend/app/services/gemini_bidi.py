import asyncio
import json
import logging
import time

import websockets

from app.core import GEMINI_API_KEY, GEMINI_LIVE_MODEL_VERSION
from app.services.gemini import chat as gemini_chat, stream_chat
from app.services.types import ConversationFrame, GeminiResult

logger = logging.getLogger(__name__)

LIVE_WS_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"


class LiveSessionError(Exception):
    pass


class RateLimitError(LiveSessionError):
    pass


class LiveSession:
    def __init__(self):
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._connected = False
        self._last_send_ts: float | None = None
        self._latency_total = 0.0
        self._turn_count = 0

    async def connect(self, voice: str = "Puck") -> bool:
        uri = f"{LIVE_WS_URL}?key={GEMINI_API_KEY}"
        try:
            self._ws = await websockets.connect(uri)
            setup = {
                "setup": {
                    "model": f"models/{GEMINI_LIVE_MODEL_VERSION}",
                    "generation_config": {
                        "response_modalities": ["AUDIO"],
                        "speech_config": {
                            "voice_config": {
                                "prebuilt_voice_config": {
                                    "voice_name": voice,
                                }
                            }
                        }
                    },
                }
            }
            await self._ws.send(json.dumps(setup))
            resp = json.loads(await self._ws.recv())
            if "setup_complete" not in resp:
                logger.error("Live setup failed: %s", resp)
                await self._ws.close()
                self._ws = None
                return False
            self._connected = True
            logger.info("LiveSession connected (voice=%s)", voice)
            return True
        except websockets.exceptions.InvalidStatus as e:
            if e.response and e.response.status_code == 429:
                logger.error("LiveSession rate limited (429) on connect")
            else:
                logger.error("LiveSession connect HTTP error: %s", e)
            if self._ws:
                await self._ws.close()
                self._ws = None
            return False
        except Exception as e:
            logger.error("LiveSession connect failed: %s", e)
            if self._ws:
                await self._ws.close()
                self._ws = None
            return False

    async def send_audio(self, audio_base64: str, mime_type: str = "audio/pcm"):
        if not self._connected or not self._ws:
            return
        msg = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "mime_type": mime_type,
                        "data": audio_base64,
                    }
                ]
            }
        }
        try:
            self._last_send_ts = time.monotonic()
            await self._ws.send(json.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            logger.warning("send_audio dropped: connection closed")
        except Exception as e:
            self._connected = False
            logger.error("send_audio error: %s", e)

    async def send_text(self, text: str):
        if not self._connected or not self._ws:
            return
        msg = {
            "client_content": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [{"text": text}],
                    }
                ],
                "turn_complete": True,
            }
        }
        try:
            self._last_send_ts = time.monotonic()
            await self._ws.send(json.dumps(msg))
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            logger.warning("send_text dropped: connection closed")
        except Exception as e:
            self._connected = False
            logger.error("send_text error: %s", e)

    async def receive(self) -> dict | None:
        if not self._connected or not self._ws:
            return None
        try:
            raw = await self._ws.recv()
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
            return None
        except Exception as e:
            self._connected = False
            logger.error("receive websocket error: %s", e)
            return {"type": "error", "code": "CONNECTION_LOST", "detail": str(e)}

        try:
            resp = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("receive malformed JSON: %s", raw[:200])
            return {"type": "error", "code": "MALFORMED_RESPONSE", "detail": raw[:200]}

        if "error" in resp:
            err = resp["error"]
            code = err.get("code", 0)
            message = err.get("message", "unknown error")
            status = err.get("status", "UNKNOWN")
            logger.error("Gemini API error: [%s] %s (code=%s)", status, message, code)
            if code == 429 or "rate" in message.lower():
                return {"type": "error", "code": "RATE_LIMIT_EXCEEDED", "detail": message}
            return {"type": "error", "code": "API_ERROR", "detail": f"{status}: {message}"}

        result: dict = {}

        if "setup_complete" in resp:
            result["type"] = "setup_complete"
        elif "server_content" in resp:
            sc = resp["server_content"]
            result["interrupted"] = sc.get("interrupted", False)
            result["turn_complete"] = sc.get("turn_complete", False)
            model_turn = sc.get("model_turn", {})
            for part in model_turn.get("parts", []):
                if "inline_data" in part:
                    result["audio"] = part["inline_data"]["data"]
                if "text" in part:
                    existing = result.get("text", "")
                    result["text"] = existing + part["text"]
            if result.get("turn_complete") and self._last_send_ts is not None:
                latency = time.monotonic() - self._last_send_ts
                self._latency_total += latency
                self._turn_count += 1
                avg = self._latency_total / self._turn_count
                logger.info("turn latency=%.2fs avg=%.2fs turns=%d", latency, avg, self._turn_count)
                self._last_send_ts = None
        elif "tool_call" in resp:
            result["tool_call"] = resp["tool_call"]

        return result

    @property
    def connected(self) -> bool:
        return self._connected

    async def disconnect(self):
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None


class GeminiStreamInterrupt(Exception):
    pass


class ResearchSession:
    def __init__(self):
        self.frame = ConversationFrame()
        self._connected = True

    async def connect(self) -> bool:
        return True

    async def send_text(self, text: str):
        pass

    async def send_audio(self, audio_base64: str, mime_type: str = "audio/pcm;rate=16000"):
        pass

    async def send_frame(self, frame_base64: str, mime_type: str = "image/jpeg"):
        pass

    async def receive(self) -> dict | None:
        return None

    async def disconnect(self):
        pass

    def process_text(self, message: str) -> GeminiResult:
        return gemini_chat(self.frame, message)

    def process_text_stream(self, message: str):
        yield from stream_chat(self.frame, message)


async def create_bidi_client() -> ResearchSession:
    return ResearchSession()


async def create_live_client(voice: str = "Puck") -> LiveSession:
    session = LiveSession()
    ok = await session.connect(voice)
    if not ok:
        raise RuntimeError("Failed to connect LiveSession")
    return session
