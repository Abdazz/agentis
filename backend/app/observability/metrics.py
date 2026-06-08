"""Prometheus metrics registry (spec §17 OBS-1)."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from fastapi.responses import Response

tasks_created_total = Counter("agentis_tasks_created_total", "Tasks created", ["status"])
tool_calls_total = Counter("agentis_tool_calls_total", "Tool calls", ["tool_name", "success"])
llm_tokens_total = Counter("agentis_llm_tokens_total", "LLM tokens consumed", ["provider", "model"])
hitl_requests_total = Counter("agentis_hitl_requests_total", "HITL requests triggered")
hitl_responses_total = Counter("agentis_hitl_responses_total", "HITL responses received", ["outcome"])

task_duration_seconds = Histogram(
    "agentis_task_duration_seconds", "Task completion time",
    buckets=[5, 15, 30, 60, 120, 300, 600, 1800]
)
tool_duration_seconds = Histogram(
    "agentis_tool_duration_seconds", "Tool call duration", ["tool_name"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60]
)

active_tasks_gauge = Gauge("agentis_active_tasks", "Currently running tasks")
sandbox_sessions_gauge = Gauge("agentis_sandbox_sessions", "Active sandbox sessions")

metrics_router = APIRouter(tags=["metrics"])


@metrics_router.get("/metrics")
async def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
