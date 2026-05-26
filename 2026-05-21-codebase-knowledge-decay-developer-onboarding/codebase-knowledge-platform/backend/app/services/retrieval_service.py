import structlog
from typing import List, Dict, Any, Optional

from app.db.neo4j_client import neo4j_client
from app.db.qdrant_client import qdrant_client
from app.services.embedding_service import embed_single

logger = structlog.get_logger()


class HybridRetriever:
    """
    Hybrid retrieval combining:
    1. Dense vector search (Qdrant) for semantic similarity
    2. Graph traversal (Neo4j) for structural context
    """

    async def retrieve(
        self,
        question: str,
        repo_name: str,
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        Retrieve relevant chunks and graph context for a question.
        """
        # 1. Semantic vector search
        query_vector = embed_single(question)
        vector_results = await qdrant_client.search(
            query_vector=query_vector,
            repo_name=repo_name,
            limit=top_k,
            score_threshold=0.25,
        )
        logger.debug("Vector search results", count=len(vector_results))

        # 2. Graph context from Neo4j
        graph_context = await self._get_graph_context(question, repo_name, vector_results)

        # 3. Merge and rank
        merged = self._merge_results(vector_results, graph_context.get("additional_chunks", []))

        return {
            "chunks": merged,
            "graph_context": graph_context,
            "vector_count": len(vector_results),
            "graph_count": len(graph_context.get("additional_chunks", [])),
        }

    async def _get_graph_context(
        self,
        question: str,
        repo_name: str,
        vector_results: List[Dict],
    ) -> Dict[str, Any]:
        """Get graph-based context using file relationships."""
        context = {
            "commits": [],
            "related_files": [],
            "additional_chunks": [],
        }

        if not vector_results:
            return context

        # Get file paths from top vector results
        top_files = list({r["file_path"] for r in vector_results[:5]})
        
        # Get commit history for these files
        all_commits = []
        for file_path in top_files[:3]:
            try:
                commits = await neo4j_client.get_file_history(file_path, repo_name)
                all_commits.extend(commits)
            except Exception as e:
                logger.debug("Could not get file history", file=file_path, error=str(e))
        
        # Deduplicate commits
        seen_hashes = set()
        for c in all_commits:
            if c.get("hash") not in seen_hashes:
                context["commits"].append(c)
                seen_hashes.add(c.get("hash"))
        
        context["commits"] = context["commits"][:10]

        # Get related files (co-change coupling)
        for file_path in top_files[:2]:
            try:
                related = await neo4j_client.get_related_files(file_path, repo_name)
                context["related_files"].extend(related[:3])
            except Exception as e:
                logger.debug("Could not get related files", error=str(e))

        # Also do a keyword search via Neo4j
        keywords = self._extract_keywords(question)
        for keyword in keywords[:3]:
            try:
                graph_results = await neo4j_client.search_by_concept(keyword, repo_name)
                context["additional_chunks"].extend(graph_results[:3])
            except Exception:
                pass

        return context

    def _extract_keywords(self, question: str) -> List[str]:
        """Simple keyword extraction from question."""
        # Remove common question words
        stop_words = {
            "what", "why", "how", "when", "where", "who", "which",
            "is", "are", "was", "were", "the", "a", "an", "this", "that",
            "does", "do", "did", "has", "have", "had", "can", "could",
            "should", "would", "will", "be", "been", "being",
        }
        words = question.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        return keywords[:5]

    def _merge_results(
        self,
        vector_results: List[Dict],
        graph_results: List[Dict],
    ) -> List[Dict]:
        """Merge and deduplicate results, prioritizing by score."""
        seen_chunk_ids = set()
        merged = []
        
        for r in vector_results:
            chunk_id = r.get("chunk_id", r.get("path", ""))
            if chunk_id not in seen_chunk_ids:
                merged.append(r)
                seen_chunk_ids.add(chunk_id)
        
        # Add graph results as lower-scored items if not already present
        for r in graph_results:
            identifier = r.get("path", "")
            if identifier and identifier not in seen_chunk_ids:
                merged.append({
                    "chunk_id": identifier,
                    "file_path": identifier,
                    "content": f"Related: {identifier}",
                    "chunk_type": r.get("type", "code"),
                    "score": float(r.get("relevance", 0.5)) * 0.5,
                    "name": "",
                    "start_line": 0,
                    "end_line": 0,
                })
                seen_chunk_ids.add(identifier)
        
        # Sort by score
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)
        return merged[:12]


hybrid_retriever = HybridRetriever()