import json
from typing import List, Dict, Any, Optional, Tuple
import structlog
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.config import get_settings
from app.models import Contract, ContractClause, Message, Violation, SeverityLevel, ViolationStatus
from app.services.embeddings import embed_text, get_openai_client

settings = get_settings()
logger = structlog.get_logger()


SCOPE_ANALYSIS_PROMPT = """You are a legal and contract analysis expert specializing in freelance and agency contracts.

Your task: Analyze a client message against the signed contract to detect scope creep.

CONTRACT CLAUSES (most relevant sections):
{contract_clauses}

CLIENT MESSAGE:
{message}

Analyze whether this message requests work that falls OUTSIDE the contract's defined scope.

Respond with a JSON object in this exact format:
{{
  "violation_score": <float 0.0-1.0, where 1.0 = definitely out of scope>,
  "severity": <"low"|"medium"|"high"|"critical">,
  "is_violation": <true|false>,
  "summary": "<1-2 sentence plain English summary of what was detected>",
  "out_of_scope_work": "<specific description of what was requested that is out of scope>",
  "cited_clauses": [
    {{"text": "<relevant contract clause excerpt>", "relevance": "<why this clause applies>"}}
  ],
  "estimated_hours": <float, your best estimate of additional hours this would take>,
  "reasoning": "<brief explanation of your analysis>"
}}

Guidelines:
- A score of 0.0-0.3 means in-scope or unclear
- A score of 0.3-0.6 means possibly out of scope (borderline)  
- A score of 0.6-0.8 means likely out of scope
- A score of 0.8-1.0 means definitely out of scope
- Only flag violations when the score is >= 0.5
- Be specific about which contract language is being violated
- Estimate hours realistically based on the type of work requested"""


CHANGE_ORDER_PROMPT = """You are a professional freelance business consultant helping draft a change order document.

CONTEXT:
- Freelancer/Agency: {freelancer_name}
- Client: {client_name}
- Project: {project_title}
- Hourly Rate: ${hourly_rate}/hour
- Detected Out-of-Scope Work: {out_of_scope_work}
- Estimated Hours: {estimated_hours}
- Original Contract Clause Violated: {cited_clause}

Draft a professional, firm but friendly change order. Respond with JSON:
{{
  "title": "<concise change order title>",
  "description": "<2-3 sentence description of the situation and why a change order is needed>",
  "scope_addition": "<detailed description of the additional work being added>",
  "terms": "<payment terms and timeline for this change order>",
  "professional_note": "<optional friendly note to maintain client relationship>"
}}"""


async def get_relevant_clauses(
    db: AsyncSession,
    contract_id: str,
    message_embedding: List[float],
    top_k: int = 5
) -> List[ContractClause]:
    """Retrieve most relevant contract clauses via cosine similarity."""
    # Use pgvector cosine distance operator
    query = text("""
        SELECT id, contract_id, chunk_index, text, clause_type,
               1 - (embedding <=> cast(:embedding as vector)) AS similarity
        FROM contract_clauses
        WHERE contract_id = :contract_id
          AND embedding IS NOT NULL
        ORDER BY embedding <=> cast(:embedding as vector)
        LIMIT :top_k
    """)
    
    result = await db.execute(
        query,
        {
            "embedding": str(message_embedding),
            "contract_id": str(contract_id),
            "top_k": top_k
        }
    )
    rows = result.fetchall()
    
    clauses = []
    for row in rows:
        clause = ContractClause()
        clause.id = row[0]
        clause.contract_id = row[1]
        clause.chunk_index = row[2]
        clause.text = row[3]
        clause.clause_type = row[4]
        clauses.append(clause)
    
    return clauses


async def analyze_message_for_scope_creep(
    db: AsyncSession,
    message: Message,
    contract: Contract,
) -> Optional[Violation]:
    """
    Main scope analysis pipeline:
    1. Embed the message
    2. Retrieve relevant contract clauses
    3. Call GPT-4o for analysis
    4. Create violation record if detected
    """
    logger.info("analyzing_message", message_id=str(message.id), contract_id=str(contract.id))
    
    # 1. Embed message
    message_embedding = await embed_text(message.content)
    
    # 2. Retrieve relevant clauses
    relevant_clauses = await get_relevant_clauses(
        db, str(contract.id), message_embedding, top_k=6
    )
    
    if not relevant_clauses:
        logger.warning("no_clauses_found", contract_id=str(contract.id))
        # Fall back to using raw contract text
        clauses_text = contract.raw_text[:3000] if contract.raw_text else "No contract text available"
    else:
        clauses_text = "\n\n---\n\n".join([
            f"[Clause {i+1} - {c.clause_type}]:\n{c.text}"
            for i, c in enumerate(relevant_clauses)
        ])
    
    # 3. Call GPT-4o
    client = get_openai_client()
    
    prompt = SCOPE_ANALYSIS_PROMPT.format(
        contract_clauses=clauses_text,
        message=message.content,
    )
    
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a contract analysis expert. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    
    result = json.loads(response.choices[0].message.content)
    logger.info("analysis_result", violation_score=result.get("violation_score"), is_violation=result.get("is_violation"))
    
    # 4. Create violation record if score >= 0.5
    if result.get("is_violation") and result.get("violation_score", 0) >= 0.5:
        # Get owner's hourly rate
        from sqlalchemy import select
        from app.models import User
        user_result = await db.execute(select(User).where(User.id == contract.owner_id))
        user = user_result.scalar_one_or_none()
        hourly_rate = user.hourly_rate if user else settings.hourly_rate if hasattr(settings, 'hourly_rate') else 150.0
        
        estimated_hours = result.get("estimated_hours", 2.0) or 2.0
        
        violation = Violation(
            contract_id=contract.id,
            message_id=message.id,
            owner_id=contract.owner_id,
            violation_score=result["violation_score"],
            severity=SeverityLevel(result.get("severity", "medium")),
            summary=result["summary"],
            out_of_scope_work=result["out_of_scope_work"],
            cited_clauses=result.get("cited_clauses", []),
            estimated_hours=estimated_hours,
            estimated_cost=estimated_hours * hourly_rate,
            status=ViolationStatus.PENDING,
        )
        db.add(violation)
        await db.commit()
        await db.refresh(violation)
        
        logger.info("violation_created", violation_id=str(violation.id))
        return violation
    
    return None


async def generate_change_order_content(
    freelancer_name: str,
    client_name: str,
    project_title: str,
    hourly_rate: float,
    out_of_scope_work: str,
    estimated_hours: float,
    cited_clause: str,
) -> Dict[str, Any]:
    """Generate professional change order content via GPT-4o."""
    client = get_openai_client()
    
    prompt = CHANGE_ORDER_PROMPT.format(
        freelancer_name=freelancer_name,
        client_name=client_name,
        project_title=project_title,
        hourly_rate=hourly_rate,
        out_of_scope_work=out_of_scope_work,
        estimated_hours=estimated_hours,
        cited_clause=cited_clause,
    )
    
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a professional business consultant. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    
    return json.loads(response.choices[0].message.content)