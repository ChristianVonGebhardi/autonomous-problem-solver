import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_hybrid_retriever_extracts_keywords():
    from app.services.retrieval_service import HybridRetriever
    retriever = HybridRetriever()
    keywords = retriever._extract_keywords("Why was the authentication redesigned?")
    assert len(keywords) > 0
    # "authentication" and "redesigned" should appear
    assert "authentication" in keywords or "redesigned" in keywords


@pytest.mark.asyncio
async def test_hybrid_retriever_merges_results():
    from app.services.retrieval_service import HybridRetriever
    retriever = HybridRetriever()
    
    vector_results = [
        {"chunk_id": "abc", "file_path": "auth.py", "content": "auth code", "score": 0.9},
        {"chunk_id": "def", "file_path": "user.py", "content": "user code", "score": 0.7},
    ]
    graph_results = [
        {"path": "middleware.py", "type": "file", "relevance": 0.8},
        {"path": "auth.py", "type": "file", "relevance": 0.6},  # duplicate
    ]
    
    merged = retriever._merge_results(vector_results, graph_results)
    
    # Should not have duplicates
    paths = [r.get("file_path", r.get("chunk_id", "")) for r in merged]
    assert len(paths) == len(set(paths))
    
    # auth.py should only appear once
    assert sum(1 for r in merged if "auth.py" in str(r.get("file_path", ""))) == 1


def test_llm_service_mock_mode():
    """LLM service should work in mock mode without API key."""
    import asyncio
    from app.services.llm_service import LLMService
    
    service = LLMService()
    # Force mock mode
    service._mock_mode = True
    
    chunks = [
        {"file_path": "main.py", "content": "def main(): pass", "chunk_type": "function", "name": "main", "score": 0.8},
    ]
    
    result = asyncio.get_event_loop().run_until_complete(
        service.answer_question("What does main do?", chunks, repo_name="test")
    )
    
    assert "answer" in result
    assert "sources" in result
    assert len(result["sources"]) > 0
    assert result["model_used"] == "mock"