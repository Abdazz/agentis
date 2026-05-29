import uuid
import json
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from app.database import AsyncSessionLocal
from app.models.user import User
from app.auth.password import hash_password
from app.repositories import task as task_repo
from app.orchestrator.events import EventEmitter
from app.orchestrator.nodes import (
    plan_node, reflect_node, report_node, route_after_think, route_after_reflect, RunContext,
)
from app.orchestrator.state import AgentState


@pytest.fixture
async def ctx():
    async with AsyncSessionLocal() as db:
        u = User(email=f"node-{uuid.uuid4()}@t.com", password_hash=hash_password("x"))
        db.add(u)
        await db.flush()
        t = await task_repo.create_task(db, user_id=u.id, goal="g", language="en",
                                        max_iterations=30, allowed_tools=None)
        await db.commit()
        uid, tid = u.id, t.id
    emitter = EventEmitter(tid)
    rc = RunContext(llm=None, emitter=emitter, sandbox_endpoint="", user_id=str(uid),
                    task_id=str(tid), allowed_tools=None)
    yield rc
    await emitter.close()


def _config(rc):
    return {"configurable": {"run_ctx": rc}}


async def test_plan_node_builds_plan_from_llm_json(ctx):
    ctx.llm = GenericFakeChatModel(messages=iter([
        AIMessage(content=json.dumps({"subtasks": ["search the web", "write summary"]})),
    ]))
    state: AgentState = {"task_id": ctx.task_id, "user_id": ctx.user_id, "goal": "g",
                         "language": "en", "messages": [], "iteration": 0}
    out = await plan_node(state, _config(ctx))
    assert len(out["plan"]["subtasks"]) == 2
    assert out["plan"]["subtasks"][0]["description"] == "search the web"


async def test_route_after_think_to_act_when_tool_calls():
    msg = AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "x"}, "id": "c1"}])
    state = {"messages": [msg], "iteration": 1, "max_iterations": 30, "failures": 0}
    assert route_after_think(state) == "act"


async def test_route_after_think_to_report_when_no_tool_calls():
    state = {"messages": [AIMessage(content="final answer")], "iteration": 1,
             "max_iterations": 30, "failures": 0}
    assert route_after_think(state) == "report"


async def test_route_after_think_to_report_when_max_iterations():
    msg = AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "c1"}])
    state = {"messages": [msg], "iteration": 30, "max_iterations": 30, "failures": 0}
    assert route_after_think(state) == "report"


async def test_reflect_node_parses_confidence_and_decision(ctx):
    ctx.llm = GenericFakeChatModel(messages=iter([
        AIMessage(content=json.dumps({"confidence": 0.9, "decision": "report",
                                      "completed_subtask_ids": [], "note": "done"})),
    ]))
    state: AgentState = {"task_id": ctx.task_id, "user_id": ctx.user_id, "goal": "g",
                         "language": "en", "messages": [HumanMessage(content="obs")],
                         "plan": {"goal": "g", "subtasks": []}, "iteration": 1}
    out = await reflect_node(state, _config(ctx))
    assert out["confidence"] == 0.9
    assert route_after_reflect({**state, **out}) == "report"


async def test_report_node_sets_done_and_summary(ctx):
    ctx.llm = GenericFakeChatModel(messages=iter([AIMessage(content="All done. Report ready.")]))
    state: AgentState = {"task_id": ctx.task_id, "user_id": ctx.user_id, "goal": "g",
                         "language": "en", "messages": [HumanMessage(content="obs")],
                         "plan": {"goal": "g", "subtasks": []}, "iteration": 2}
    out = await report_node(state, _config(ctx))
    assert out["done"] is True
    assert "result_summary" in out
