"""AgentState (working memory, spec §5.3) and Plan structures.

AgentState is checkpointed by PostgresSaver, so every value must be
JSON-serializable. The Plan is stored as a dict (Plan.model_dump())."""
from typing import Annotated, Any, Literal, Optional, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class SubTask(BaseModel):
    id: str
    description: str
    status: Literal["pending", "in_progress", "done", "failed"] = "pending"
    result: Optional[str] = None


class Plan(BaseModel):
    goal: str
    subtasks: list[SubTask] = Field(default_factory=list)


def new_plan(goal: str, descriptions: list[str]) -> Plan:
    return Plan(
        goal=goal,
        subtasks=[SubTask(id=f"s{i+1}", description=d) for i, d in enumerate(descriptions)],
    )


def mark_subtask_done(plan: Plan, subtask_id: str, result: str | None = None) -> Plan:
    for st in plan.subtasks:
        if st.id == subtask_id:
            st.status = "done"
            st.result = result
    return plan


class AgentState(TypedDict, total=False):
    task_id: str
    user_id: str
    goal: str
    language: str                              # "en" | "fr"
    plan: dict                                 # Plan.model_dump()
    messages: Annotated[list[BaseMessage], add_messages]
    scratchpad: str
    iteration: int
    max_iterations: int
    confidence: float
    allowed_tools: list[str]
    artifacts: list[dict[str, Any]]
    failures: int                              # total tool/LLM failures (BR-ORCH-34)
    hitl_pending: bool
    hitl_response: Optional[str]
    partial: bool                              # token budget hit (BR-ORCH-22)
    done: bool                                 # set by report node
