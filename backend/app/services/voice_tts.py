"""edge-tts text-to-speech service (Phase 4B)."""
import structlog

log = structlog.get_logger()

try:
    from edge_tts import Communicate
    _tts_available = True
except ImportError:
    Communicate = None  # type: ignore
    _tts_available = False


async def synthesize_text(text: str, voice: str | None = None) -> bytes:
    """Convert text to MP3 audio bytes using edge-tts."""
    if not _tts_available:
        raise RuntimeError("edge-tts is not installed; cannot synthesize speech")
    from app.config import settings
    effective_voice = voice or settings.tts_voice
    communicate = Communicate(text, effective_voice)
    chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            chunks.append(chunk["data"])
    return b"".join(chunks)
