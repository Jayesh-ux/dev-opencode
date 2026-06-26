from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from app.services.stt import transcribe_audio
from app.services.tts import text_to_speech_mp3

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/stt")
async def speech_to_text(
    file: UploadFile = File(...),
):
    if not file.filename:
        return {"transcript": "[No audio file received]"}
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            return {"transcript": "[Empty audio recording]"}
        transcript = transcribe_audio(audio_bytes, filename=file.filename or "audio.webm")
        return {"transcript": transcript}
    except Exception as e:
        return {"transcript": f"[STT processing error: {str(e)}]"}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not file.filename:
        return {"transcript": "[No audio file received]"}
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            return {"transcript": "[Empty audio recording]"}
        transcript = transcribe_audio(audio_bytes, filename=file.filename or "audio.webm")
        return {"transcript": transcript}
    except Exception as e:
        return {"transcript": f"[STT processing error: {str(e)}]"}


@router.post("/tts")
async def text_to_speech(text: str = Form(...)):
    if not text.strip():
        return Response(
            content=b"",
            media_type="audio/mpeg",
            status_code=400,
        )
    try:
        mp3_bytes = text_to_speech_mp3(text)
        return Response(
            content=mp3_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=response.mp3"},
        )
    except Exception as e:
        return Response(
            content=b"",
            media_type="audio/mpeg",
            status_code=500,
            headers={"X-Error": str(e)},
        )
