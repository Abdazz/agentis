"""Celery Beat periodic jobs — Phase 2A memory maintenance."""
from app.worker.celery_app import celery_app
from app.memory.long_term import long_term_memory


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
