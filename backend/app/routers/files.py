from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.task import Artifact, Task
from app.services.minio_client import minio_service, object_name_for_upload
from app.schemas.files import FileUploadInitResponse, FileDownloadResponse
from app.config import settings

router = APIRouter(prefix="/files", tags=["files"])


class UploadInitRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"


@router.post("/upload/initiate", response_model=FileUploadInitResponse)
async def initiate_upload(body: UploadInitRequest, current_user: User = Depends(get_current_user)):
    obj = object_name_for_upload(user_id=str(current_user.id), filename=body.filename)
    url = minio_service.presigned_upload_url(object_name=obj, content_type=body.content_type)
    return FileUploadInitResponse(
        upload_url=url,
        object_name=obj,
        expires_in=settings.minio_presigned_expiry_seconds,
    )


class ScanRequest(BaseModel):
    object_name: str


class ScanResponse(BaseModel):
    object_name: str
    clean: bool
    virus: str | None = None
    skipped: bool = False


@router.post("/scan", response_model=ScanResponse)
async def scan_file(
    body: ScanRequest,
    current_user: User = Depends(get_current_user),
):
    """Download object from MinIO and run ClamAV scan."""
    if not settings.clamav_enabled:
        return ScanResponse(object_name=body.object_name, clean=True, skipped=True)

    data = minio_service.download_bytes(object_name=body.object_name)
    from app.services.clamav_scanner import scan_bytes
    result = scan_bytes(data, socket_path=settings.clamav_socket)
    return ScanResponse(
        object_name=body.object_name,
        clean=result["clean"],
        virus=result.get("virus"),
        skipped=result.get("skipped", False),
    )


@router.get("/artifacts/{object_path:path}/url", response_model=FileDownloadResponse)
async def get_artifact_download_url(
    object_path: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify the artifact belongs to the requesting user before minting a presigned URL (IDOR guard)
    result = await db.execute(
        select(Artifact)
        .join(Task, Task.id == Artifact.task_id)
        .where(Artifact.storage_key == object_path)
        .where(Artifact.deleted_at.is_(None))
        .where(Task.user_id == current_user.id)
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    url = minio_service.presigned_download_url(
        object_name=object_path,
        bucket=settings.minio_bucket_artifacts,
    )
    return FileDownloadResponse(download_url=url, expires_in=settings.minio_presigned_expiry_seconds)
