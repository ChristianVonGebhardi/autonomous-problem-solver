"""
LLM-powered Explainability Service

Generates human-readable drift summaries ONLY when an alert is triggered.
Gated behind alert signal to control cost.

Supports OpenAI GPT-4o. Falls back to a rule-based template if no API key.
"""

import os
import logging
import json
from typing import Optional, Dict, Any
import hashlib

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def _generate_rule_based_explanation(
    workflow_id: str,
    composite_score: float,
    structural_score: float,
    semantic_score: float,
    distributional_score: float,
    structural_details: Dict[str, Any],
    semantic_details: Dict[str, Any],
    distributional_details: Dict[str, Any],
) -> str:
    """Generate a template-based explanation without LLM."""
    lines = [
        f"⚠️ Behavioral drift detected in workflow '{workflow_id}'",
        f"",
        f"Composite drift score: {composite_score:.2f}",
        f"",
        "Signal breakdown:",
    ]

    # Structural
    if structural_score > 0.3:
        current_tools = structural_details.get("current_tools", [])
        tool_dist = structural_details.get("tool_sequence_distance", 0)
        lines.append(
            f"  • Structural drift ({structural_score:.2f}): Tool sequence has changed "
            f"significantly (edit distance: {tool_dist:.2f}). "
            f"Current tools: {current_tools}"
        )
    else:
        lines.append(f"  • Structural: Low drift ({structural_score:.2f}) — tool sequences stable")

    # Semantic
    if semantic_score > 0.3:
        dist = semantic_details.get("distance_to_centroid", 0)
        z = semantic_details.get("z_score", 0)
        lines.append(
            f"  • Semantic drift ({semantic_score:.2f}): Agent reasoning has moved "
            f"{dist:.3f} cosine distance from baseline centroid (z={z:.1f}σ)"
        )
    else:
        lines.append(f"  • Semantic: Low drift ({semantic_score:.2f}) — reasoning aligned with baseline")

    # Distributional
    if distributional_score > 0.3:
        conf_data = distributional_details.get("details", {}).get("confidence", {})
        if conf_data:
            lines.append(
                f"  • Distributional drift ({distributional_score:.2f}): "
                f"Confidence score trend: current={conf_data.get('current', 'N/A'):.2f}, "
                f"baseline_mean={conf_data.get('baseline_mean', 'N/A'):.2f}"
            )
        else:
            lines.append(f"  • Distributional drift ({distributional_score:.2f}): Output distribution has shifted")
    else:
        lines.append(f"  • Distributional: Low drift ({distributional_score:.2f}) — outputs stable")

    lines.append("")
    lines.append("Recommended action: Review recent agent configuration changes, model updates, or prompt modifications.")

    return "\n".join(lines)


async def generate_explanation(
    workflow_id: str,
    run_id: str,
    composite_score: float,
    alert_level: str,
    structural_score: float,
    semantic_score: float,
    distributional_score: float,
    structural_details: Dict[str, Any],
    semantic_details: Dict[str, Any],
    distributional_details: Dict[str, Any],
) -> str:
    """
    Generate a human-readable explanation for a drift alert.

    Uses GPT-4o if OPENAI_API_KEY is set, otherwise falls back to
    rule-based template generation.
    """
    if not OPENAI_API_KEY:
        logger.debug("No OPENAI_API_KEY — using rule-based explanation")
        return _generate_rule_based_explanation(
            workflow_id=workflow_id,
            composite_score=composite_score,
            structural_score=structural_score,
            semantic_score=semantic_score,
            distributional_score=distributional_score,
            structural_details=structural_details,
            semantic_details=semantic_details,
            distributional_details=distributional_details,
        )

    # LLM-powered explanation
    try:
        import httpx

        context = {
            "workflow_id": workflow_id,
            "run_id": run_id,
            "alert_level": alert_level,
            "scores": {
                "composite": composite_score,
                "structural": structural_score,
                "semantic": semantic_score,
                "distributional": distributional_score,
            },
            "structural_details": structural_details,
            "semantic_details": semantic_details,
            "distributional_details": distributional_details,
        }

        prompt = f"""You are a behavioral drift analyst for enterprise AI agent workflows.

A drift alert has been triggered. Analyze the following drift data and generate a concise, actionable explanation (3-5 sentences) for an engineering team. Focus on:
1. Which signal layer shows the most significant drift
2. What this likely means about agent behavior change
3. What the team should investigate

Drift data:
{json.dumps(context, indent=2, default=str)}

Write a professional, technical summary. Be specific about the numbers."""

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.3,
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                logger.warning(f"OpenAI API error {response.status_code} — falling back to template")
                return _generate_rule_based_explanation(
                    workflow_id=workflow_id,
                    composite_score=composite_score,
                    structural_score=structural_score,
                    semantic_score=semantic_score,
                    distributional_score=distributional_score,
                    structural_details=structural_details,
                    semantic_details=semantic_details,
                    distributional_details=distributional_details,
                )

    except Exception as e:
        logger.error(f"LLM explanation failed: {e}")
        return _generate_rule_based_explanation(
            workflow_id=workflow_id,
            composite_score=composite_score,
            structural_score=structural_score,
            semantic_score=semantic_score,
            distributional_score=distributional_score,
            structural_details=structural_details,
            semantic_details=semantic_details,
            distributional_details=distributional_details,
        )