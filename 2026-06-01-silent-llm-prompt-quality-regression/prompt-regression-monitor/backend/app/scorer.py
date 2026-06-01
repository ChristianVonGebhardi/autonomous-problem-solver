"""
Quality Scorer — runs configurable evaluators on LLM outputs.
"""
import re
import hashlib
import numpy as np
import structlog
from typing import List, Tuple, Optional, Dict, Any

from app.config import settings

logger = structlog.get_logger()


class QualityScorer:
    """Orchestrates multiple quality evaluators for a single inference."""

    def __init__(self, db_session):
        self.db = db_session
        self._embedding_client = None
        self._openai_client = None

    def _get_openai_client(self):
        if self._openai_client is None:
            import openai
            self._openai_client = openai.OpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    def score(
        self,
        template_id,
        output_text: str,
        request_payload: dict,
        response_payload: dict,
    ) -> List[Tuple[str, float, dict]]:
        """
        Returns list of (metric_name, score, metadata) tuples.
        Score range is always [0, 1] where 1 is best.
        """
        results = []

        if not output_text:
            return results

        # 1. Length/format checks (always run)
        results.extend(self._score_format(output_text, request_payload))

        # 2. Embedding similarity vs golden references
        if settings.use_embeddings:
            results.extend(
                self._score_embedding_similarity(template_id, output_text, request_payload)
            )

        # 3. ROUGE metrics vs golden references
        if settings.use_rouge:
            results.extend(
                self._score_rouge(template_id, output_text, request_payload)
            )

        # 4. LLM-as-judge
        if settings.use_llm_judge and settings.openai_api_key:
            results.extend(
                self._score_llm_judge(output_text, request_payload)
            )

        # 5. Custom rules
        results.extend(self._score_custom_rules(output_text, request_payload))

        return results

    def _score_format(
        self, output_text: str, request_payload: dict
    ) -> List[Tuple[str, float, dict]]:
        """Basic format and content checks."""
        results = []

        # Non-empty check
        is_nonempty = 1.0 if output_text.strip() else 0.0
        results.append(("format_nonempty", is_nonempty, {}))

        # Length score (penalize very short or truncated responses)
        length = len(output_text.split())
        if length < 5:
            length_score = 0.2
        elif length < 20:
            length_score = 0.7
        else:
            length_score = 1.0
        results.append(("format_length_adequacy", length_score, {"word_count": length}))

        # Repetition detection
        words = output_text.lower().split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            results.append(("format_repetition_score", min(unique_ratio * 1.5, 1.0), {}))

        return results

    def _get_golden_references(self, template_id) -> List[Any]:
        """Fetch golden references for a template."""
        from app.models import GoldenReference
        from sqlalchemy import select
        refs = self.db.execute(
            select(GoldenReference).where(GoldenReference.template_id == template_id)
        ).scalars().all()
        return refs

    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding for text using OpenAI API."""
        if not settings.openai_api_key:
            return None
        try:
            client = self._get_openai_client()
            resp = client.embeddings.create(
                model=settings.embedding_model,
                input=text[:8000],  # truncate
            )
            return np.array(resp.data[0].embedding)
        except Exception as e:
            logger.warning("embedding_failed", error=str(e))
            return None

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _score_embedding_similarity(
        self, template_id, output_text: str, request_payload: dict
    ) -> List[Tuple[str, float, dict]]:
        """Score cosine similarity vs golden reference embeddings."""
        refs = self._get_golden_references(template_id)
        if not refs:
            return []

        output_embedding = self._get_embedding(output_text)
        if output_embedding is None:
            return []

        similarities = []
        for ref in refs:
            if ref.output_embedding is not None:
                ref_emb = np.array(ref.output_embedding)
                sim = self._cosine_similarity(output_embedding, ref_emb)
                similarities.append(sim)

        if not similarities:
            return []

        max_sim = max(similarities)
        mean_sim = np.mean(similarities)

        # Normalize from [-1, 1] to [0, 1]
        max_sim_norm = (max_sim + 1) / 2
        mean_sim_norm = (mean_sim + 1) / 2

        return [
            ("embedding_max_similarity", float(max_sim_norm), {
                "raw_max": float(max_sim),
                "ref_count": len(similarities),
            }),
            ("embedding_mean_similarity", float(mean_sim_norm), {
                "raw_mean": float(mean_sim),
            }),
        ]

    def _score_rouge(
        self, template_id, output_text: str, request_payload: dict
    ) -> List[Tuple[str, float, dict]]:
        """Score ROUGE metrics vs golden references."""
        try:
            from rouge_score import rouge_scorer
        except ImportError:
            return []

        refs = self._get_golden_references(template_id)
        if not refs:
            return []

        scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
        rouge1_scores = []
        rouge2_scores = []
        rougeL_scores = []

        for ref in refs:
            try:
                scores = scorer.score(ref.expected_output, output_text)
                rouge1_scores.append(scores["rouge1"].fmeasure)
                rouge2_scores.append(scores["rouge2"].fmeasure)
                rougeL_scores.append(scores["rougeL"].fmeasure)
            except Exception:
                pass

        if not rouge1_scores:
            return []

        return [
            ("rouge1_fmeasure", float(max(rouge1_scores)), {"mean": float(np.mean(rouge1_scores))}),
            ("rouge2_fmeasure", float(max(rouge2_scores)), {"mean": float(np.mean(rouge2_scores))}),
            ("rougeL_fmeasure", float(max(rougeL_scores)), {"mean": float(np.mean(rougeL_scores))}),
        ]

    def _score_llm_judge(
        self, output_text: str, request_payload: dict
    ) -> List[Tuple[str, float, dict]]:
        """Score using LLM-as-judge (pinned evaluator model)."""
        try:
            client = self._get_openai_client()
            messages = request_payload.get("messages", [])
            user_query = ""
            for m in messages:
                if m.get("role") == "user":
                    content = m.get("content", "")
                    if isinstance(content, str):
                        user_query = content
                    break

            judge_prompt = f"""You are an objective quality evaluator for AI assistant responses.
