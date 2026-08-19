"""Prometheus metrics registry (spec §17 OBS-1).

The API and Celery worker run as separate processes (see
docker-compose.yml) — plain in-process Counters/Histograms recorded in
the worker (where tool calls, LLM usage, and task completions actually
happen) would never be visible on the API's /metrics endpoint that
Prometheus scrapes. PROMETHEUS_MULTIPROC_DIR (set in both services'
environment, pointed at a shared tmpfs volume) switches prometheus_client
into multiprocess mode: each process writes its own mmap'd metric file,
and /metrics aggregates all of them via MultiProcessCollector.
"""
import os

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry, multiprocess
from fastapi import APIRouter
from fastapi.responses import Response

tasks_created_total = Counter("agentis_tasks_created_total", "Tasks created", ["status"])
tool_calls_total = Counter("agentis_tool_calls_total", "Tool calls", ["tool_name", "success"])
llm_tokens_total = Counter("agentis_llm_tokens_total", "LLM tokens consumed", ["provider", "model"])
hitl_requests_total = Counter("agentis_hitl_requests_total", "HITL requests triggered")
hitl_responses_total = Counter("agentis_hitl_responses_total", "HITL responses received", ["outcome"])
scheduled_tasks_fired_total = Counter(
    "agentis_scheduled_tasks_fired_total", "Scheduled task firings", ["status"]
)

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
    multiproc_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiproc_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=multiproc_dir)
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    # Single-process fallback (e.g. local dev running only `uvicorn`, or
    # tests) — the default global registry.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
