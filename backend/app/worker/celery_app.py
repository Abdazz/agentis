"""Celery application (spec: Task Queue, Redis DB0 broker)."""
from celery import Celery
from app.config import settings

celery_app = Celery(
    "agentis",
    broker=settings.redis_broker_url,
    backend=settings.redis_broker_url,
    include=["app.worker.tasks", "app.worker.beat_jobs", "app.worker.backup_jobs", "app.services.webhook_dispatcher"],
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

celery_app.conf.beat_schedule = {
    "decay-memory-importance-daily": {
        "task": "beat.decay_memory_importance",
        "schedule": 86400.0,
    },
    "prune-memory-daily": {
        "task": "beat.prune_memory",
        "schedule": 86400.0,
    },
    "cleanup-artifacts-weekly": {
        "task": "beat.cleanup_artifacts",
        "schedule": 604800.0,
    },
    "reset-monthly-tokens": {
        "task": "beat.reset_monthly_tokens",
        "schedule": 2592000.0,
    },
    "backup-postgres-daily": {
        "task": "beat.backup_postgres",
        "schedule": 86400.0,
    },
    "backup-qdrant-daily": {
        "task": "beat.backup_qdrant",
        "schedule": 86400.0,
    },
    "replenish-sandbox-warm-pool": {
        "task": "beat.replenish_sandbox_warm_pool",
        "schedule": 60.0,
    },
    "run-due-scheduled-tasks": {
        "task": "beat.run_due_scheduled_tasks",
        "schedule": 60.0,
    },
}
