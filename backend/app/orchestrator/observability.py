"""Langfuse integration (spec §12). No-op when Langfuse is not configured."""
import structlog
from app.config import settings

log = structlog.get_logger()


def get_langfuse_callbacks() -> list:
    """Return a list of LangChain callback handlers for LLM tracing.
    Empty list when Langfuse keys are absent (dev default)."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return []
    try:
        from langfuse.callback import CallbackHandler
        return [CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or "http://langfuse:3000",
        )]
    except Exception as e:
        log.warning("langfuse_init_failed", error=str(e))
        return []
