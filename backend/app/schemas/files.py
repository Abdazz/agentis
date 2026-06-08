from pydantic import BaseModel


class FileUploadInitResponse(BaseModel):
    upload_url: str
    object_name: str
    expires_in: int


class FileDownloadResponse(BaseModel):
    download_url: str
    expires_in: int
