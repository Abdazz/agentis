import pytest
from unittest.mock import patch, MagicMock


def test_transcribe_returns_text():
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (
        [MagicMock(text=" Hello world")],
        MagicMock(language="en", duration=2.5),
    )
    with patch("app.services.voice_asr._get_model", return_value=fake_model):
        from app.services.voice_asr import transcribe_bytes
        result = transcribe_bytes(b"\x00" * 100, language=None)
    assert result["text"] == "Hello world"
    assert result["language"] == "en"
    assert result["duration_seconds"] == 2.5


def test_transcribe_raises_when_faster_whisper_missing():
    import app.services.voice_asr as m
    original = m._whisper_available
    m._whisper_available = False
    m._model = None
    try:
        with pytest.raises(RuntimeError, match="faster-whisper"):
            m.transcribe_bytes(b"data")
    finally:
        m._whisper_available = original
