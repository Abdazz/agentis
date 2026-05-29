from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.orchestrator.context import (
    count_tokens,
    count_message_tokens,
    model_window,
    needs_summarization,
    truncate_tool_output,
)


def test_count_tokens_nonzero_for_text():
    assert count_tokens("hello world this is a test") > 0


def test_count_message_tokens_sums_messages():
    msgs = [HumanMessage(content="hi"), AIMessage(content="hello there friend")]
    assert count_message_tokens(msgs) > 0


def test_model_window_known_and_default():
    assert model_window("claude-sonnet-4-5-20251022") == 200_000
    assert model_window("gpt-4o") == 128_000
    assert model_window("some-unknown-model") == 128_000  # safe default


def test_needs_summarization_true_when_over_budget():
    # window 100, budget 0.8 → threshold 80; 90 tokens exceeds
    assert needs_summarization(total_tokens=90, model="x", window_override=100, budget=0.8) is True
    assert needs_summarization(total_tokens=50, model="x", window_override=100, budget=0.8) is False


def test_truncate_tool_output_appends_note_when_over_limit():
    big = "x" * 100_000
    out = truncate_tool_output(big, max_tokens=10)
    assert "OUTPUT TRUNCATED" in out
    assert len(out) < len(big)


def test_truncate_tool_output_passthrough_when_small():
    assert truncate_tool_output("short", max_tokens=1000) == "short"
