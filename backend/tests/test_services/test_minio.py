import pytest
from unittest.mock import MagicMock, patch
from io import BytesIO


@pytest.fixture
def mock_minio():
    client = MagicMock()
    client.presigned_put_object = MagicMock(return_value="https://minio/upload-url")
    client.presigned_get_object = MagicMock(return_value="https://minio/download-url")
    client.put_object = MagicMock()
    client.get_object = MagicMock(return_value=MagicMock(read=MagicMock(return_value=b"file data")))
    return client


def test_upload_url_returns_presigned(mock_minio):
    with patch("app.services.minio_client.Minio", return_value=mock_minio):
        from app.services.minio_client import MinioService
        svc = MinioService()
        url = svc.presigned_upload_url(object_name="uploads/u1/test.pdf", content_type="application/pdf")
        assert url == "https://minio/upload-url"
        mock_minio.presigned_put_object.assert_called_once()


def test_download_url_returns_presigned(mock_minio):
    with patch("app.services.minio_client.Minio", return_value=mock_minio):
        from app.services.minio_client import MinioService
        svc = MinioService()
        url = svc.presigned_download_url(object_name="artifacts/t1/result.json", bucket="agentis-artifacts")
        assert url == "https://minio/download-url"
        mock_minio.presigned_get_object.assert_called_once()


def test_upload_bytes_calls_put_object(mock_minio):
    with patch("app.services.minio_client.Minio", return_value=mock_minio):
        from app.services.minio_client import MinioService
        svc = MinioService()
        svc.upload_bytes(object_name="uploads/u1/data.json", data=b'{"ok": true}', content_type="application/json")
        mock_minio.put_object.assert_called_once()


def test_object_name_for_upload_includes_user_and_filename():
    from app.services.minio_client import object_name_for_upload
    name = object_name_for_upload(user_id="u1", filename="report.pdf")
    assert name.startswith("uploads/u1/")
    assert "report.pdf" in name
