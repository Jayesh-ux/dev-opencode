import io

from gtts import gTTS


def text_to_speech_mp3(text: str) -> bytes:
    if not text.strip():
        return b""

    tts = gTTS(text=text, lang="en", slow=False)
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()
