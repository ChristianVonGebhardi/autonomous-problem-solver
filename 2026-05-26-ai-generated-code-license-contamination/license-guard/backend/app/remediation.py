"""
Remediation advisor: uses LLM to suggest license-compatible rewrites
"""
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_remediation_suggestion(
    original_code: str,
    license_spdx: str,
    risk_tier: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Use OpenAI to suggest a license-compatible rewrite.
    Falls back to template-based suggestions if no API key.
    """
    if api_key:
        return _openai_suggestion(original_code, license_spdx, risk_tier, api_key)
    else:
        return _template_suggestion(original_code, license_spdx, risk_tier)


def _openai_suggestion(
    original_code: str,
    license_spdx: str,
    risk_tier: str,
    api_key: str
) -> Dict[str, Any]:
    """Get remediation suggestion from OpenAI."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        prompt = f"""You are a software licensing expert and senior developer. 
        
The following code snippet has been flagged as potentially contaminated by a {license_spdx} license (risk tier: {risk_tier}):

```
{original_code[:2000]}
```

Please provide:
1. A clean, original reimplementation that achieves the same functionality without copying from the original source
2. A brief explanation of what changes were made and why
3. Confirm the suggested code is free from {license_spdx} contamination

Format your response as:
SUGGESTED_CODE:
```
[your code here]
```

EXPLANATION:
[your explanation here]
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        
        content = response.choices[0].message.content
        suggested_code, explanation = _parse_llm_response(content)
        
        return {
            "suggested_code": suggested_code,
            "explanation": explanation,
            "model_used": "gpt-4o-mini",
            "status": "completed"
        }
    
    except Exception as e:
        logger.error(f"OpenAI remediation failed: {e}")
        return _template_suggestion(original_code, license_spdx, risk_tier)


def _parse_llm_response(content: str) -> tuple:
    """Parse LLM response into code and explanation."""
    suggested_code = ""
    explanation = ""
    
    if "SUGGESTED_CODE:" in content:
        parts = content.split("SUGGESTED_CODE:")
        if len(parts) > 1:
            code_part = parts[1]
            # Extract code from markdown blocks
            import re
            code_match = re.search(r'```(?:\w+)?\n(.*?)\n```', code_part, re.DOTALL)
            if code_match:
                suggested_code = code_match.group(1).strip()
    
    if "EXPLANATION:" in content:
        parts = content.split("EXPLANATION:")
        if len(parts) > 1:
            explanation = parts[1].strip()
    
    if not suggested_code:
        # Try to extract any code block
        import re
        code_match = re.search(r'```(?:\w+)?\n(.*?)\n```', content, re.DOTALL)
        if code_match:
            suggested_code = code_match.group(1).strip()
    
    if not explanation:
        explanation = content if not suggested_code else content.replace(f"```{suggested_code}```", "").strip()
    
    return suggested_code, explanation


def _template_suggestion(
    original_code: str,
    license_spdx: str,
    risk_tier: str
) -> Dict[str, Any]:
    """Template-based remediation suggestion (fallback when no OpenAI key)."""
    
    explanations = {
        "high": f"""This code matches {license_spdx} which has strong copyleft requirements.
        
Actions required:
1. Do NOT include this code in your proprietary codebase
2. Rewrite the functionality from scratch without referencing the original implementation
3. Document the business logic requirements and implement independently
4. Consider using a permissively-licensed alternative library

To rewrite: Focus on the algorithm's input/output contract, not the implementation details.
Write unit tests first, then implement to pass the tests using only your own logic.""",
        
        "medium": f"""This code matches {license_spdx} which has weak copyleft requirements.
        
Actions required:
1. Check if you can use the library as a dependency (with LGPL, you may be able to)
2. If embedding the code directly, add proper license notices
3. Alternatively, rewrite to avoid the specific licensed implementation
4. Consult your legal team about your distribution model""",
        
        "low": f"""This code matches {license_spdx} which is permissive.
        
Actions required:
1. Add appropriate copyright notice and attribution in your NOTICE or LICENSE file
2. Include the original license text if required
3. The code may generally be used freely with proper attribution"""
    }
    
    explanation = explanations.get(risk_tier, f"Review the {license_spdx} license terms before use.")
    
    return {
        "suggested_code": None,
        "explanation": explanation,
        "model_used": "template",
        "status": "template_only",
        "note": "Add OPENAI_API_KEY to .env for AI-generated code suggestions"
    }