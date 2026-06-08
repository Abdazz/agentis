from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.auth.dependencies import get_current_user
from app.models.user import User
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


@router.get("/artifacts/{object_path:path}/url", response_model=FileDownloadResponse)
async def get_artifact_download_url(object_path: str, current_user: User = Depends(get_current_user)):
    url = minio_service.presigned_download_url(
        object_name=object_path,
        bucket=settings.minio_bucket_artifacts,
    )
    return FileDownloadResponse(download_url=url, expires_in=settings.minio_presigned_expiry_seconds)
