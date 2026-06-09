"""Whisper ASR transcription service (Phase 4B). Uses faster-whisper."""
import io
import structlog

log = structlog.get_logger()

try:
    from faster_whisper import WhisperModel
    _whisper_available = True
except ImportError:
    WhisperModel = None  # type: ignore
    _whisper_available = False

_model = None


def _get_model():
    global _model
    if not _whisper_available:
        raise RuntimeError("faster-whisper is not installed; cannot transcribe audio")
    if _model is None:
        from app.config import settings
        _model = WhisperModel(settings.whisper_model, device=settings.whisper_device)
    return _model


def transcribe_bytes(data: bytes, language: str | None = None) -> dict:
    """Transcribe raw audio bytes. Returns {text, language, duration_seconds}."""
    model = _get_model()
    audio_buf = io.BytesIO(data)
    kwargs = {}
    if language:
        kwargs["language"] = language
    segments, info = model.transcribe(audio_buf, **kwargs)
    text = "".join(seg.text for seg in segments).strip()
    return {
        "text": text,
        "language": info.language,
        "duration_seconds": round(info.duration, 2),
    }
