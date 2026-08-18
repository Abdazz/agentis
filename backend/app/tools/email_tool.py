"""EmailTool — operator-enabled, HITL required before send (spec §6.4, Phase 3B).

Uses generic IMAP (read/search) + SMTP (send) against the credentials the
user configured via POST /integrations (provider="email"). This runs in
the orchestrator process, not inside the sandbox — the sandbox's Squid
egress allowlist wouldn't include arbitrary mail hosts, and mail
protocols aren't HTTP anyway (see spec §7.5 — sandbox egress is proxied
HTTP/HTTPS only).

Expected credentials shape (see routers/integrations.py):
    {
      "username": "...", "password": "...",
      "imap_host": "...", "imap_port": 993,
      "smtp_host": "...", "smtp_port": 587, "smtp_use_ssl": false,
      "from_address": "..."  # optional, defaults to username
    }
"""
import asyncio
import email as email_lib
import email.utils
import imaplib
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from app.database import AsyncSessionLocal
from app.services.integration_credentials import (
    get_integration_credentials, IntegrationNotConfigured,
)
from app.tools.base import BaseTool, SessionContext, ToolResult

log = structlog.get_logger()

PROVIDER = "email"


async def _get_credentials(user_id: str) -> dict | None:
    async with AsyncSessionLocal() as db:
        return await get_integration_credentials(db, user_id, PROVIDER)


def _summarize_message(msg: email_lib.message.Message) -> dict:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return {
        "from": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "body": body[:5000],
    }


def _imap_fetch_sync(creds: dict, limit: int, search_criteria: str) -> list[dict]:
    conn = imaplib.IMAP4_SSL(creds["imap_host"], int(creds.get("imap_port", 993)), timeout=20)
    try:
        conn.login(creds["username"], creds["password"])
        conn.select("INBOX", readonly=True)
        status, data = conn.search(None, search_criteria)
        if status != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()
        if limit:
            ids = ids[-limit:]
        emails = []
        for msg_id in reversed(ids):
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            msg = email_lib.message_from_bytes(msg_data[0][1])
            emails.append(_summarize_message(msg))
        return emails
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            conn.logout()
        except Exception:
            pass


def _imap_criteria_for_search(query: str) -> str:
    # Minimal escaping — IMAP quoted strings can't contain a literal ".
    safe = query.replace('"', "'")
    return f'TEXT "{safe}"'


async def _fetch_inbox(session: SessionContext, limit: int, filter_str=None) -> list[dict]:
    creds = await _get_credentials(session.user_id)
    if creds is None:
        return []
    criteria = _imap_criteria_for_search(filter_str) if filter_str else "ALL"
    return await asyncio.get_event_loop().run_in_executor(
        None, _imap_fetch_sync, creds, limit, criteria
    )


async def _search_emails(session: SessionContext, query: str) -> list[dict]:
    creds = await _get_credentials(session.user_id)
    if creds is None:
        return []
    criteria = _imap_criteria_for_search(query)
    return await asyncio.get_event_loop().run_in_executor(
        None, _imap_fetch_sync, creds, 0, criteria
    )


def _smtp_send_sync(creds: dict, to: list[str], subject: str, body: str) -> dict:
    msg = MIMEMultipart()
    from_addr = creds.get("from_address") or creds["username"]
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg["Message-ID"] = email.utils.make_msgid()
    msg.attach(MIMEText(body, "plain"))

    host = creds.get("smtp_host") or creds.get("imap_host")
    port = int(creds.get("smtp_port", 587))
    use_ssl = creds.get("smtp_use_ssl", port == 465)

    server = smtplib.SMTP_SSL(host, port, timeout=20) if use_ssl else smtplib.SMTP(host, port, timeout=20)
    try:
        if not use_ssl:
            server.starttls()
        server.login(creds["username"], creds["password"])
        server.sendmail(from_addr, to, msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass

    return {"message_id": msg["Message-ID"]}


async def _send_email(
    session: SessionContext, to: list[str], subject: str, body: str, attachments=None
) -> dict:
    creds = await _get_credentials(session.user_id)
    if creds is None:
        return {"error": "No email integration configured for this user"}
    if attachments:
        log.warning("email_send_attachments_not_supported", task_id=session.task_id)
    return await asyncio.get_event_loop().run_in_executor(
        None, _smtp_send_sync, creds, to, subject, body
    )


class EmailTool(BaseTool):
    name = "email"
    description = (
        "Send, read, and search emails via the user's configured email account "
        "(IMAP/SMTP — configured under Settings > Integrations). "
        "Requires HITL confirmation before sending. Operator must enable this tool. "
        "Attachments are not yet supported on send."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["send", "read_inbox", "search"]},
            "to": {"type": "array", "items": {"type": "string"}},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 20},
            "filter": {"type": "string"},
            "query": {"type": "string"},
            "hitl_approved": {"type": "boolean", "default": False},
        },
        "required": ["action"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        action = params.get("action", "")
        hitl_approved = params.get("hitl_approved", False)

        if action == "send":
            if not hitl_approved:
                return ToolResult(
                    ok=False,
                    error="HITL required: email.send requires human confirmation before execution.",
                    data={
                        "hitl_required": True,
                        "action": "send",
                        "to": params.get("to"),
                        "subject": params.get("subject"),
                    },
                )
            try:
                data = await _send_email(
                    session,
                    to=params.get("to", []),
                    subject=params.get("subject", ""),
                    body=params.get("body", ""),
                    attachments=params.get("attachments"),
                )
            except (imaplib.IMAP4.error, smtplib.SMTPException, OSError, IntegrationNotConfigured) as e:
                return ToolResult(ok=False, error=f"Failed to send email: {e}", retryable=True)
            if "error" in data:
                return ToolResult(ok=False, error=data["error"])
            return ToolResult(ok=True, data=data)

        elif action == "read_inbox":
            try:
                emails = await _fetch_inbox(
                    session, limit=params.get("limit", 20), filter_str=params.get("filter")
                )
            except (imaplib.IMAP4.error, OSError, IntegrationNotConfigured) as e:
                return ToolResult(ok=False, error=f"Failed to read inbox: {e}", retryable=True)
            return ToolResult(ok=True, data={"emails": emails})

        elif action == "search":
            try:
                emails = await _search_emails(session, query=params.get("query", ""))
            except (imaplib.IMAP4.error, OSError, IntegrationNotConfigured) as e:
                return ToolResult(ok=False, error=f"Failed to search emails: {e}", retryable=True)
            return ToolResult(ok=True, data={"emails": emails})

        else:
            return ToolResult(ok=False, error=f"Unknown action: {action!r}")
