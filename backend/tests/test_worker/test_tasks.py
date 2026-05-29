import uuid
import pytest
from unittest.mock import patch, AsyncMock
from app.worker.tasks import run_agent_task
from app.worker.celery_app import celery_app


def test_celery_app_configured():
    assert celery_app.conf.task_serializer == "json"
    assert "redis" in celery_app.conf.broker_url


def test_run_agent_task_invokes_runner():
    """The Celery task runs the async runner via asyncio."""
    tid = str(uuid.uuid4())
    with patch("app.worker.tasks.run_task", new=AsyncMock()) as mock_run:
        run_agent_task.run(tid)  # .run() executes the task body synchronously
        mock_run.assert_awaited_once_with(tid)
