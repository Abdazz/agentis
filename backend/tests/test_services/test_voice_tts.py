import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.asyncio
async def test_synthesize_returns_audio_bytes():
    async def fake_stream():
        yield {"type": "audio", "data": b"chunk1"}
        yield {"type": "audio", "data": b"chunk2"}
        yield {"type": "WordBoundary", "data": b""}

    fake_communicate = MagicMock()
    fake_communicate.stream = fake_stream

    with patch("app.services.voice_tts._tts_available", True):
        with patch("app.services.voice_tts.Communicate", return_value=fake_communicate):
            from app.services.voice_tts import synthesize_text
            audio = await synthesize_text("Hello world")
    assert audio == b"chunk1chunk2"


@pytest.mark.asyncio
async def test_synthesize_raises_when_tts_missing():
    import app.services.voice_tts as m
    original = m._tts_available
    m._tts_available = False
    try:
        with pytest.raises(RuntimeError, match="edge-tts"):
            await m.synthesize_text("test")
    finally:
        m._tts_available = original
