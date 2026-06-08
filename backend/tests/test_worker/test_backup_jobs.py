import pytest
from unittest.mock import MagicMock, patch


def test_backup_postgres_calls_pg_dump():
    with patch("app.worker.backup_jobs.subprocess.run") as mock_run, \
         patch("app.worker.backup_jobs.minio_service") as mock_minio:
        mock_run.return_value = MagicMock(returncode=0, stdout=b"dump-data")
        mock_minio.upload_bytes = MagicMock()
        from app.worker.backup_jobs import backup_postgres
        result = backup_postgres()
        mock_run.assert_called_once()
        mock_minio.upload_bytes.assert_called_once()
        assert result["success"] is True


def test_backup_qdrant_calls_snapshot_api():
    with patch("app.worker.backup_jobs.httpx.post") as mock_post, \
         patch("app.worker.backup_jobs.httpx.get") as mock_get, \
         patch("app.worker.backup_jobs.minio_service") as mock_minio:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"result": {"name": "snap.snapshot"}})
        mock_get.return_value = MagicMock(status_code=200, content=b"snapshot-data")
        mock_minio.upload_bytes = MagicMock()
        from app.worker.backup_jobs import backup_qdrant
        result = backup_qdrant()
        assert result["success"] is True
        mock_minio.upload_bytes.assert_called_once()


def test_cleanup_artifacts_removes_old_objects():
    with patch("app.worker.beat_jobs.minio_service") as mock_minio:
        mock_minio._client = MagicMock()
        mock_minio._client.list_objects = MagicMock(return_value=[])
        from app.worker.beat_jobs import cleanup_artifacts
        result = cleanup_artifacts()
        assert "deleted" in result
