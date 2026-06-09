"""Tests for Voyage AI self-hosted base_url config option (Phase 3B Task 6)."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


def test_voyage_base_url_config_default_empty():
    """voyage_base_url should default to empty string."""
    from app.config import Settings
    s = Settings()
    assert s.voyage_base_url == ""


def test_voyage_base_url_config_from_env(monkeypatch):
    """voyage_base_url should be populated from AGENTIS_VOYAGE_BASE_URL env var."""
    monkeypatch.setenv("AGENTIS_VOYAGE_BASE_URL", "http://voyage:8080/v1")
    from app.config import Settings
    s = Settings()
    assert s.voyage_base_url == "http://voyage:8080/v1"


def test_voyage_client_initialized_with_base_url(monkeypatch):
    """LongTermMemory should pass base_url to voyageai.Client if voyage_base_url is set."""
    monkeypatch.setenv("AGENTIS_VOYAGE_BASE_URL", "http://voyage:8080/v1")

    with patch("app.memory.long_term.voyageai") as mock_voyageai:
        mock_client = MagicMock()
        mock_voyageai.Client.return_value = mock_client

        # Force settings to reload with the new env var
        monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
        monkeypatch.setattr("app.memory.long_term.settings.voyage_base_url", "http://voyage:8080/v1")

        with patch("app.memory.long_term.QdrantClient"):
            with patch("app.memory.long_term.AsyncQdrantClient"):
                from app.memory.long_term import LongTermMemory
                ltm = LongTermMemory()

                # Verify that voyageai.Client was called with base_url parameter
                call_kwargs = mock_voyageai.Client.call_args[1]
                assert "base_url" in call_kwargs
                assert call_kwargs["base_url"] == "http://voyage:8080/v1"


def test_voyage_client_without_base_url_when_empty(monkeypatch):
    """LongTermMemory should not pass base_url if voyage_base_url is empty."""
    with patch("app.memory.long_term.voyageai") as mock_voyageai:
        mock_client = MagicMock()
        mock_voyageai.Client.return_value = mock_client

        monkeypatch.setattr("app.memory.long_term.settings.voyage_api_key", "test-key")
        monkeypatch.setattr("app.memory.long_term.settings.voyage_base_url", "")

        with patch("app.memory.long_term.QdrantClient"):
            with patch("app.memory.long_term.AsyncQdrantClient"):
                from app.memory.long_term import LongTermMemory
                ltm = LongTermMemory()

                # Verify that voyageai.Client was NOT called with base_url parameter
                call_kwargs = mock_voyageai.Client.call_args[1]
                assert "base_url" not in call_kwargs
