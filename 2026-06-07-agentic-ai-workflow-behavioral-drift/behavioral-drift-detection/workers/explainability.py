"""
LLM-Powered Drift Explainability Service

Only called when an alert is triggered (composite score >= threshold).
Gating behind real signal keeps LLM API costs negligible at scale.

Uses OpenAI GPT-4o (or GPT-3.5 as fallback) to generate human-readable
summaries of detected drift — what changed, why it matters, what to investigate.
"""

from __future__ import annotations

import json
from typing import Optional

import structlog

from api.config import settings

logger = structlog.get_logger(__name__)


def _build_prompt(
    workflow_name: str,
    composite_score: float,
    severity: str,
    structural_detail: dict,
    semantic_detail: dict,
    distributional_detail: dict,
    run_tool_sequence: list[str],
    baseline_sequences: list[list[str]],
) -> str:
    prompt = f"""You are an AI observability expert analyzing behavioral drift in an enterprise agentic AI workflow.

WORKFLOW: {workflow_name}
DRIFT SEVERITY: {severity.upper()} (composite score: {composite_score:.3f})

STRUCTURAL DRIFT ANALYSIS:
- Edit distance to nearest baseline: {structural_detail.get('min_edit_distance', 'N/A')}
- Step count deviation: {structural_detail.get('step_count_deviation', 'N/A')}
- Current tool sequence: {run_tool_sequence}
- Unexpected tools: {structural_detail.get('unexpected_tools', [])}
- Missing tools: {structural_detail.get('missing_tools', [])}

SEMANTIC DRIFT ANALYSIS:
- Cosine distance from baseline reasoning: {semantic_detail.get('min_cosine_distance', 'N/A')}
- Step outputs analyzed: {semantic_detail.get('step_output_count', 'N/A')}

DISTRIBUTIONAL DRIFT ANALYSIS:
- Signal ({distributional_detail.get('signal_source', 'unknown')}): {distributional_detail.get('signal_value', 'N/A')}
- CUSUM positive accumulator: {distributional_detail.get('cusum_pos', 'N/A')}
- CUSUM negative accumulator: {distributional_detail.get('cusum_neg', 'N/A')}
- CUSUM alarm triggered: {distributional_detail.get('cusum_alarm', False)}
- Baseline mean: {distributional_detail.get('baseline_mean', 'N/A')}

Write a concise (3-5 sentence) drift alert explanation for an engineering team. Focus on:
1. What specifically changed from the baseline behavior
2. Which signal layer shows the strongest drift signal
3. What the team should investigate first

Be specific, actionable, and avoid generic statements."""

    return prompt


def generate_drift_explanation(
    workflow_name: str,
    composite_score: float,
    severity: str,
    structural_detail: Optional[dict],
    semantic_detail: Optional[dict],
    distributional_detail: Optional[dict],
    run_tool_sequence: list[str],
    baseline_sequences: list[list[str]],
) -> Optional[str]:
    """
    Generate a human-readable drift explanation using an LLM.
    
    Returns None if OpenAI API key is not configured or on any API error.
    The caller should treat None as "explanation unavailable" and not fail.
    """
    if not settings.openai_api_key:
        logger.info("llm_explanation_skipped", reason="no_api_key")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
    except ImportError:
        logger.warning("openai_not_installed")
        return None

    prompt = _build_prompt(
        workflow_name=workflow_name,
        composite_score=composite_score,
        severity=severity,
        structural_detail=structural_detail or {},
        semantic_detail=semantic_detail or {},
        distributional_detail=distributional_detail or {},
        run_tool_sequence=run_tool_sequence,
        baseline_sequences=baseline_sequences,
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI observability expert. Be concise and actionable.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        explanation = response.choices[0].message.content.strip()
        logger.info("llm_explanation_generated", severity=severity, tokens=response.usage.total_tokens)
        return explanation
    except Exception as exc:
        logger.warning("llm_explanation_failed", error=str(exc))
        return None