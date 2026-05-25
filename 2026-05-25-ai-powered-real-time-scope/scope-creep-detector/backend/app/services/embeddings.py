from typing import List
import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

# Use 1536-dim model (text-embedding-3-large supports multiple dims)
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 1536


def get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_text(text: str) -> List[float]:
    """Embed a single text string."""
    client = get_openai_client()
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts in a single API call."""
    if not texts:
        return []
    client = get_openai_client()
    # Batch in chunks of 100
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i:i+100]
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([d.embedding for d in sorted_data])
    return all_embeddings