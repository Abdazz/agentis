"""Celery Beat periodic jobs — Phase 2A memory maintenance + Phase 2D cleanup/reset."""
from app.worker.celery_app import celery_app
from app.memory.long_term import long_term_memory
from app.services.minio_client import minio_service
from app.config import settings


@celery_app.task(name="beat.decay_memory_importance")
def decay_memory_importance() -> dict:
    """Reduce importance of all memory entries by 5% daily (BR-MEM-29)."""
    updated = long_term_memory.decay_all(factor=0.95)
    return {"updated": updated}


@celery_app.task(name="beat.prune_memory")
def prune_memory() -> dict:
    """Delete memory entries with importance < 0.05 daily (BR-MEM-31)."""
    deleted = long_term_memory.prune(threshold=0.05)
    return {"deleted": deleted}


@celery_app.task(name="beat.cleanup_artifacts")
def cleanup_artifacts() -> dict:
    """Delete MinIO artifact objects older than 30 days (spec §18 BK-4)."""
    import datetime
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    objects = minio_service._client.list_objects(
        settings.minio_bucket_artifacts, recursive=True
    )
    deleted = 0
    for obj in objects:
        if obj.last_modified and obj.last_modified.replace(tzinfo=None) < cutoff:
            minio_service._client.remove_object(settings.minio_bucket_artifacts, obj.object_name)
            deleted += 1
    return {"deleted": deleted}


@celery_app.task(name="beat.reset_monthly_tokens")
def reset_monthly_tokens() -> dict:
    """Reset token_used_this_month to 0 for all users on the 1st of each month."""
    import asyncio
    from sqlalchemy import update

    async def _run():
        from app.database import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as session:
            result = await session.execute(update(User).values(token_used_this_month=0))
            await session.commit()
            return result.rowcount

    count = asyncio.run(_run())
    return {"reset": count}
