# Phase 4B — Voice Interface (Whisper ASR + TTS)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users submit tasks by speaking (Whisper speech-to-text) and receive responses as synthesized speech (edge-tts text-to-speech), via two new backend endpoints.

**Architecture:** Two FastAPI endpoints — `POST /voice/transcribe` (multipart audio → text) and `POST /voice/synthesize` (JSON text → MP3 bytes). Both are optional/graceful: transcription returns an error if `faster-whisper` is not installed, synthesis uses `edge-tts` which calls Microsoft's free TTS service. Frontend integration is minimal (endpoints are called by JS on the task creation page).

**Tech Stack:** Python 3.12, FastAPI, `faster-whisper` (Whisper inference), `edge-tts` (TTS), pytest-asyncio

---

### Task 1: Voice service — Whisper ASR transcription

**Files:**
- Create: `backend/app/services/voice_asr.py`
- Modify: `backend/app/config.py` (add `whisper_model: str = "base"`, `whisper_device: str = "cpu"`)
- Test: `backend/tests/test_services/test_voice_asr.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_services/test_voice_asr.py
import pytest
from unittest.mock import patch, MagicMock


def test_transcribe_returns_text():
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (
        [MagicMock(text=" Hello world")],
        MagicMock(language="en"),
    )
    with patch("app.services.voice_asr._get_model", return_value=fake_model):
        from app.services.voice_asr import transcribe_bytes
        result = transcribe_bytes(b"\x00" * 100, language=None)
    assert result["text"] == "Hello world"
    assert result["language"] == "en"


def test_transcribe_raises_when_faster_whisper_missing():
    import sys
    with patch.dict("sys.modules", {"faster_whisper": None}):
        import importlib
        import app.services.voice_asr as m
        importlib.reload(m)
        with pytest.raises(RuntimeError, match="faster-whisper"):
            m.transcribe_bytes(b"data")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_services/test_voice_asr.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement voice_asr.py**

```python
# backend/app/services/voice_asr.py
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
```

- [ ] **Step 4: Add config fields**

In `backend/app/config.py`, add to the `Settings` class:

```python
whisper_model: str = "base"   # tiny, base, small, medium, large
whisper_device: str = "cpu"   # cpu or cuda
```

- [ ] **Step 5: Run test**

```bash
cd backend && python3 -m pytest tests/test_services/test_voice_asr.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/voice_asr.py backend/app/config.py backend/tests/test_services/test_voice_asr.py
git commit -m "feat(4b): Whisper ASR transcription service"
```

---

### Task 2: Voice service — edge-tts text-to-speech

**Files:**
- Create: `backend/app/services/voice_tts.py`
- Modify: `backend/app/config.py` (add `tts_voice: str = "en-US-AriaNeural"`)
- Test: `backend/tests/test_services/test_voice_tts.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_services/test_voice_tts.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_synthesize_returns_audio_bytes():
    fake_communicate = MagicMock()
    fake_communicate.stream = AsyncMock(return_value=aiter([
        {"type": "audio", "data": b"audio-chunk-1"},
        {"type": "audio", "data": b"audio-chunk-2"},
        {"type": "WordBoundary", "data": b""},
    ]))

    async def aiter(items):
        for item in items:
            yield item

    with patch("app.services.voice_tts.Communicate", return_value=fake_communicate):
        from app.services.voice_tts import synthesize_text
        audio = await synthesize_text("Hello world")
    assert audio == b"audio-chunk-1audio-chunk-2"


@pytest.mark.asyncio
async def test_synthesize_raises_when_edge_tts_missing():
    import sys
    with patch.dict("sys.modules", {"edge_tts": None}):
        import importlib
        import app.services.voice_tts as m
        importlib.reload(m)
        with pytest.raises(RuntimeError, match="edge-tts"):
            await m.synthesize_text("test")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python3 -m pytest tests/test_services/test_voice_tts.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement voice_tts.py**

```python
# backend/app/services/voice_tts.py
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
```

- [ ] **Step 4: Add config field**

In `backend/app/config.py`:

```python
tts_voice: str = "fr-FR-DeniseNeural"  # Default French voice to match AGENTIS_DEFAULT_LANGUAGE
```

- [ ] **Step 5: Run test**

```bash
cd backend && python3 -m pytest tests/test_services/test_voice_tts.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/voice_tts.py backend/app/config.py backend/tests/test_services/test_voice_tts.py
git commit -m "feat(4b): edge-tts text-to-speech service"
```

---

### Task 3: Voice router — `/voice/transcribe` and `/voice/synthesize` endpoints

**Files:**
- Create: `backend/app/routers/voice.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_routers/test_voice.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_routers/test_voice.py
import pytest
from unittest.mock import patch
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_transcribe_returns_text(async_client: AsyncClient, auth_headers: dict):
    with patch("app.routers.voice.transcribe_bytes",
               return_value={"text": "hello world", "language": "en", "duration_seconds": 2.5}):
        resp = await async_client.post(
            "/api/v1/voice/transcribe",
            headers=auth_headers,
            files={"audio": ("test.wav", b"\x00" * 100, "audio/wav")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "hello world"
    assert data["language"] == "en"


@pytest.mark.asyncio
async def test_transcribe_requires_auth(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("test.wav", b"\x00" * 100, "audio/wav")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_synthesize_returns_audio(async_client: AsyncClient, auth_headers: dict):
    with patch("app.routers.voice.synthesize_text", return_value=b"fake-mp3-bytes"):
        resp = await async_client.post(
            "/api/v1/voice/synthesize",
            json={"text": "Bonjour le monde"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == b"fake-mp3-bytes"


@pytest.mark.asyncio
async def test_synthesize_requires_auth(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/voice/synthesize",
        json={"text": "hello"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_transcribe_returns_503_when_whisper_unavailable(async_client: AsyncClient, auth_headers: dict):
    with patch("app.routers.voice.transcribe_bytes",
               side_effect=RuntimeError("faster-whisper is not installed")):
        resp = await async_client.post(
            "/api/v1/voice/transcribe",
            headers=auth_headers,
            files={"audio": ("test.wav", b"\x00" * 100, "audio/wav")},
        )
    assert resp.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python3 -m pytest tests/test_routers/test_voice.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement voice router**

```python
# backend/app/routers/voice.py
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
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, import and include:

```python
from app.routers.voice import router as voice_router
# ...
app.include_router(voice_router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests**

```bash
cd backend && python3 -m pytest tests/test_routers/test_voice.py -v
```
Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
cd backend && python3 -m pytest tests/ -x --tb=short -q 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/voice.py backend/app/main.py backend/tests/test_routers/test_voice.py
git commit -m "feat(4b): voice router — POST /voice/transcribe + /voice/synthesize"
```

---

### Task 4: Add faster-whisper and edge-tts to pyproject.toml

**Files:**
- Modify: `backend/pyproject.toml`
- Test: (implicit — existing import tests cover the graceful-degradation path)

- [ ] **Step 1: Check current optional deps**

```bash
grep -A5 "optional\|extras\|whisper\|tts" backend/pyproject.toml | head -20
```

- [ ] **Step 2: Add optional dependencies**

In `backend/pyproject.toml`, add to the `[project.optional-dependencies]` section (create it if absent):

```toml
[project.optional-dependencies]
voice = [
    "faster-whisper>=1.0.3",
    "edge-tts>=6.1.12",
]
```

If `[project.optional-dependencies]` already exists, append the `voice` key. Do NOT add these to the required deps — they are optional; the services degrade gracefully without them (RuntimeError caught at router level → HTTP 503).

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "feat(4b): add faster-whisper + edge-tts as optional voice dependencies"
```
