import pytest
from app.orchestrator.llm import build_llm


def test_build_llm_anthropic_returns_chat_model():
    llm = build_llm(provider="anthropic", model="claude-sonnet-4-5-20251022", api_key="sk-test")
    from langchain_anthropic import ChatAnthropic
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-5-20251022"


def test_build_llm_openai_returns_chat_model():
    llm = build_llm(provider="openai", model="gpt-4o", api_key="sk-test")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)


def test_build_llm_ollama_uses_base_url():
    llm = build_llm(provider="ollama", model="llama3", api_key="", base_url="http://ollama:11434/v1")
    from langchain_openai import ChatOpenAI
    assert isinstance(llm, ChatOpenAI)


def test_build_llm_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        build_llm(provider="madeup", model="x", api_key="y")
