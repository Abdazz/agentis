"""LangGraph StateGraph assembly + checkpointer (spec §5.2, ADR-1C-01)."""
from contextlib import asynccontextmanager
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from app.config import settings
from app.orchestrator.state import AgentState
from app.orchestrator import nodes


def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    graph.add_node("plan", nodes.plan_node)
    graph.add_node("think", nodes.think_node)
    graph.add_node("act", nodes.act_node)
    graph.add_node("observe", nodes.observe_node)
    graph.add_node("reflect", nodes.reflect_node)
    graph.add_node("report", nodes.report_node)
    graph.add_node("wait_hitl", nodes.wait_hitl_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "think")
    graph.add_conditional_edges("think", nodes.route_after_think,
                                {"act": "act", "report": "report"})
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "reflect")
    graph.add_conditional_edges("reflect", nodes.route_after_reflect,
                                {"think": "think", "report": "report", "wait_hitl": "wait_hitl"})
    graph.add_conditional_edges("wait_hitl", nodes.route_after_wait_hitl,
                                {"think": "think", "report": "report"})
    graph.add_edge("report", END)
    return graph.compile(checkpointer=checkpointer)


@asynccontextmanager
async def checkpointer_context():
    """Yield an AsyncPostgresSaver backed by a direct-Postgres pool (ADR-1C-01)."""
    async with AsyncConnectionPool(
        conninfo=settings.checkpointer_dsn,
        max_size=4,
        kwargs={"autocommit": True, "prepare_threshold": None},
        open=False,
    ) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield checkpointer
