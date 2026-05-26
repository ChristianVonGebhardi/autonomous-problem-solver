import structlog
from typing import List, Dict, Any, Optional
import json

from app.config import settings

logger = structlog.get_logger()


class LLMService:
    """LLM synthesis layer. Uses OpenAI GPT-4o when available, else mock."""

    def __init__(self):
        self._client = None
        self._mock_mode = False

    def _get_client(self):
        if self._client is not None:
            return self._client
        
        if not settings.openai_api_key:
            logger.warning("No OpenAI API key — using mock LLM mode")
            self._mock_mode = True
            return None

        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            return self._client
        except Exception as e:
            logger.error("Failed to create OpenAI client", error=str(e))
            self._mock_mode = True
            return None

    async def answer_question(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        graph_context: Optional[Dict] = None,
        repo_name: str = "",
    ) -> Dict[str, Any]:
        """Generate an answer using retrieved context (RAG)."""
        
        client = self._get_client()
        
        if self._mock_mode or client is None:
            return self._mock_answer(question, context_chunks, repo_name)

        # Build context string
        context_parts = []
        sources = []
        
        for i, chunk in enumerate(context_chunks[:8], 1):
            file_path = chunk.get("file_path", "unknown")
            content = chunk.get("content", "")
            chunk_type = chunk.get("chunk_type", "code")
            name = chunk.get("name", "")
            score = chunk.get("score", 0)
            
            context_parts.append(
                f"[Source {i}] File: {file_path}"
                + (f" | {chunk_type}: {name}" if name else "")
                + f"\n```\n{content[:800]}\n```"
            )
            sources.append({
                "file_path": file_path,
                "chunk_type": chunk_type,
                "name": name,
                "score": round(score, 3),
                "start_line": chunk.get("start_line", 0),
                "end_line": chunk.get("end_line", 0),
            })

        # Add graph context
        graph_section = ""
        if graph_context:
            commits = graph_context.get("commits", [])
            if commits:
                commit_info = "\n".join(
                    f"- {c.get('hash', '')[:8]}: {c.get('message', '')[:100]} (by {c.get('author_name', 'unknown')})"
                    for c in commits[:5]
                )
                graph_section = f"\n\nRelevant commit history:\n{commit_info}"

        context_str = "\n\n".join(context_parts)
        
        system_prompt = """You are a senior software architect helping developers understand a codebase.
You answer questions about code architecture, design decisions, and implementation details.
Always ground your answers in the provided code context. When referencing code, cite the source file.
Be concise but thorough. Explain the 'why' behind architectural decisions when evident from commits and PRs."""

        user_prompt = f"""Repository: {repo_name}

Code Context:
{context_str}
{graph_section}

Question: {question}

Provide a clear, grounded answer based on the code context above."""

        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1500,
            )
            answer = response.choices[0].message.content
            model_used = settings.openai_model
        except Exception as e:
            logger.error("OpenAI API call failed", error=str(e))
            return self._mock_answer(question, context_chunks, repo_name)

        return {
            "answer": answer,
            "sources": sources,
            "model_used": model_used,
            "context_chunks_used": len(context_chunks),
        }

    def _mock_answer(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        repo_name: str,
    ) -> Dict[str, Any]:
        """Generate a mock answer when OpenAI is not available."""
        sources = []
        context_preview = []

        for chunk in context_chunks[:5]:
            file_path = chunk.get("file_path", "unknown")
            content = chunk.get("content", "")
            sources.append({
                "file_path": file_path,
                "chunk_type": chunk.get("chunk_type", "code"),
                "name": chunk.get("name", ""),
                "score": round(chunk.get("score", 0), 3),
                "start_line": chunk.get("start_line", 0),
                "end_line": chunk.get("end_line", 0),
            })
            context_preview.append(f"- `{file_path}`: {content[:100].strip()}...")

        context_text = "\n".join(context_preview) if context_preview else "No relevant context found."

        answer = f"""**[Mock Mode — Set OPENAI_API_KEY for AI-powered answers]**

**Question:** {question}

**Repository:** `{repo_name}`

**Relevant code context found in {len(context_chunks)} chunks:**

{context_text}

To get AI-synthesized answers that explain architecture decisions, design rationale, and system interactions, please configure your OpenAI API key in `.env`.

The system has successfully:
1. Indexed your codebase into a semantic vector store
2. Retrieved the {len(context_chunks)} most relevant code sections
3. Built a knowledge graph of file relationships and commit history

With an OpenAI key, the LLM synthesizer would analyze these sources and provide a coherent architectural explanation."""

        return {
            "answer": answer,
            "sources": sources,
            "model_used": "mock",
            "context_chunks_used": len(context_chunks),
        }

    async def generate_summary(self, content: str, content_type: str = "code") -> str:
        """Generate a brief summary of code/commit/PR content."""
        client = self._get_client()
        if self._mock_mode or client is None:
            return f"[Mock summary of {content_type}]: {content[:100]}..."

        try:
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "user",
                        "content": f"Summarize this {content_type} in 1-2 sentences:\n\n{content[:2000]}",
                    }
                ],
                temperature=0.0,
                max_tokens=150,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("Summary generation failed", error=str(e))
            return f"Summary unavailable: {content[:100]}..."


llm_service = LLMService()