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
                                                   mock_minio_svc, db_session):
    import uuid
    from datetime import datetime, timezone
    from app.models.task import Task, TaskStatus, Artifact
    from app.models.user import User
    from sqlalchemy import select

    # Resolve the user created by auth_headers
    result = await db_session.execute(select(User).where(User.email == "filetest@example.com"))
    user = result.scalar_one()

    storage_key = f"tasks/{user.id}/result.json"
    task = Task(
        id=uuid.uuid4(), user_id=user.id, goal="test", status=TaskStatus.completed,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.flush()
    artifact = Artifact(
        task_id=task.id, name="result.json", storage_key=storage_key,
        size_bytes=100, created_at=datetime.now(timezone.utc),
    )
    db_session.add(artifact)
    await db_session.commit()

    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.get(
            f"/api/v1/files/artifacts/{storage_key}/url",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert "download_url" in resp.json()


@pytest.mark.asyncio
async def test_get_download_url_rejects_other_user_artifact(async_client: AsyncClient,
                                                             mock_minio_svc, db_session):
    """IDOR guard: user A cannot get a presigned URL for user B's artifact."""
    import uuid
    from datetime import datetime, timezone
    from app.models.task import Task, TaskStatus, Artifact
    from app.models.user import User
    from app.auth.password import hash_password

    # Create a separate user whose artifact we'll try to access
    other_user = User(
        id=uuid.uuid4(), email=f"other_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=hash_password("Pass1234!Secret"),
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(other_user)
    await db_session.flush()
    task = Task(
        id=uuid.uuid4(), user_id=other_user.id, goal="other goal",
        status=TaskStatus.completed,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    db_session.add(task)
    await db_session.flush()
    artifact = Artifact(
        task_id=task.id, name="secret.json",
        storage_key=f"tasks/{other_user.id}/secret.json",
        size_bytes=50, created_at=datetime.now(timezone.utc),
    )
    db_session.add(artifact)
    await db_session.commit()

    # Register/login as a different user and try to access the artifact
    reg = await async_client.post("/api/v1/auth/register",
                                  json={"email": "attacker@test.com", "password": "Pass1234!Secret"})
    if reg.status_code == 409:
        login = await async_client.post("/api/v1/auth/login",
                                        json={"email": "attacker@test.com", "password": "Pass1234!Secret"})
    else:
        login = await async_client.post("/api/v1/auth/login",
                                        json={"email": "attacker@test.com", "password": "Pass1234!Secret"})
    attacker_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    with patch("app.routers.files.minio_service", mock_minio_svc):
        resp = await async_client.get(
            f"/api/v1/files/artifacts/tasks/{other_user.id}/secret.json/url",
            headers=attacker_headers,
        )
    assert resp.status_code == 404
