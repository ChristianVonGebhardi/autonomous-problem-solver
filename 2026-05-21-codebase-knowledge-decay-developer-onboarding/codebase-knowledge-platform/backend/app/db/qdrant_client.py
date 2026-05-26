import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
)
from typing import List, Dict, Any, Optional
import uuid

from app.config import settings

logger = structlog.get_logger()

COLLECTION_NAME = "code_chunks"


class QdrantClientWrapper:
    def __init__(self):
        self.client: Optional[AsyncQdrantClient] = None

    async def connect(self):
        try:
            self.client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
            )
            logger.info("Qdrant connected", host=settings.qdrant_host)
        except Exception as e:
            logger.warning("Qdrant not available", error=str(e))

    async def create_collections(self):
        if not self.client:
            return
        try:
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
        points = []
        for chunk in chunks:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"]))
            # Convert UUID string to int for Qdrant
            point_int_id = int(uuid.UUID(point_id))
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
        try:
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
            filter_condition = None
            if repo_name:
                filter_condition = Filter(
                    must=[FieldCondition(key="repo_name", match=MatchValue(value=repo_name))]
                )

            results = await self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=filter_condition,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [
                {**r.payload, "score": r.score}
                for r in results
            ]
        except Exception as e:
            logger.error("Qdrant search failed", error=str(e))
            return []

    async def delete_by_repo(self, repo_name: str):
        """Remove all chunks for a repository."""
        if not self.client:
            return
        try:
            await self.client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[FieldCondition(key="repo_name", match=MatchValue(value=repo_name))]
                ),
            )
        except Exception as e:
            logger.error("Failed to delete repo chunks", error=str(e))


qdrant_client = QdrantClientWrapper()