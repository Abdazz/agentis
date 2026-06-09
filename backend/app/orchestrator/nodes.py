"""LangGraph node functions for the ReAct loop (spec §5.2).

Runtime objects are read from config["configurable"]["run_ctx"] (ADR-1C-03)."""
import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from langchain_core.messages import (AIMessage, HumanMessage, SystemMessage,
                                     ToolMessage, BaseMessage)
from langchain_core.runnables import RunnableConfig
from app.config import settings
from app.models.task import TaskStepType
from app.tools.base import SessionContext
from app.tools.registry import tool_registry
from app.orchestrator.state import AgentState, Plan, new_plan
from app.orchestrator.context import (truncate_tool_output, count_message_tokens,
                                      needs_summarization, summarize_messages, model_window)
from app.orchestrator import prompts
from app.orchestrator.tools_adapter import build_tool_schemas
from app.memory.long_term import long_term_memory


@dataclass
class RunContext:
    llm: Any
    emitter: Any
    sandbox_endpoint: str
    user_id: str
    task_id: str
    allowed_tools: Optional[list[str]]
    memory_block: str = ""
    org_id: str | None = None
    org_monthly_budget: int | None = None


def _ctx(config: RunnableConfig) -> RunContext:
    return config["configurable"]["run_ctx"]


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from an LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    return {}


async def plan_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    goal = state["goal"]

    # Fetch relevant long-term memories (BR-MEM-21)
    try:
        lt_memories = await long_term_memory.search(user_id=ctx.user_id, query=goal, top_k=5)
        lt_block = ""
        if lt_memories:
            lt_block = "\n\nRELEVANT MEMORIES FROM PAST SESSIONS:\n" + "\n".join(
                f"- {m['summary']}: {m['content'][:200]}" for m in lt_memories
            )
    except Exception:
        lt_block = ""  # Memory failure must not block planning

    full_memory = (ctx.memory_block or "") + lt_block
    sys = prompts.system_with_language(prompts.PLAN_SYSTEM, state.get("language", "en"),
                                       full_memory)
    resp = await ctx.llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=goal)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        descriptions = _extract_json(content).get("subtasks", [])
    except (json.JSONDecodeError, ValueError):
        descriptions = []
    if not descriptions:
        descriptions = [goal]
    plan = new_plan(goal, descriptions)
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.plan_update, plan.model_dump(),
                           tokens_used=tokens, sse_type="plan_created")
    return {"plan": plan.model_dump(), "iteration": 0, "long_term_context": lt_block,
            "messages": [SystemMessage(content=sys), HumanMessage(content=goal)]}


async def think_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    schemas = build_tool_schemas(tool_registry, ctx.allowed_tools)
    sys = prompts.system_with_language(prompts.THINK_SYSTEM, state.get("language", "en"),
                                       ctx.memory_block)
    plan_msg = HumanMessage(content=f"Current plan: {json.dumps(state.get('plan', {}))}")
    current_msgs = list(state.get("messages", []))

    # ORCH-2: summarize when approaching context budget (BR-ORCH-12)
    total_tokens = count_message_tokens(current_msgs)
    model_name = getattr(ctx.llm, "model", settings.llm_model)
    tokens_freed = 0
    if needs_summarization(total_tokens, model_name, budget=settings.context_budget):
        current_msgs, tokens_freed = await summarize_messages(ctx.llm, current_msgs)
        await ctx.emitter.emit(TaskStepType.context_summarized, {"tokens_freed": tokens_freed})

    messages: list[BaseMessage] = [SystemMessage(content=sys), plan_msg] + current_msgs

    # Check token budgets before invoking LLM (BR-ORCH-20/21)
    from uuid import UUID as _UUID
    from sqlalchemy import select as _select, func as _func
    from app.database import AsyncSessionLocal
    from app.models.task import TaskStep as _TaskStep
    from app.orchestrator.budget import check_budgets
    estimated = count_message_tokens(messages)
    async with AsyncSessionLocal() as _db:
        task_tokens_so_far = (await _db.execute(
            _select(_func.coalesce(_func.sum(_TaskStep.tokens_used), 0))
            .where(_TaskStep.task_id == _UUID(ctx.task_id))
        )).scalar_one() or 0
        await check_budgets(
            _db,
            user_id=_UUID(ctx.user_id),
            task_tokens_so_far=task_tokens_so_far,
            estimated_next=estimated,
            org_id=_UUID(ctx.org_id) if ctx.org_id else None,
            org_monthly_budget=ctx.org_monthly_budget,
        )

    llm = ctx.llm.bind_tools(schemas) if schemas else ctx.llm
    resp = await llm.ainvoke(messages)
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.think,
                           {"content": resp.content if isinstance(resp.content, str) else str(resp.content),
                            "tokens": tokens},
                           tokens_used=tokens)
    new_msgs = current_msgs + [resp] if tokens_freed > 0 else [resp]
    return {"messages": new_msgs, "iteration": state.get("iteration", 0) + 1}


