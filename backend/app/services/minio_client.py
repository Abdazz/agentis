import datetime
from io import BytesIO
from minio import Minio
from app.config import settings


def object_name_for_upload(user_id: str, filename: str) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    return f"uploads/{user_id}/{ts}_{filename}"


class MinioService:
    def __init__(self) -> None:
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def presigned_upload_url(self, object_name: str, content_type: str = "application/octet-stream",
                              bucket: str | None = None) -> str:
        bkt = bucket or settings.minio_bucket_uploads
        return self._client.presigned_put_object(
            bkt, object_name,
            expires=datetime.timedelta(seconds=settings.minio_presigned_expiry_seconds),
        )

    def presigned_download_url(self, object_name: str, bucket: str | None = None) -> str:
        bkt = bucket or settings.minio_bucket_uploads
        return self._client.presigned_get_object(
            bkt, object_name,
            expires=datetime.timedelta(seconds=settings.minio_presigned_expiry_seconds),
        )

    def upload_bytes(self, object_name: str, data: bytes,
                     content_type: str = "application/octet-stream",
                     bucket: str | None = None) -> None:
        bkt = bucket or settings.minio_bucket_uploads
        self._client.put_object(bkt, object_name, BytesIO(data), length=len(data),
                                 content_type=content_type)

    def download_bytes(self, object_name: str, bucket: str | None = None) -> bytes:
        bkt = bucket or settings.minio_bucket_uploads
        response = self._client.get_object(bkt, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


minio_service = MinioService()
