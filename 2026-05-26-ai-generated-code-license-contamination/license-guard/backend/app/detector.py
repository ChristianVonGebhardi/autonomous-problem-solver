"""
Core detection engine: AST parsing, MinHash LSH, and semantic similarity
"""
import re
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# Try importing tree-sitter
try:
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree-sitter not available, falling back to regex tokenization")

# Try importing datasketch
try:
    from datasketch import MinHash, MinHashLSH
    MINHASH_AVAILABLE = True
except ImportError:
    MINHASH_AVAILABLE = False
    logger.warning("datasketch not available")

# Try importing sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers not available")


# Singleton for the embedding model
_embedding_model = None


def get_embedding_model(model_name: str = "all-MiniLM-L6-v2"):
    global _embedding_model
    if _embedding_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
        try:
            _embedding_model = SentenceTransformer(model_name)
            logger.info(f"Loaded embedding model: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
    return _embedding_model


def tokenize_code(code: str, language: Optional[str] = None) -> List[str]:
    """
    Tokenize code into normalized tokens.
    Falls back to regex-based tokenization if tree-sitter is unavailable.
    """
    # Normalize whitespace
    code = re.sub(r'\s+', ' ', code.strip())
    
    # Try tree-sitter first
    if TREE_SITTER_AVAILABLE and language:
        try:
            tokens = _tree_sitter_tokenize(code, language)
            if tokens:
                return tokens
        except Exception as e:
            logger.debug(f"tree-sitter tokenization failed: {e}")
    
    # Fallback: regex-based tokenization
    return _regex_tokenize(code)


def _regex_tokenize(code: str) -> List[str]:
    """Regex-based code tokenization."""
    # Remove comments
    code = re.sub(r'#[^\n]*', '', code)
    code = re.sub(r'//[^\n]*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Extract identifiers, keywords, operators, literals
    token_pattern = re.compile(
        r'"[^"]*"|\'[^\']*\'|'           # String literals
        r'\b\d+\.?\d*\b|'               # Numbers
        r'\b[a-zA-Z_][a-zA-Z0-9_]*\b|'  # Identifiers
        r'[+\-*/=<>!&|^~%]+|'           # Operators
        r'[(){}\[\];,.]'                # Punctuation
    )
    tokens = token_pattern.findall(code)
    return [t.lower() for t in tokens if t.strip()]


def _tree_sitter_tokenize(code: str, language: str) -> List[str]:
    """Tree-sitter based tokenization for better AST normalization."""
    # Note: In production, you'd compile tree-sitter grammars
    # For MVP, we use the regex fallback primarily
    return _regex_tokenize(code)


def compute_minhash(tokens: List[str], num_perm: int = 128) -> Optional[List[int]]:
    """Compute MinHash signature for a set of tokens."""
    if not MINHASH_AVAILABLE or not tokens:
        return None
    
    try:
        m = MinHash(num_perm=num_perm)
        # Use shingles (k-grams) for better similarity
        shingles = set()
        k = 3  # trigrams
        for i in range(len(tokens) - k + 1):
            shingle = ' '.join(tokens[i:i+k])
            shingles.add(shingle.encode('utf-8'))
        
        # If too few tokens for shingles, use individual tokens
        if not shingles:
            for token in tokens:
                shingles.add(token.encode('utf-8'))
        
        for shingle in shingles:
            m.update(shingle)
        
        return list(m.hashvalues)
    except Exception as e:
        logger.error(f"MinHash computation failed: {e}")
        return None


def jaccard_similarity_from_minhash(sig1: List[int], sig2: List[int]) -> float:
    """Estimate Jaccard similarity from two MinHash signatures."""
    if not sig1 or not sig2 or len(sig1) != len(sig2):
        return 0.0
    
    matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
    return matches / len(sig1)


def compute_embedding(code: str, model_name: str = "all-MiniLM-L6-v2") -> Optional[List[float]]:
    """Compute semantic embedding for code snippet."""
    model = get_embedding_model(model_name)
    if model is None:
        return None
    
    try:
        # Truncate very long code snippets
        code_truncated = code[:2000] if len(code) > 2000 else code
        embedding = model.encode(code_truncated)
        return embedding.tolist()
    except Exception as e:
        logger.error(f"Embedding computation failed: {e}")
        return None


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return float(np.dot(v1, v2) / (norm1 * norm2))


def compute_code_hash(code: str) -> str:
    """Compute normalized hash for exact matching."""
    # Normalize: remove whitespace, lowercase
    normalized = re.sub(r'\s+', '', code.lower())
    return hashlib.sha256(normalized.encode()).hexdigest()


def normalize_code(code: str) -> str:
    """Normalize code for comparison."""
    # Remove comments
    code = re.sub(r'#[^\n]*', '', code)
    code = re.sub(r'//[^\n]*', '', code)
    # Normalize whitespace
    code = re.sub(r'\s+', ' ', code)
    return code.strip().lower()


class CodeAnalysis:
    """Result of analyzing a code snippet."""
    
    def __init__(self, code: str, language: Optional[str] = None):
        self.code = code
        self.language = language
        self.tokens = tokenize_code(code, language)
        self.minhash = compute_minhash(self.tokens)
        self.embedding = compute_embedding(code)
        self.code_hash = compute_code_hash(code)
        self.normalized = normalize_code(code)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens_count": len(self.tokens),
            "has_minhash": self.minhash is not None,
            "has_embedding": self.embedding is not None,
            "code_hash": self.code_hash,
        }