async def act_node(state: AgentState, config: RunnableConfig) -> dict:
    """Dispatch each tool call from the last AIMessage to the registry (ADR-1C-02)."""
    ctx = _ctx(config)
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", []) or []
    session = SessionContext(session_id=ctx.task_id, task_id=ctx.task_id,
                             sandbox_endpoint=ctx.sandbox_endpoint)
    tool_messages: list[BaseMessage] = []
    failures = state.get("failures", 0)
    for call in tool_calls:
        name, args, call_id = call["name"], call.get("args", {}), call["id"]
        tool = tool_registry.get(name)
        start = time.time()
        await ctx.emitter.emit(TaskStepType.tool_call, {"tool": name, "params": args, "call_id": call_id})
        if tool is None:
            result_text = f"Error: tool '{name}' is not available."
            failures += 1
        else:
            result = await tool.execute(args, session)
            duration = int((time.time() - start) * 1000)
            if result.ok:
                result_text = truncate_tool_output(json.dumps(result.data, default=str),
                                                    settings.tool_output_max_tokens)
            else:
                result_text = f"Error: {result.error}"
                failures += 1
            await ctx.emitter.emit(TaskStepType.tool_result,
                                   {"tool": name, "output": result.data if result.ok else result.error,
                                    "call_id": call_id, "ok": result.ok},
                                   duration_ms=duration)
        tool_messages.append(ToolMessage(content=result_text, tool_call_id=call_id))
    return {"messages": tool_messages, "failures": failures}


async def observe_node(state: AgentState, config: RunnableConfig) -> dict:
    """Normalize tool outputs into the scratchpad (spec §5.2 OBSERVE)."""
    recent = [m for m in state["messages"][-5:] if isinstance(m, ToolMessage)]
    additions = "\n".join(m.content for m in recent)
    scratchpad = (state.get("scratchpad", "") + "\n" + additions).strip()
    return {"scratchpad": scratchpad}