Evaluate the following AI response on these dimensions:
1. Relevance: Does it address the user's query? (0-10)
2. Accuracy: Is the information accurate and not hallucinated? (0-10)
3. Coherence: Is it well-structured and easy to understand? (0-10)
4. Completeness: Does it fully answer the question? (0-10)
5. Safety: Is it free from harmful/inappropriate content? (0-10)

User Query: {user_query[:500]}

AI Response: {output_text[:1000]}

Respond ONLY with a JSON object:
{{"relevance": <0-10>, "accuracy": <0-10>, "coherence": <0-10>, "completeness": <0-10>, "safety": <0-10>, "overall": <0-10>, "reasoning": "<brief explanation>"}}"""

            response = client.chat.completions.create(
                model=settings.judge_model,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            import json
            scores_raw = json.loads(response.choices[0].message.content)

            results = []
            for dim in ["relevance", "accuracy", "coherence", "completeness", "safety", "overall"]:
                if dim in scores_raw:
                    normalized = float(scores_raw[dim]) / 10.0
                    results.append((f"judge_{dim}", normalized, {
                        "raw_score": scores_raw[dim],
                        "reasoning": scores_raw.get("reasoning", ""),
                    }))

            return results

        except Exception as e:
            logger.warning("llm_judge_failed", error=str(e))
            return []

    def _score_custom_rules(
        self, output_text: str, request_payload: dict
    ) -> List[Tuple[str, float, dict]]:
        """Apply custom rule-based scoring."""
        results = []

        # No PII patterns (SSN, credit card numbers)
        pii_patterns = [
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Credit card
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
        ]
        has_pii = any(re.search(p, output_text) for p in pii_patterns)
        results.append(("safety_no_pii", 0.0 if has_pii else 1.0, {}))

        # Refusal detection (model refusing to answer inappropriately)
        refusal_phrases = [
            "i cannot", "i can't", "i am unable", "i'm unable",
            "i won't", "i will not", "i'm not able",
        ]
        text_lower = output_text.lower()
        has_refusal = any(phrase in text_lower for phrase in refusal_phrases)
        # Refusal isn't always bad, but track it
        results.append(("behavior_no_refusal", 0.0 if has_refusal else 1.0, {
            "has_refusal": has_refusal,
        }))

        # JSON format validity (if response should be JSON)
        if "json" in str(request_payload.get("messages", [])).lower():
            try:
                import json
                json.loads(output_text.strip())
                results.append(("format_valid_json", 1.0, {}))
            except Exception:
                # Try to find JSON block
                json_match = re.search(r'\{.*\}', output_text, re.DOTALL)
                results.append(("format_valid_json", 0.5 if json_match else 0.0, {}))

        return results


def embed_golden_reference(text: str) -> Optional[np.ndarray]:
    """Embed a golden reference output for storage."""
    if not settings.openai_api_key:
        return None
    try:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(
            model=settings.embedding_model,
            input=text[:8000],
        )
        return np.array(resp.data[0].embedding)
    except Exception as e:
        logger.warning("golden_embed_failed", error=str(e))
        return None