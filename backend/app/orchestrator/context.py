"""Context window management (Feature ORCH-2). Token counts use tiktoken
cl100k_base as a provider-agnostic approximation."""
import tiktoken
from langchain_core.messages import BaseMessage, SystemMessage

_ENCODER = tiktoken.get_encoding("cl100k_base")

MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet-4-5-20251022": 200_000,
    "claude": 200_000,
    "gpt-4o": 128_000,
    "llama3": 128_000,
    "deepseek": 64_000,
}
_DEFAULT_WINDOW = 128_000


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text))


def count_message_tokens(messages: list[BaseMessage]) -> int:
    total = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        total += count_tokens(content) + 4  # per-message overhead
    return total


def model_window(model: str) -> int:
    for key, window in MODEL_CONTEXT_WINDOWS.items():
        if key in model:
            return window
    return _DEFAULT_WINDOW


def needs_summarization(
    total_tokens: int, model: str, window_override: int | None = None, budget: float = 0.8
) -> bool:
    window = window_override if window_override is not None else model_window(model)
    return total_tokens > window * budget


def truncate_tool_output(output: str, max_tokens: int) -> str:
    tokens = _ENCODER.encode(output)
    if len(tokens) <= max_tokens:
        return output
    kept = _ENCODER.decode(tokens[:max_tokens])
    removed_chars = len(output) - len(kept)
    return f"{kept}\n[OUTPUT TRUNCATED — {removed_chars} characters removed. Full output available in task_steps.]"


async def summarize_messages(llm, messages: list[BaseMessage]) -> tuple[list[BaseMessage], int]:
    """Replace the oldest 50% of messages with one LLM summary SystemMessage
    (BR-ORCH-12). Returns (new_messages, tokens_freed)."""
    if len(messages) < 4:
        return messages, 0
    split = len(messages) // 2
    old, recent = messages[:split], messages[split:]
    freed = count_message_tokens(old)
    transcript = "\n".join(
        f"{m.__class__.__name__}: {m.content if isinstance(m.content, str) else str(m.content)}"
        for m in old
    )
    prompt = [
        SystemMessage(content="Summarize the following agent transcript into a concise summary "
                              "of key facts, decisions, and tool results. Preserve information "
                              "needed to continue the task."),
        SystemMessage(content=transcript),
    ]
    resp = await llm.ainvoke(prompt)
    summary = resp.content if isinstance(resp.content, str) else str(resp.content)
    new_messages = [SystemMessage(content=f"[SUMMARY OF EARLIER STEPS]\n{summary}")] + recent
    return new_messages, freed
