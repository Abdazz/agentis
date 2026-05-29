import pytest
from app.orchestrator.llm import build_llm


def test_build_llm_anthropic_returns_chat_model():
    llm = build_llm(provider="anthropic", model="claude-sonnet-4-5-20251022", api_key="sk-test")
    from langchain_anthropic import ChatAnthropic
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-5-20251022"
    assert llm.max_retries == 0


def test_build_llm_openai_returns_chat_model():
    llm = build_llm(provider="openai", model="gpt-4o", api_key="sk-test")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)


def test_build_llm_ollama_uses_base_url():
    llm = build_llm(provider="ollama", model="llama3", api_key="", base_url="http://ollama:11434/v1")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)


def test_build_llm_ollama_default_base_url():
    """Ollama with no explicit base_url must resolve to the default endpoint."""
    llm = build_llm(provider="ollama", model="llama3", api_key="")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == "http://ollama:11434/v1"


def test_build_llm_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        build_llm(provider="madeup", model="x", api_key="y")
