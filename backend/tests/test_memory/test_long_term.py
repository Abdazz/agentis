import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


@pytest.fixture
def mock_qdrant_sync():
    client = MagicMock()
    client.collection_exists = MagicMock(return_value=False)
    client.create_collection = MagicMock()
    client.scroll = MagicMock(return_value=([], None))
    client.set_payload = MagicMock()
    client.delete = MagicMock()
    client.count = MagicMock(return_value=MagicMock(count=0))
    return client


@pytest.fixture
def mock_qdrant_async():
    client = AsyncMock()
    client.upsert = AsyncMock()
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_voyage():
    with patch("app.memory.long_term.voyageai") as m:
        client = MagicMock()
        client.embed = MagicMock(return_value=MagicMock(embeddings=[[0.1] * 1024]))
        m.Client.return_value = client
        yield m


def test_init_creates_collection_if_missing(mock_qdrant_sync, mock_qdrant_async, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant_sync), \
         patch("app.memory.long_term.AsyncQdrantClient", return_value=mock_qdrant_async):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        ltm.ensure_collection()
        mock_qdrant_sync.create_collection.assert_called_once()


def test_init_skips_creation_if_collection_exists(mock_qdrant_sync, mock_qdrant_async, mock_voyage, monkeypatch):
    mock_qdrant_sync.collection_exists.return_value = True
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant_sync), \
         patch("app.memory.long_term.AsyncQdrantClient", return_value=mock_qdrant_async):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        ltm.ensure_collection()
        mock_qdrant_sync.create_collection.assert_not_called()


@pytest.mark.asyncio
async def test_store_memory_upserts_to_qdrant(mock_qdrant_sync, mock_qdrant_async, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant_sync), \
         patch("app.memory.long_term.AsyncQdrantClient", return_value=mock_qdrant_async):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        point_id = await ltm.store(
            user_id=str(uuid4()),
            task_id=str(uuid4()),
            content="The user prefers concise answers.",
            summary="User communication style preference",
            tags=["preference"],
            language="fr",
        )
        assert point_id is not None
        mock_qdrant_async.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_search_returns_empty_list_on_no_results(mock_qdrant_sync, mock_qdrant_async, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    mock_qdrant_async.search.return_value = []
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant_sync), \
         patch("app.memory.long_term.AsyncQdrantClient", return_value=mock_qdrant_async):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        results = await ltm.search(user_id=str(uuid4()), query="user preferences", top_k=5)
        assert results == []


@pytest.mark.asyncio
async def test_search_filters_by_user_id(mock_qdrant_sync, mock_qdrant_async, mock_voyage, monkeypatch):
    monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
    mock_result = MagicMock()
    mock_result.payload = {"content": "User likes Python", "user_id": "u1", "summary": ""}
    mock_result.score = 0.95
    mock_qdrant_async.search.return_value = [mock_result]
    with patch("app.memory.long_term.QdrantClient", return_value=mock_qdrant_sync), \
         patch("app.memory.long_term.AsyncQdrantClient", return_value=mock_qdrant_async):
        from app.memory.long_term import LongTermMemory
        ltm = LongTermMemory()
        results = await ltm.search(user_id="u1", query="Python", top_k=5)
        assert len(results) == 1
        assert results[0]["content"] == "User likes Python"
        call_kwargs = mock_qdrant_async.search.call_args[1]
        assert call_kwargs.get("query_filter") is not None
