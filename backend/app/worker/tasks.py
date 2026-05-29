"""Celery task entry points. Each task bridges sync Celery → async runner."""
import asyncio
import structlog
from app.worker.celery_app import celery_app
from app.orchestrator.runner import run_task

log = structlog.get_logger()


@celery_app.task(name="agentis.run_agent", bind=True)
def run_agent_task(self, task_id: str) -> None:
    log.info("celery_run_agent_start", task_id=task_id, celery_id=self.request.id)
    asyncio.run(run_task(task_id))
    log.info("celery_run_agent_done", task_id=task_id)
