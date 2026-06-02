"""
Root-cause classifier for flaky tests.

Uses a two-tier approach:
1. Rule-based classifier: high-confidence regex patterns for known failure signatures
2. ML classifier: DistilBERT-based model (with graceful fallback to rule-based if model unavailable)

Classifies failures into: timing, concurrency, environment, state_leakage, unknown
"""
import re
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass
class ClassificationResult:
    primary_cause: str
    confidence: float
    secondary_causes: List[Dict]
    evidence: Dict
    classifier_version: str


# Rule-based patterns for each root cause category
TIMING_PATTERNS = [
    (r"timeout|timed?\s*out", 0.85),
    (r"sleep\s*\(|asyncio\.sleep|time\.sleep", 0.70),
    (r"waitfor|wait_for|wait_until", 0.75),
    (r"expected.*within\s+\d+\s*(ms|seconds?|s\b)", 0.80),
    (r"element.*not.*appear|not.*visible.*timeout", 0.80),
    (r"deadline.exceeded|context.*deadline", 0.85),
    (r"took\s+\d+.*expected.*\d+", 0.65),
    (r"response.*too.*slow|slow.*response", 0.60),
    (r"elapsed.*exceeded|exceeded.*elapsed", 0.75),
    (r"StaleElementReference", 0.70),
    (r"EventuallyConsistency|eventually\s+consistent", 0.75),
]

CONCURRENCY_PATTERNS = [
    (r"deadlock|dead.lock", 0.90),
    (r"race.condition|data.race", 0.90),
    (r"concurrent.*access|thread.*safe", 0.80),
    (r"mutex|semaphore|lock.*contention", 0.75),
    (r"parallel.*fail|worker.*collision", 0.70),
    (r"already.*locked|lock.*acquired", 0.75),
    (r"ThreadSanitizer|tsan|TSAN", 0.95),
    (r"concurrent.*modification|ConcurrentModification", 0.85),
    (r"atomic.*fail|non.atomic", 0.75),
    (r"goroutine.*panic|goroutine.*leak", 0.80),
]

ENVIRONMENT_PATTERNS = [
    (r"connection.*refused|ECONNREFUSED", 0.80),
    (r"no.*such.*file|file.*not.*found|FileNotFound", 0.70),
    (r"environment.*variable|env.*var.*missing", 0.75),
    (r"ENOENT|EACCES|permission.*denied", 0.75),
    (r"docker.*not.*running|container.*exit", 0.85),
    (r"network.*unreachable|host.*unreachable", 0.80),
    (r"service.*unavailable|503|502", 0.70),
    (r"out.*of.*memory|OOM|MemoryError", 0.80),
    (r"disk.*full|no.*space.*left", 0.85),
    (r"port.*in.*use|EADDRINUSE|address.*already.*in.*use", 0.85),
    (r"SSL.*error|certificate.*expired|TLS.*handshake", 0.75),
    (r"import.*error|module.*not.*found|ModuleNotFoundError", 0.65),
    (r"CI.*environment|runner.*terminated", 0.70),
    (r"kubectl.*fail|k8s.*error", 0.70),
]

STATE_LEAKAGE_PATTERNS = [
    (r"already.*exists|duplicate.*key|unique.*constraint", 0.80),
    (r"left.*over.*data|leftover.*state|dirty.*state", 0.80),
    (r"database.*not.*clean|test.*isolation", 0.75),
    (r"setUp.*fail|tearDown.*fail", 0.70),
    (r"fixture.*not.*reset|fixture.*leak", 0.75),
    (r"global.*state|shared.*state|mutable.*global", 0.70),
    (r"previous.*test.*affect|test.*order.*depend", 0.80),
    (r"transaction.*not.*rolled.*back|uncommitted.*change", 0.85),
    (r"mock.*not.*reset|patch.*leak", 0.75),
    (r"static.*variable|singleton.*state", 0.65),
    (r"IntegrityError|ForeignKeyViolation|UniqueViolation", 0.80),
]


def match_patterns(
    text: str, patterns: List[Tuple[str, float]]
) -> Tuple[float, List[str]]:
    """
    Match text against patterns, return (max_confidence, matched_patterns).
    """
    matched = []
    max_conf = 0.0
    text_lower = text.lower()
    
    for pattern, confidence in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matched.append(pattern)
            max_conf = max(max_conf, confidence)
    
    return max_conf, matched


def classify_rule_based(log_text: str, error_message: str = "") -> ClassificationResult:
    """
    Rule-based classifier: fast, interpretable, high-precision for known patterns.
    """
    combined = f"{log_text or ''}\n{error_message or ''}"
    
    category_scores = {}
    category_evidence = {}
    
    for cause, patterns in [
        ("timing", TIMING_PATTERNS),
        ("concurrency", CONCURRENCY_PATTERNS),
        ("environment", ENVIRONMENT_PATTERNS),
        ("state_leakage", STATE_LEAKAGE_PATTERNS),
    ]:
        score, matched = match_patterns(combined, patterns)
        category_scores[cause] = score
        category_evidence[cause] = matched
    
    # Find primary cause
    best_cause = max(category_scores, key=lambda k: category_scores[k])
    best_score = category_scores[best_cause]
    
    if best_score < 0.3:
        # No confident classification
        return ClassificationResult(
            primary_cause="unknown",
            confidence=0.3,
            secondary_causes=[],
            evidence={"patterns": [], "method": "rule_based"},
            classifier_version="rule_based_v1",
        )
    
    # Secondary causes: anything with score > 0.2 that isn't primary
    secondary = []
    for cause, score in sorted(category_scores.items(), key=lambda x: -x[1]):
        if cause != best_cause and score > 0.2:
            secondary.append({
                "cause": cause,
                "confidence": round(score, 3),
                "evidence": category_evidence[cause],
            })
    
    return ClassificationResult(
        primary_cause=best_cause,
        confidence=round(best_score, 3),
        secondary_causes=secondary[:3],
        evidence={
            "patterns_matched": category_evidence[best_cause],
            "all_scores": {k: round(v, 3) for k, v in category_scores.items()},
            "method": "rule_based",
        },
        classifier_version="rule_based_v1",
    )


