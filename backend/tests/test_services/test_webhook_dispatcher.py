import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch


def test_compute_signature_is_hmac_sha256():
    from app.services.webhook_dispatcher import compute_hmac_signature
    secret = "mysecret"
    payload = '{"event":"task_completed"}'
    sig = compute_hmac_signature(secret, payload)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


def test_compute_signature_different_secrets_differ():
    from app.services.webhook_dispatcher import compute_hmac_signature
    payload = '{"event":"task_completed"}'
    assert compute_hmac_signature("a", payload) != compute_hmac_signature("b", payload)


@pytest.mark.asyncio
async def test_dispatch_webhook_sends_post_with_signature():
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("app.services.webhook_dispatcher._validate_webhook_url"), \
         patch("app.services.webhook_dispatcher.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        from app.services.webhook_dispatcher import dispatch_webhook_request
        result = await dispatch_webhook_request(
            url="https://example.com/hook",
            secret="mysecret",
            payload={"event": "task_completed", "task_id": "t1"},
        )
        assert result is True
        call_kwargs = mock_client.post.call_args[1]
        assert "X-Agentis-Signature" in call_kwargs["headers"]


@pytest.mark.asyncio
async def test_dispatch_webhook_returns_false_on_non_2xx():
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("app.services.webhook_dispatcher._validate_webhook_url"), \
         patch("app.services.webhook_dispatcher.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        from app.services.webhook_dispatcher import dispatch_webhook_request
        result = await dispatch_webhook_request(
            url="https://example.com/hook",
            secret="mysecret",
            payload={"event": "task_completed"},
        )
        assert result is False
