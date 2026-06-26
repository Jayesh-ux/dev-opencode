import base64
import mimetypes

import requests

from app.core import GEMINI_API_KEY, GEMINI_MODEL_VERSION

GEMINI_STT_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL_VERSION}:generateContent"


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "audio/webm"
    encoded = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": encoded,
                        }
                    },
                    {"text": "Transcribe the speech in this audio exactly. Return only the transcribed text."},
                ]
            }
        ]
    }

    try:
        resp = requests.post(
            f"{GEMINI_STT_URL}?key={GEMINI_API_KEY}",
            json=payload,
            timeout=60,
        )
    except requests.exceptions.ConnectionError:
        return "[STT: Cannot reach Gemini API — check network connection]"
    except requests.exceptions.Timeout:
        return "[STT: Gemini API request timed out]"
    except Exception as e:
        return f"[STT: Request failed: {str(e)}]"

    if resp.status_code == 429:
        return "[Quota exceeded — Gemini STT unavailable. Using browser-based SpeechRecognition as fallback.]"

    if not resp.ok:
        return f"[STT error {resp.status_code}]"

    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return "[STT: could not parse response]"
