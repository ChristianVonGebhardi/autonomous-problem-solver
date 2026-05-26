import structlog
import numpy as np
from typing import List, Optional
from sentence_transformers import SentenceTransformer

from app.config import settings

logger = structlog.get_logger()

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model", model=settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
        logger.info("Embedding model loaded")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts and return vectors."""
    model = get_embedding_model()
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
    return embeddings.tolist()


def embed_single(text: str) -> List[float]:
    """Embed a single text string."""
    return embed_texts([text])[0]