import pytest
from datetime import timedelta
from app.auth.jwt import create_access_token, decode_access_token, TokenExpiredError, TokenInvalidError


def test_create_and_decode_token():
    token = create_access_token(user_id="abc-123", role="user")
    payload = decode_access_token(token)
    assert payload["sub"] == "abc-123"
    assert payload["role"] == "user"


def test_token_contains_exp_iat():
    token = create_access_token(user_id="abc", role="user")
    payload = decode_access_token(token)
    assert "exp" in payload
    assert "iat" in payload


def test_expired_token_raises():
    token = create_access_token(user_id="abc", role="user", ttl=timedelta(seconds=-1))
    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_tampered_token_raises():
    token = create_access_token(user_id="abc", role="user")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(TokenInvalidError):
        decode_access_token(tampered)


def test_org_id_in_token():
    token = create_access_token(user_id="abc", role="admin", org_id="org-1")
    payload = decode_access_token(token)
    assert payload["org_id"] == "org-1"
