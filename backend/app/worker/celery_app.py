"""Celery application (spec: Task Queue, Redis DB0 broker)."""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "agentis",
    broker=settings.redis_broker_url,
    backend=settings.redis_broker_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=settings.worker_concurrency,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)