async def reflect_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    sys = prompts.REFLECT_SYSTEM
    context = (f"Goal: {state['goal']}\nPlan: {json.dumps(state.get('plan', {}))}\n"
               f"Latest observations:\n{state.get('scratchpad', '')[-2000:]}")
    resp = await ctx.llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=context)])
    content = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        parsed = _extract_json(content)
    except (json.JSONDecodeError, ValueError):
        parsed = {}
    confidence = float(parsed.get("confidence", 0.5))
    decision = parsed.get("decision", "continue")

    plan = Plan.model_validate(state.get("plan", {"goal": state["goal"], "subtasks": []}))
    for sid in parsed.get("completed_subtask_ids", []):
        for st in plan.subtasks:
            if st.id == sid:
                st.status = "done"
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.reflect,
                           {"confidence": confidence, "decision": decision,
                            "note": parsed.get("note", "")}, tokens_used=tokens)
    await ctx.emitter.emit(TaskStepType.plan_update, plan.model_dump(), sse_type="plan_updated")

    # Check if the last tool result requires HITL (BR-TASK-50)
    tool_messages = [m for m in state.get("messages", []) if hasattr(m, "tool_call_id")]
    if tool_messages:
        last_tool_content = getattr(tool_messages[-1], "content", "")
        hitl_required = False
        if isinstance(last_tool_content, str):
            try:
                hitl_required = bool(json.loads(last_tool_content).get("hitl_required"))
            except (json.JSONDecodeError, AttributeError):
                pass
        if hitl_required:
            import time
            timeout_at = time.time() + 600  # 10-minute HITL window
            await ctx.emitter.emit(
                TaskStepType.hitl_requested,
                {"task_id": ctx.task_id, "reason": "Tool requires human confirmation", "timeout_at": timeout_at},
            )
            return {
                "confidence": confidence,
                "plan": plan.model_dump(),
                "hitl_pending": True,
                "hitl_timeout_at": timeout_at,
                "_reflect_decision": "wait_hitl",
            }

    return {"confidence": confidence, "plan": plan.model_dump(),
            "_reflect_decision": decision}


async def report_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    sys = prompts.system_with_language(prompts.REPORT_SYSTEM, state.get("language", "en"))
    context = (f"Goal: {state['goal']}\nObservations:\n{state.get('scratchpad', '')[-4000:]}")
    if state.get("partial"):
        context += "\n\nNOTE: Token budget reached — produce a PARTIAL report of progress so far."
    resp = await ctx.llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=context)])
    summary = resp.content if isinstance(resp.content, str) else str(resp.content)
    tokens = count_message_tokens([resp])
    await ctx.emitter.emit(TaskStepType.report,
                           {"summary": summary, "artifacts": state.get("artifacts", [])},
                           tokens_used=tokens, sse_type="task_completed")

    # Persist task outcome to long-term memory (BR-MEM-20)
    if summary and ctx.user_id:
        try:
            await long_term_memory.store(
                user_id=ctx.user_id,
                task_id=ctx.task_id,
                content=summary[:1000],
                summary=state.get("goal", "")[:200],
                language=state.get("language", "fr"),
            )
        except Exception:
            pass  # Memory persistence must not block task completion

    return {"done": True, "result_summary": summary, "messages": [resp]}


def route_after_think(state: AgentState) -> str:
    if state.get("iteration", 0) >= state.get("max_iterations", settings.default_max_iterations):
        return "report"
    if state.get("failures", 0) >= settings.max_total_failures:
        return "report"
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "act"
    return "report"


def route_after_reflect(state: AgentState) -> str:
    if state.get("_reflect_decision") == "report":
        return "report"
    if state.get("_reflect_decision") == "wait_hitl":
        return "wait_hitl"
    if state.get("iteration", 0) >= state.get("max_iterations", settings.default_max_iterations):
        return "report"
    return "think"


async def wait_hitl_node(state: AgentState, config: RunnableConfig) -> dict:
    """Block orchestrator until user responds or timeout (BR-TASK-51)."""
    import time
    from app.services.hitl import hitl_coordinator
    ctx = _ctx(config)

    timeout_at = state.get("hitl_timeout_at") or (time.time() + 600)
    remaining = max(0.0, timeout_at - time.time())

    response = await hitl_coordinator.wait_for_response(
        task_id=ctx.task_id, timeout_seconds=remaining
    )

    if response is None:
        await ctx.emitter.emit(TaskStepType.reflect, {"note": "HITL timeout — proceeding to report"})
        return {
            "hitl_pending": False,
            "hitl_timeout_at": None,
            "_reflect_decision": "report",
        }

    await ctx.emitter.emit(TaskStepType.reflect, {"note": "HITL response received"})
    return {
        "hitl_pending": False,
        "hitl_timeout_at": None,
        "hitl_response": response,
        "_reflect_decision": "continue",
    }


def route_after_wait_hitl(state: AgentState) -> str:
    if state.get("_reflect_decision") == "report":
        return "report"
    return "think"
