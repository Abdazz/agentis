"""Encrypt/decrypt and look up user integration credentials (UserIntegration).
Shared by routers/integrations.py (CRUD) and the email/calendar tools
(read-only lookup at execution time) so there's one Fernet code path.

Per spec: "Secrets for tool execution ... are fetched from Vault at call
time — never stored in AgentState or task_steps." This implementation
uses Fernet-encrypted-at-rest storage in Postgres rather than Vault
(Vault integration for tool secrets remains a Phase 3B follow-up per the
original plan docs), but preserves the same guarantee: credentials are
looked up fresh per tool call and never placed in AgentState/task_steps.
"""
import json
from cryptography.fernet import Fernet
from sqlalchemy import select
from app.config import settings
from app.models.user_integration import UserIntegration


class IntegrationNotConfigured(Exception):
    """Raised when AGENTIS_FERNET_KEY isn't set, so encrypted credential
    storage can't be used at all."""


def _fernet() -> Fernet:
    if not settings.fernet_key:
        raise IntegrationNotConfigured("AGENTIS_FERNET_KEY is not configured")
    return Fernet(settings.fernet_key.encode())


def encrypt_credentials(credentials: dict) -> str:
    return _fernet().encrypt(json.dumps(credentials).encode()).decode()


def decrypt_credentials(encrypted: str) -> dict:
    return json.loads(_fernet().decrypt(encrypted.encode()).decode())


async def get_integration_credentials(db, user_id: str, provider: str) -> dict | None:
    """Look up the user's active credentials for a given integration
    provider (e.g. "email", "caldav"). Returns None if the user hasn't
    configured one — callers should treat that as "tool unavailable",
    not raise. Raises IntegrationNotConfigured if Fernet isn't set up
    at all (an operator misconfiguration, not a per-user state)."""
    if not user_id:
        return None
    result = await db.execute(
        select(UserIntegration).where(
            UserIntegration.user_id == user_id,
            UserIntegration.provider == provider,
            UserIntegration.is_active == True,  # noqa: E712
        )
    )
    integ = result.scalar_one_or_none()
    if integ is None:
        return None
    return decrypt_credentials(integ.credentials_encrypted)
