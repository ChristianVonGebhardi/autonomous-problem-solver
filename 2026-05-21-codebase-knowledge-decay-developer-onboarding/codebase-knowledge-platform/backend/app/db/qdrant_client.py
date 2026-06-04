import structlog
import uuid
from typing import List, Dict, Any, Optional

from app.config import settings

logger = structlog.get_logger()

COLLECTION_NAME = "code_chunks"


class QdrantClientWrapper:
    def __init__(self):
        self.client = None

    async def connect(self):
        try:
            from qdrant_client import AsyncQdrantClient
            self.client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
            # Verify connectivity
            await self.client.get_collections()
            logger.info("Qdrant connected", host=settings.qdrant_host)
        except Exception as e:
            logger.warning("Qdrant not available", error=str(e))
            self.client = None

    async def create_collections(self):
        if not self.client:
            return
        try:
            from qdrant_client.models import Distance, VectorParams
            collections = await self.client.get_collections()
            existing = [c.name for c in collections.collections]
            if COLLECTION_NAME not in existing:
                await self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimension,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Created Qdrant collection", name=COLLECTION_NAME)
        except Exception as e:
            logger.warning("Could not create Qdrant collection", error=str(e))

    async def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        """Store code chunks with embeddings."""
        if not self.client or not chunks:
            return
        try:
            from qdrant_client.models import PointStruct
            points = []
            for chunk in chunks:
                # Deterministic UUID from chunk_id string
                point_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"])
                point_int_id = point_uuid.int >> 64  # Use upper 64 bits as positive int

                points.append(
                    PointStruct(
                        id=point_int_id,
                        vector=chunk["embedding"],
                        payload={
                            "chunk_id": chunk["chunk_id"],
                            "file_path": chunk["file_path"],
                            "repo_name": chunk["repo_name"],
                            "content": chunk["content"],
                            "start_line": chunk.get("start_line", 0),
                            "end_line": chunk.get("end_line", 0),
                            "chunk_type": chunk.get("chunk_type", "code"),
                            "name": chunk.get("name", ""),
                            "language": chunk.get("language", ""),
                            "commit_hash": chunk.get("commit_hash", ""),
                        },
                    )
                )
            await self.client.upsert(collection_name=COLLECTION_NAME, points=points)
        except Exception as e:
            logger.error("Failed to upsert chunks to Qdrant", error=str(e))

    async def search(
        self,
        query_vector: List[float],
        repo_name: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Semantic search over code chunks."""
        if not self.client:
            return []
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            filter_condition = None
            if repo_name:
                filter_condition = Filter(
                    must=[
                        FieldCondition(key="repo_name", match=MatchValue(value=repo_name))
                    ]
                )

            results = await self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=filter_condition,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [{**r.payload, "score": r.score} for r in results]
        except Exception as e:
            logger.error("Qdrant search failed", error=str(e))
            return []

    async def delete_by_repo(self, repo_name: str):
        """Remove all chunks for a repository."""
        if not self.client:
            return
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            await self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="repo_name", match=MatchValue(value=repo_name))
                    ]
                ),
            )
        except Exception as e:
            logger.error("Failed to delete repo chunks", error=str(e))


qdrant_client = QdrantClientWrapper()