"""
Embedding generation for semantic drift detection.

Uses sentence-transformers (local, no API key required) to embed:
  - Agent step outputs
  - Concatenated run reasoning chains
  - Baseline golden run summaries

Embedding generation is intentionally off the agent critical path —
the SDK sends raw text, workers embed asynchronously.
"""

from __future__ import annotations

import numpy as np
from functools import lru_cache
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _get_model(model_name: str):
    """Load embedding model once and cache."""
    from sentence_transformers import SentenceTransformer
    logger.info("loading_embedding_model", model=model_name)
    return SentenceTransformer(model_name)


def embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> list[float]:
    """Embed a single text string. Returns list of floats (JSON-serializable)."""
    model = _get_model(model_name)
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_batch(texts: list[str], model_name: str = "all-MiniLM-L6-v2") -> list[list[float]]:
    """Embed multiple texts in a single batch for efficiency."""
    if not texts:
        return []
    model = _get_model(model_name)
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [e.tolist() for e in embeddings]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """
    Compute cosine distance (1 - cosine_similarity) between two embeddings.
    Returns 0.0 (identical) to 2.0 (opposite), clipped to [0, 1] for scoring.
    """
    va = np.array(a)
    vb = np.array(b)
    
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    
    if norm_a == 0 or norm_b == 0:
        return 1.0  # undefined — treat as maximally different
    
    similarity = np.dot(va, vb) / (norm_a * norm_b)
    # Clip for numerical stability
    similarity = float(np.clip(similarity, -1.0, 1.0))
    distance = 1.0 - similarity
    return float(np.clip(distance, 0.0, 1.0))


def aggregate_run_embedding(
    step_outputs: list[str],
    model_name: str = "all-MiniLM-L6-v2",
) -> Optional[list[float]]:
    """
    Create a single run-level embedding by mean-pooling step output embeddings.
    
    This captures the overall semantic "intent trajectory" of the run rather
    than any single step in isolation.
    """
    if not step_outputs:
        return None
    
    # Filter empty outputs
    texts = [t for t in step_outputs if t and t.strip()]
    if not texts:
        return None

    embeddings = embed_batch(texts, model_name)
    if not embeddings:
        return None

    arr = np.array(embeddings)
    mean_embedding = arr.mean(axis=0)
    
    # Renormalize after mean pooling
    norm = np.linalg.norm(mean_embedding)
    if norm > 0:
        mean_embedding = mean_embedding / norm
    
    return mean_embedding.tolist()


def mean_cosine_distance_to_baselines(
    run_embedding: list[float],
    baseline_embeddings: list[list[float]],
) -> float:
    """
    Compute mean cosine distance from a run embedding to all baseline embeddings.
    
    Returns 0.0 (matches baseline cluster perfectly) to 1.0 (fully diverged).
    Uses minimum distance (nearest baseline) to be fair when there are multiple
    valid behavioral modes.
    """
    if not baseline_embeddings:
        return 0.0  # No baselines — can't detect drift, score as 0
    
    distances = [cosine_distance(run_embedding, b) for b in baseline_embeddings]
    # Use minimum distance (closest baseline match)
    return float(min(distances))