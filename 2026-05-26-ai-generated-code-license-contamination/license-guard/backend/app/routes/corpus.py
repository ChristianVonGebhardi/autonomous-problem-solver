import uuid
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CorpusSnippet
from app.schemas import CorpusSnippetCreate
from app.detector import tokenize_code, compute_minhash, compute_embedding
from app.license_taxonomy import classify_license

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/corpus", status_code=201)
async def add_corpus_snippet(
    snippet: CorpusSnippetCreate,
    db: Session = Depends(get_db)
):
    """Add a code snippet to the FOSS corpus for comparison."""
    risk_tier, _ = classify_license(snippet.license_spdx)
    
    # Compute fingerprints
    tokens = tokenize_code(snippet.code_snippet, snippet.language)
    minhash = compute_minhash(tokens)
    embedding = compute_embedding(snippet.code_snippet)
    
    corpus_snippet = CorpusSnippet(
        id=str(uuid.uuid4()),
        source_repo=snippet.source_repo,
        source_file=snippet.source_file,
        license_spdx=snippet.license_spdx,
        license_risk_tier=risk_tier,
        language=snippet.language,
        code_snippet=snippet.code_snippet,
        ast_tokens={"tokens": tokens[:100]},  # Store first 100 tokens
        minhash_signature=minhash,
        embedding=embedding,
    )
    db.add(corpus_snippet)
    db.commit()
    db.refresh(corpus_snippet)
    
    return {
        "id": corpus_snippet.id,
        "license_spdx": corpus_snippet.license_spdx,
        "license_risk_tier": corpus_snippet.license_risk_tier,
        "tokens_count": len(tokens),
    }


@router.get("/corpus/stats")
async def get_corpus_stats(db: Session = Depends(get_db)):
    """Get corpus statistics."""
    from sqlalchemy import func
    
    total = db.query(func.count(CorpusSnippet.id)).scalar()
    by_tier = db.query(
        CorpusSnippet.license_risk_tier,
        func.count(CorpusSnippet.id)
    ).group_by(CorpusSnippet.license_risk_tier).all()
    
    by_license = db.query(
        CorpusSnippet.license_spdx,
        func.count(CorpusSnippet.id)
    ).group_by(CorpusSnippet.license_spdx).order_by(
        func.count(CorpusSnippet.id).desc()
    ).limit(10).all()
    
    return {
        "total_snippets": total,
        "by_risk_tier": [{"tier": t, "count": c} for t, c in by_tier],
        "top_licenses": [{"license": l, "count": c} for l, c in by_license],
    }