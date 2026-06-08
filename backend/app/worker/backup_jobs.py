"""Backup Celery tasks: PostgreSQL dump to MinIO + Qdrant snapshot (spec §18 BK-1..3)."""
import subprocess
import datetime
import httpx
from app.worker.celery_app import celery_app
from app.services.minio_client import minio_service
from app.config import settings


@celery_app.task(name="beat.backup_postgres")
def backup_postgres() -> dict:
    """pg_dump → upload to agentis-backups bucket."""
    import os
    from urllib.parse import urlparse as _urlparse
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    object_name = f"backups/postgres/{ts}.dump"

    # Pass credentials via environment, not argv, to avoid exposure in process listings
    parsed = _urlparse(str(settings.postgres_direct_url).replace("postgresql+asyncpg://", "postgresql://"))
    pg_env = {**os.environ, "PGPASSWORD": parsed.password or ""}
    result = subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            f"--host={parsed.hostname}",
            f"--port={parsed.port or 5432}",
            f"--username={parsed.username}",
            parsed.path.lstrip("/"),  # database name only
        ],
        capture_output=True,
        env=pg_env,
    )
    if result.returncode != 0:
        # Return generic failure; credentials must never appear in error output
        return {"success": False, "error": "pg_dump failed — check worker logs for details"}

    minio_service.upload_bytes(
        object_name=object_name,
        data=result.stdout,
        content_type="application/octet-stream",
        bucket=settings.minio_bucket_backups,
    )
    return {"success": True, "object": object_name, "size_bytes": len(result.stdout)}


@celery_app.task(name="beat.backup_qdrant")
def backup_qdrant() -> dict:
    """Create Qdrant snapshot → download → upload to MinIO."""
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    collection = settings.qdrant_collection

    resp = httpx.post(
        f"{settings.qdrant_url}/collections/{collection}/snapshots",
        timeout=120.0,
    )
    if resp.status_code not in (200, 201):
        return {"success": False, "error": resp.text}

    snap_name = resp.json()["result"]["name"]
    snap_resp = httpx.get(
        f"{settings.qdrant_url}/collections/{collection}/snapshots/{snap_name}",
        timeout=300.0,
    )

    object_name = f"backups/qdrant/{ts}_{snap_name}"
    minio_service.upload_bytes(
        object_name=object_name,
        data=snap_resp.content,
        content_type="application/octet-stream",
        bucket=settings.minio_bucket_backups,
    )
    return {"success": True, "object": object_name, "size_bytes": len(snap_resp.content)}
