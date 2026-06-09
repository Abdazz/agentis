"""Voice endpoints: ASR transcription + TTS synthesis (Phase 4B)."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.voice_asr import transcribe_bytes
from app.services.voice_tts import synthesize_text

router = APIRouter(prefix="/voice", tags=["voice"])

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None


class TranscribeResponse(BaseModel):
    text: str
    language: str
    duration_seconds: float


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    _user: User = Depends(get_current_user),
) -> TranscribeResponse:
    data = await audio.read(_MAX_AUDIO_BYTES)
    try:
        result = transcribe_bytes(data)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return TranscribeResponse(**result)


@router.post("/synthesize")
async def synthesize(
    body: SynthesizeRequest,
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        audio_bytes = await synthesize_text(body.text, voice=body.voice)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return Response(content=audio_bytes, media_type="audio/mpeg")
