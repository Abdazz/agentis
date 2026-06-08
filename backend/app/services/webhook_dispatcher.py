"""Webhook dispatcher with HMAC-SHA256 signing + retry (spec §15 WH-1..5)."""
import hmac
import hashlib
import ipaddress
import json
import asyncio
import socket
from urllib.parse import urlparse
import httpx
from app.config import settings
from app.worker.celery_app import celery_app

# RFC 1918 + loopback + link-local + APIPA + metadata services
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _validate_webhook_url(url: str) -> None:
    """Raise ValueError if the URL targets an internal/private IP (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not contain credentials")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL must have a hostname")
    # Resolve all IPs for the hostname
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve webhook hostname: {hostname}")
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(f"Webhook URL resolves to a private/internal address: {ip_str}")


def compute_hmac_signature(secret: str, payload_str: str) -> str:
    return hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()


def decrypt_secret(encrypted: str) -> str:
    from cryptography.fernet import Fernet
    f = Fernet(settings.fernet_key.encode())
    return f.decrypt(encrypted.encode()).decode()


async def dispatch_webhook_request(url: str, secret: str, payload: dict) -> bool:
    """Send a single webhook POST. Returns True on 2xx, False otherwise."""
    _validate_webhook_url(url)  # SSRF guard — raises ValueError for internal URLs
    payload_str = json.dumps(payload, separators=(",", ":"))
    sig = compute_hmac_signature(secret, payload_str)
    headers = {
        "Content-Type": "application/json",
        "X-Agentis-Signature": f"sha256={sig}",
        "User-Agent": "Agentis-Webhook/1.0",
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        resp = await client.post(url, content=payload_str, headers=headers)
        return 200 <= resp.status_code < 300


@celery_app.task(name="webhooks.dispatch", bind=True, max_retries=5)
def dispatch_webhook_task(self, webhook_id: str, event: str, payload: dict):
    """Celery task: send webhook with exponential backoff on failure."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.models.webhook import UserWebhook
        import uuid as uuid_lib
        async with AsyncSessionLocal() as session:
            wh = await session.get(UserWebhook, uuid_lib.UUID(webhook_id))
            if not wh or not wh.is_active:
                return
            secret = decrypt_secret(wh.secret_encrypted)
            success = await dispatch_webhook_request(url=wh.url, secret=secret, payload=payload)
            if not success:
                delay = (2 ** self.request.retries) * 30
                raise self.retry(countdown=delay)

    asyncio.run(_run())
