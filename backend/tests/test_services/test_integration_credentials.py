import pytest
from unittest.mock import MagicMock
from app.services.integration_credentials import (
    encrypt_credentials, decrypt_credentials, get_integration_credentials,
    IntegrationNotConfigured,
)

TEST_KEY = "u7u2ST4mr6Iv_fzEme_7z8azemhvgJP63GQg5O9Q4Bk="  # test-only Fernet key


def test_encrypt_decrypt_roundtrip(monkeypatch):
    from app import config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)

    encrypted = encrypt_credentials({"username": "me", "password": "secret"})
    assert encrypted != "secret"
    decrypted = decrypt_credentials(encrypted)
    assert decrypted == {"username": "me", "password": "secret"}


def test_encrypt_raises_when_fernet_key_missing(monkeypatch):
    from app import config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", "")

    with pytest.raises(IntegrationNotConfigured):
        encrypt_credentials({"a": "b"})


@pytest.mark.asyncio
async def test_get_integration_credentials_returns_none_for_empty_user_id():
    result = await get_integration_credentials(MagicMock(), "", "email")
    assert result is None


@pytest.mark.asyncio
async def test_get_integration_credentials_returns_none_when_not_found():
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    async def _execute(*a, **kw):
        return mock_result
    mock_db.execute = _execute

    result = await get_integration_credentials(mock_db, "user-1", "email")
    assert result is None


@pytest.mark.asyncio
async def test_get_integration_credentials_decrypts_found_row(monkeypatch):
    from app import config as app_config
    monkeypatch.setattr(app_config.settings, "fernet_key", TEST_KEY)

    encrypted = encrypt_credentials({"username": "me@x.com", "password": "pw"})
    mock_integ = MagicMock()
    mock_integ.credentials_encrypted = encrypted

    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_integ

    async def _execute(*a, **kw):
        return mock_result
    mock_db.execute = _execute

    result = await get_integration_credentials(mock_db, "user-1", "email")
    assert result == {"username": "me@x.com", "password": "pw"}
