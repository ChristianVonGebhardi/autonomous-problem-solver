"""
Span Enricher — Async embedding generation for behavioral spans.

Runs off the critical path so agent SLAs are not impacted.
Uses local sentence-transformers (no API key required).
"""

import asyncio
import hashlib
import logging
from typing import Optional, List
import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded to avoid import time cost
_model = None
_model_lock = asyncio.Lock()


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load the sentence-transformer model (cached singleton)."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(model_name)
            logger.info(f"Loaded embedding model: {model_name}")
        except ImportError:
            logger.warning(
                "sentence-transformers not available — embeddings disabled"
            )
            return None
    return _model


class SpanEnricher:
    """
    Enriches BehaviorSpan instances with computed metadata.

    - reasoning_embedding: embedding vector for semantic drift detection
    - retrieved_chunk_hashes: normalized content fingerprints
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name

    def embed_text(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a text string. Returns None if unavailable."""
        if not text or not text.strip():
            return None
        model = _get_model(self.model_name)
        if model is None:
            return None
        try:
            embedding = model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None

    def hash_content(self, content: str) -> str:
        """Create a short content fingerprint for retrieval tracking."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def enrich_span(self, span) -> None:
        """Enrich a single span with embeddings (async wrapper)."""
        loop = asyncio.get_event_loop()

        # Generate reasoning embedding if reasoning is available
        if span.reasoning and span.reasoning_embedding is None:
            embedding = await loop.run_in_executor(
                None, self.embed_text, span.reasoning
            )
            span.reasoning_embedding = embedding

    async def enrich_run(self, run) -> None:
        """Enrich all spans in a trace run concurrently."""
        tasks = [self.enrich_span(span) for span in run.spans]
        await asyncio.gather(*tasks, return_exceptions=True)

    def compute_run_embedding(self, run) -> Optional[List[float]]:
        """
        Compute a single representative embedding for an entire run.
        Aggregates reasoning across all steps by averaging embeddings.
        """
        embeddings = []
        for span in run.spans:
            if span.reasoning_embedding:
                embeddings.append(np.array(span.reasoning_embedding))
            elif span.reasoning:
                emb = self.embed_text(span.reasoning)
                if emb:
                    embeddings.append(np.array(emb))

        if not embeddings:
            return None

        # Mean pooling across steps
        stacked = np.stack(embeddings, axis=0)
        mean_emb = np.mean(stacked, axis=0)
        # Re-normalize
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm
        return mean_emb.tolist()