import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient


@pytest.fixture
def mock_minio_svc():
    svc = MagicMock()
    svc.presigned_upload_url.return_value = "https://minio/upload-presigned"
    svc.presigned_download_url.return_value = "https://minio/download-presigned"
    return svc


@pytest.mark.asyncio
async def test_initiate_upload_returns_presigned_url(async_client: AsyncClient, auth_headers: dict,
                                                      mock_minio_svc):
    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.post(
            "/api/v1/files/upload/initiate",
            json={"filename": "document.pdf", "content_type": "application/pdf"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "upload_url" in data
    assert "object_name" in data
    assert data["upload_url"] == "https://minio/upload-presigned"


@pytest.mark.asyncio
async def test_initiate_upload_requires_auth(async_client: AsyncClient, mock_minio_svc):
    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.post(
            "/api/v1/files/upload/initiate",
            json={"filename": "document.pdf", "content_type": "application/pdf"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_download_url_returns_presigned(async_client: AsyncClient, auth_headers: dict,
                                                   mock_minio_svc):
    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.get(
            "/api/v1/files/artifacts/tasks/t1/result.json/url",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert "download_url" in resp.json()
