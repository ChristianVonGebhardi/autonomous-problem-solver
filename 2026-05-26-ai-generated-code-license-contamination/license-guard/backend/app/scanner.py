"""
Scan worker: orchestrates detection pipeline
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models import ScanJob, ScanMatch, CorpusSnippet
from app.detector import (
    CodeAnalysis, jaccard_similarity_from_minhash,
    cosine_similarity, compute_code_hash
)
from app.license_taxonomy import classify_license, get_highest_risk_tier, TIER_RECOMMENDATIONS

logger = logging.getLogger(__name__)


def find_corpus_matches(
    analysis: CodeAnalysis,
    db: Session,
    threshold: float = 0.75
) -> List[Dict[str, Any]]:
    """
    Find matching corpus snippets using multiple strategies:
    1. Exact hash match
    2. MinHash Jaccard similarity
    3. Semantic embedding similarity (via pgvector)
    """
    matches = []
    seen_corpus_ids = set()

    # Strategy 1: Exact hash match
    exact_matches = _find_exact_matches(analysis.code_hash, db)
    for match in exact_matches:
        if match['corpus_id'] not in seen_corpus_ids:
            seen_corpus_ids.add(match['corpus_id'])
            matches.append(match)

    # Strategy 2: MinHash similarity
    if analysis.minhash:
        minhash_matches = _find_minhash_matches(analysis, db, threshold)
        for match in minhash_matches:
            if match['corpus_id'] not in seen_corpus_ids:
                seen_corpus_ids.add(match['corpus_id'])
                matches.append(match)

    # Strategy 3: Semantic embedding similarity
    if analysis.embedding:
        semantic_matches = _find_semantic_matches(analysis, db, threshold)
        for match in semantic_matches:
            if match['corpus_id'] not in seen_corpus_ids:
                seen_corpus_ids.add(match['corpus_id'])
                matches.append(match)

    # Sort by similarity score descending
    matches.sort(key=lambda x: x['similarity_score'], reverse=True)
    return matches[:10]  # Return top 10 matches


def _find_exact_matches(code_hash: str, db: Session) -> List[Dict[str, Any]]:
    """Find exact matches using code hash."""
    results = []
    try:
        from app.detector import compute_code_hash
        snippets = db.query(CorpusSnippet).limit(1000).all()
        for snippet in snippets:
            snippet_hash = compute_code_hash(snippet.code_snippet)
            if snippet_hash == code_hash:
                results.append({
                    'corpus_id': snippet.id,
                    'match_type': 'exact',
                    'similarity_score': 1.0,
                    'license_spdx': snippet.license_spdx,
                    'license_risk_tier': snippet.license_risk_tier,
                    'matched_snippet': snippet.code_snippet,
                    'source_repo': snippet.source_repo,
                })
    except Exception as e:
        logger.error(f"Exact match search failed: {e}")
    return results


def _find_minhash_matches(
    analysis: CodeAnalysis,
    db: Session,
    threshold: float
) -> List[Dict[str, Any]]:
    """Find near-duplicate matches using MinHash Jaccard similarity."""
    results = []
    try:
        snippets = db.query(CorpusSnippet).filter(
            CorpusSnippet.minhash_signature.isnot(None)
        ).limit(500).all()

        for snippet in snippets:
            if snippet.minhash_signature:
                similarity = jaccard_similarity_from_minhash(
                    analysis.minhash,
                    snippet.minhash_signature
                )
                if similarity >= threshold:
                    results.append({
                        'corpus_id': snippet.id,
                        'match_type': 'near_duplicate',
                        'similarity_score': float(similarity),
                        'license_spdx': snippet.license_spdx,
                        'license_risk_tier': snippet.license_risk_tier,
                        'matched_snippet': snippet.code_snippet,
                        'source_repo': snippet.source_repo,
                    })
    except Exception as e:
        logger.error(f"MinHash match search failed: {e}")
    return results


def _find_semantic_matches(
    analysis: CodeAnalysis,
    db: Session,
    threshold: float
) -> List[Dict[str, Any]]:
    """Find semantic matches using vector similarity."""
    results = []
    try:
        # Try pgvector cosine search first
        try:
            from sqlalchemy import text
            embedding_str = '[' + ','.join(str(x) for x in analysis.embedding) + ']'
            sql = text("""
                SELECT id, license_spdx, license_risk_tier, code_snippet, source_repo,
                       1 - (embedding <=> :embedding::vector) as similarity
                FROM corpus_snippets
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> :embedding::vector
                LIMIT 10
            """)
            rows = db.execute(sql, {"embedding": embedding_str}).fetchall()

            for row in rows:
                if row.similarity >= threshold:
                    results.append({
                        'corpus_id': row.id,
                        'match_type': 'semantic',
                        'similarity_score': float(row.similarity),
                        'license_spdx': row.license_spdx,
                        'license_risk_tier': row.license_risk_tier,
                        'matched_snippet': row.code_snippet,
                        'source_repo': row.source_repo,
                    })
        except Exception as pgvector_err:
            logger.debug(f"pgvector query failed, falling back to manual cosine: {pgvector_err}")
            # Fallback: manual cosine similarity
            snippets = db.query(CorpusSnippet).filter(
                CorpusSnippet.embedding.isnot(None)
            ).limit(200).all()

            for snippet in snippets:
                if snippet.embedding is not None:
                    emb = snippet.embedding
                    if not isinstance(emb, list):
                        try:
                            emb = list(emb)
                        except Exception:
                            continue
                    sim = cosine_similarity(analysis.embedding, emb)
                    if sim >= threshold:
                        results.append({
                            'corpus_id': snippet.id,
                            'match_type': 'semantic',
                            'similarity_score': float(sim),
                            'license_spdx': snippet.license_spdx,
                            'license_risk_tier': snippet.license_risk_tier,
                            'matched_snippet': snippet.code_snippet,
                            'source_repo': snippet.source_repo,
                        })
    except Exception as e:
        logger.error(f"Semantic match search failed: {e}")
    return results


def process_scan_job(scan_job_id: str, database_url: str) -> Dict[str, Any]:
    """
    Main scan job processor - called by RQ worker.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import settings as app_settings

    engine = create_engine(database_url, pool_pre_ping=True)
    SessionFactory = sessionmaker(bind=engine)
    db = SessionFactory()

    try:
        # Fetch scan job
        scan_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
        if not scan_job:
            logger.error(f"Scan job not found: {scan_job_id}")
            return {"error": "Scan job not found"}

        # Update status
        scan_job.status = "processing"
        db.commit()

        logger.info(f"Processing scan job: {scan_job_id}")

        # Analyze code
        analysis = CodeAnalysis(scan_job.code_snippet, scan_job.language)

        # Find corpus matches
        # Import settings from config
        threshold = app_settings.similarity_threshold
        matches = find_corpus_matches(
            analysis,
            db,
            threshold=threshold
        )

        # Save matches to DB
        db_matches = []
        for match_data in matches:
            match = ScanMatch(
                id=str(uuid.uuid4()),
                scan_job_id=scan_job_id,
                corpus_snippet_id=match_data['corpus_id'],
                match_type=match_data['match_type'],
                similarity_score=match_data['similarity_score'],
                license_spdx=match_data['license_spdx'],
                license_risk_tier=match_data['license_risk_tier'],
                matched_snippet=match_data.get('matched_snippet', '')[:500],
                source_repo=match_data.get('source_repo', ''),
            )
            db.add(match)
            db_matches.append(match)

        # Determine overall risk tier
        risk_tiers = [m['license_risk_tier'] for m in matches]
        overall_tier = get_highest_risk_tier(risk_tiers) if risk_tiers else "clean"

        # Build result
        result = {
            "matches": [
                {
                    "match_id": m.id,
                    "match_type": m.match_type,
                    "similarity_score": m.similarity_score,
                    "license_spdx": m.license_spdx,
                    "license_risk_tier": m.license_risk_tier,
                    "source_repo": m.source_repo,
                }
                for m in db_matches
            ],
            "risk_tier": overall_tier,
            "recommendation": TIER_RECOMMENDATIONS.get(overall_tier, ""),
            "tokens_analyzed": len(analysis.tokens),
            "detection_methods": {
                "exact_match": any(m['match_type'] == 'exact' for m in matches),
                "minhash": analysis.minhash is not None,
                "semantic": analysis.embedding is not None,
            }
        }

        # Update scan job
        scan_job.status = "completed"
        scan_job.risk_tier = overall_tier
        scan_job.result = result
        scan_job.completed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(f"Scan completed: {scan_job_id}, risk_tier={overall_tier}, matches={len(matches)}")
        return result

    except Exception as e:
        logger.error(f"Scan job failed: {scan_job_id}, error: {e}", exc_info=True)
        try:
            scan_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
            if scan_job:
                scan_job.status = "failed"
                scan_job.result = {"error": str(e)}
                db.commit()
        except Exception:
            pass
        raise
    finally:
        db.close()