class MLClassifier:
    """
    DistilBERT-based classifier wrapper with lazy loading and graceful fallback.
    Uses a zero-shot or fine-tuned classifier on failure log text.
    """
    
    def __init__(self):
        self._pipeline = None
        self._available = False
        self._attempted_load = False
    
    def _try_load(self):
        """Lazily load the model, falling back to rule-based if unavailable."""
        if self._attempted_load:
            return
        self._attempted_load = True
        
        try:
            from transformers import pipeline
            # Use zero-shot classification as a proxy for the fine-tuned model
            # In production, this would be a fine-tuned DistilBERT on labeled data
            self._pipeline = pipeline(
                "zero-shot-classification",
                model="cross-encoder/nli-distilroberta-base",
                device=-1,  # CPU
            )
            self._available = True
            logger.info("ml_classifier_loaded", model="nli-distilroberta-base")
        except Exception as e:
            logger.warning("ml_classifier_unavailable", error=str(e))
            self._available = False
    
    def classify(self, text: str, max_length: int = 512) -> Optional[ClassificationResult]:
        """
        Classify using ML model. Returns None if unavailable (triggers rule-based fallback).
        """
        self._try_load()
        if not self._available or not self._pipeline:
            return None
        
        try:
            # Truncate text to avoid token limit issues
            truncated = text[:2000]
            
            candidate_labels = [
                "timing issue or timeout",
                "concurrency or thread safety problem",
                "environment or infrastructure failure",
                "test state leakage or test isolation problem",
            ]
            
            result = self._pipeline(truncated, candidate_labels, multi_label=True)
            
            label_to_cause = {
                "timing issue or timeout": "timing",
                "concurrency or thread safety problem": "concurrency",
                "environment or infrastructure failure": "environment",
                "test state leakage or test isolation problem": "state_leakage",
            }
            
            scores = {
                label_to_cause[label]: score
                for label, score in zip(result["labels"], result["scores"])
            }
            
            best_cause = max(scores, key=lambda k: scores[k])
            best_score = scores[best_cause]
            
            secondary = [
                {"cause": c, "confidence": round(s, 3)}
                for c, s in sorted(scores.items(), key=lambda x: -x[1])
                if c != best_cause and s > 0.2
            ]
            
            return ClassificationResult(
                primary_cause=best_cause,
                confidence=round(best_score, 3),
                secondary_causes=secondary,
                evidence={
                    "all_scores": {k: round(v, 3) for k, v in scores.items()},
                    "method": "ml_zero_shot",
                },
                classifier_version="nli-distilroberta-v1",
            )
        except Exception as e:
            logger.warning("ml_classification_failed", error=str(e))
            return None


# Module-level classifier instance
_ml_classifier = MLClassifier()


def classify_failure(
    log_output: str = "",
    error_message: str = "",
    stack_trace: str = "",
    use_ml: bool = True,
) -> ClassificationResult:
    """
    Main classification entry point. Tries ML first, falls back to rule-based.
    Combines both signals when both are available.
    """
    combined_text = " ".join(filter(None, [log_output, error_message, stack_trace]))
    
    # Try ML classification
    ml_result = None
    if use_ml:
        ml_result = _ml_classifier.classify(combined_text)
    
    # Always run rule-based
    rule_result = classify_rule_based(combined_text, error_message)
    
    if ml_result is None:
        # Use rule-based only
        return rule_result
    
    # Combine: if both agree, boost confidence; if they disagree, use higher confidence
    if ml_result.primary_cause == rule_result.primary_cause:
        # Agreement: average confidence, slightly boosted
        combined_confidence = min(
            1.0,
            (ml_result.confidence * 0.6 + rule_result.confidence * 0.4) * 1.1
        )
        result = ClassificationResult(
            primary_cause=ml_result.primary_cause,
            confidence=round(combined_confidence, 3),
            secondary_causes=ml_result.secondary_causes,
            evidence={
                **rule_result.evidence,
                "ml_scores": ml_result.evidence.get("all_scores", {}),
                "method": "combined_agreement",
            },
            classifier_version=f"combined_{ml_result.classifier_version}_{rule_result.classifier_version}",
        )
    else:
        # Disagreement: use whichever has higher confidence
        if ml_result.confidence >= rule_result.confidence:
            result = ml_result
            result.evidence["rule_based_cause"] = rule_result.primary_cause
            result.evidence["method"] = "combined_ml_wins"
        else:
            result = rule_result
            result.evidence["ml_cause"] = ml_result.primary_cause
            result.evidence["method"] = "combined_rules_win"
    
    return result