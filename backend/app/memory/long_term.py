"""Long-term memory via Qdrant + Voyage AI embeddings (spec §8.3 MEM-3)."""
import uuid
from typing import Any
import voyageai
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue,
    FilterSelector, Range,
)
from app.config import settings


class LongTermMemory:
    def __init__(self) -> None:
        self._qdrant_sync = QdrantClient(url=settings.qdrant_url)
        self._qdrant_async = AsyncQdrantClient(url=settings.qdrant_url)

        # Initialize Voyage AI client with optional self-hosted base_url
        if settings.voyage_api_key:
            voyage_kwargs = {"api_key": settings.voyage_api_key}
            if settings.voyage_base_url:
                voyage_kwargs["base_url"] = settings.voyage_base_url
            self._voyage = voyageai.Client(**voyage_kwargs)
        else:
            self._voyage = None

        self._collection = settings.qdrant_collection

    def ensure_collection(self) -> None:
        """Idempotent collection init (BR-MEM-27, BR-MEM-28)."""
        if self._qdrant_sync.collection_exists(self._collection):
            return
        self._qdrant_sync.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=settings.voyage_embedding_dim, distance=Distance.COSINE),
        )

    def _embed(self, text: str) -> list[float]:
        if not self._voyage:
            return [0.0] * settings.voyage_embedding_dim
        result = self._voyage.embed([text], model=settings.voyage_model)
        return result.embeddings[0]

    async def store(
        self,
        user_id: str,
        task_id: str,
        content: str,
        summary: str,
        tags: list[str] | None = None,
        language: str = "fr",
        importance: float = 0.5,
    ) -> str:
        """Embed + upsert a memory. Returns the Qdrant point ID string."""
        vector = self._embed(content)
        point_id = str(uuid.uuid4())
        await self._qdrant_async.upsert(
            collection_name=self._collection,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "user_id": user_id,
                    "task_id": task_id,
                    "content": content,
                    "summary": summary,
                    "tags": tags or [],
                    "language": language,
                    "importance": importance,
                },
            )],
        )
        return point_id

    async def search(self, user_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search scoped to user_id. Returns list of {content, summary, score}."""
        vector = self._embed(query)
        user_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
        )
        results = await self._qdrant_async.search(
            collection_name=self._collection,
            query_vector=vector,
            query_filter=user_filter,
            limit=top_k,
        )
        return [
            {
                "content": r.payload.get("content", ""),
                "summary": r.payload.get("summary", ""),
                "score": r.score,
            }
            for r in results
        ]

    def decay_all(self, factor: float = 0.95) -> int:
        """Reduce importance by factor for all points. Returns count updated."""
        offset = None
        updated = 0
        while True:
            points, next_offset = self._qdrant_sync.scroll(
                collection_name=self._collection, limit=100, offset=offset, with_payload=True
            )
            if not points:
                break
            for p in points:
                new_imp = float(p.payload.get("importance", 0.5)) * factor
                self._qdrant_sync.set_payload(
                    collection_name=self._collection,
                    payload={"importance": new_imp},
                    points=[p.id],
                )
                updated += 1
            if next_offset is None:
                break
            offset = next_offset
        return updated

    def prune(self, threshold: float = 0.05) -> int:
        """Delete points with importance < threshold. Returns count deleted."""
        low_imp_filter = Filter(
            must=[FieldCondition(key="importance", range=Range(lt=threshold))]
        )
        # Count before deleting (UpdateResult has no count field)
        count_result = self._qdrant_sync.count(
            collection_name=self._collection,
            count_filter=low_imp_filter,
            exact=True,
        )
        deleted = count_result.count
        if deleted > 0:
            self._qdrant_sync.delete(
                collection_name=self._collection,
                points_selector=FilterSelector(filter=low_imp_filter),
            )
        return deleted


# Module-level singleton — QdrantClient connects lazily on first call
long_term_memory = LongTermMemory()
