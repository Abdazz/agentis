"""LLM provider factory (Feature ORCH-1). Provider is config-only — no
provider-specific code outside this module (BR-ORCH-02)."""
from langchain_core.language_models.chat_models import BaseChatModel
from app.config import settings


def build_llm(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout_s: int | None = None,
) -> BaseChatModel:
    provider = (provider or settings.llm_provider).lower()
    model = model or settings.llm_model
    api_key = api_key if api_key is not None else settings.llm_api_key
    base_url = base_url if base_url is not None else settings.llm_base_url
    timeout_s = timeout_s if timeout_s is not None else settings.llm_timeout_s

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=api_key or None, timeout=timeout_s, max_retries=0)

    # OpenAI-compatible providers (openai, groq, deepseek, mistral, ollama)
    openai_compatible = {
        "openai": None,
        "groq": "https://api.groq.com/openai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "mistral": "https://api.mistral.ai/v1",
        "ollama": None,
    }
    if provider in openai_compatible:
        from langchain_openai import ChatOpenAI
        # Explicit base_url wins; ollama falls back to its default endpoint.
        resolved_base = base_url or openai_compatible[provider] or (
            "http://ollama:11434/v1" if provider == "ollama" else None
        )
        return ChatOpenAI(
            model=model,
            api_key=api_key or "not-needed",
            base_url=resolved_base,
            timeout=timeout_s,
            max_retries=0,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
