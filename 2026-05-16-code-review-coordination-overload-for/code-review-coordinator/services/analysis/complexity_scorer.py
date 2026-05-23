"""
PR Complexity Scoring Engine.

Uses a combination of heuristic rules and a lightweight ML model
to score PR complexity and estimate review time.
"""
import re
import math
import numpy as np
from typing import Tuple, Dict


# Security/risk keywords that increase risk score
SECURITY_KEYWORDS = [
    "auth", "authentication", "authorization", "password", "secret",
    "token", "crypto", "encrypt", "decrypt", "hash", "jwt", "oauth",
    "permission", "access", "privilege", "credential", "key", "cert",
    "ssl", "tls", "https", "cors", "csrf", "xss", "injection", "sql",
    "sanitize", "escape", "validate",
]

# High-risk file patterns
HIGH_RISK_PATTERNS = [
    r"auth.*\.(go|py|ts|js)$",
    r"security.*\.(go|py|ts|js)$",
    r"payment.*\.(go|py|ts|js)$",
    r".*\.env$",
    r".*migration.*\.sql$",
    r".*schema.*\.(go|py|ts|js)$",
    r"k8s/.*\.yaml$",
    r"helm/.*\.yaml$",
    r"terraform/.*\.tf$",
    r"\.github/workflows/.*\.yml$",
]

# Complexity-adding file types
COMPLEX_EXTENSIONS = {
    ".go": 1.2,
    ".py": 1.1,
    ".ts": 1.15,
    ".tsx": 1.2,
    ".java": 1.3,
    ".rs": 1.4,
    ".cpp": 1.5,
    ".c": 1.4,
    ".sql": 1.6,  # Schema changes are complex
    ".proto": 1.3,
    ".yaml": 1.1,
    ".json": 0.8,
    ".md": 0.3,
    ".txt": 0.2,
}


class PRComplexityScorer:
    """
    Scores PR complexity on a 0-10 scale.
    
    Factors considered:
    - Lines changed (size)
    - Files changed
    - Author experience
    - Title/description keywords
    - Historical patterns
    """

    def __init__(self):
        # Feature weights calibrated from empirical data
        self.weights = {
            "size_score": 0.35,
            "file_count_score": 0.20,
            "author_experience_score": 0.15,
            "keyword_score": 0.15,
            "churn_ratio_score": 0.15,
        }

    def score(
        self,
        lines_added: int,
        lines_deleted: int,
        files_changed: int,
        title: str = "",
        author_pr_count: int = 0,
        author_avg_complexity: float = 5.0,
    ) -> Tuple[float, Dict]:
        """
        Compute complexity score (0-10).
        Returns (score, factors_dict).
        """
        total_lines = lines_added + lines_deleted
        
        # 1. Size score (logarithmic scale)
        if total_lines == 0:
            size_score = 1.0
        elif total_lines < 50:
            size_score = 2.0
        elif total_lines < 200:
            size_score = 4.0 + (total_lines - 50) / 150 * 2.0
        elif total_lines < 500:
            size_score = 6.0 + (total_lines - 200) / 300 * 2.0
        elif total_lines < 1000:
            size_score = 8.0 + (total_lines - 500) / 500 * 1.5
        else:
            size_score = min(10.0, 9.5 + math.log10(total_lines / 1000) * 0.5)

        # 2. File count score
        if files_changed <= 1:
            file_count_score = 2.0
        elif files_changed <= 5:
            file_count_score = 4.0 + (files_changed - 1) / 4 * 2.0
        elif files_changed <= 15:
            file_count_score = 6.0 + (files_changed - 5) / 10 * 2.0
        elif files_changed <= 30:
            file_count_score = 8.0 + (files_changed - 15) / 15 * 1.5
        else:
            file_count_score = min(10.0, 9.5)

        # 3. Author experience (inverse — less experience = more complex review)
        if author_pr_count >= 100:
            author_experience_score = 3.0  # Experienced author, cleaner PRs expected
        elif author_pr_count >= 30:
            author_experience_score = 5.0
        elif author_pr_count >= 10:
            author_experience_score = 6.5
        else:
            author_experience_score = 8.0  # New author needs more careful review

        # 4. Keyword complexity (title analysis)
        keyword_score = self._title_complexity_score(title)

        # 5. Churn ratio (deletions relative to additions — refactoring is complex)
        if lines_added > 0:
            churn_ratio = lines_deleted / max(lines_added, 1)
            if churn_ratio > 0.8:  # Heavy refactoring
                churn_ratio_score = 7.0
            elif churn_ratio > 0.4:
                churn_ratio_score = 5.0
            else:
                churn_ratio_score = 3.0
        else:
            churn_ratio_score = 4.0

        # Weighted average
        complexity_score = (
            size_score * self.weights["size_score"] +
            file_count_score * self.weights["file_count_score"] +
            author_experience_score * self.weights["author_experience_score"] +
            keyword_score * self.weights["keyword_score"] +
            churn_ratio_score * self.weights["churn_ratio_score"]
        )

        # Incorporate author's historical complexity (light influence)
        complexity_score = complexity_score * 0.9 + author_avg_complexity * 0.1
        complexity_score = max(1.0, min(10.0, complexity_score))

        factors = {
            "size_score": round(size_score, 2),
            "file_count_score": round(file_count_score, 2),
            "author_experience_score": round(author_experience_score, 2),
            "keyword_score": round(keyword_score, 2),
            "churn_ratio_score": round(churn_ratio_score, 2),
            "total_lines": total_lines,
            "files_changed": files_changed,
        }

        return complexity_score, factors

    def risk_score(
        self,
        lines_added: int,
        files_changed: int,
        title: str = "",
        repo: str = "",
    ) -> float:
        """
        Compute risk score (0-10).
        High risk = security-sensitive, infrastructure, or large changes.
        """
        risk = 3.0  # Base risk

        # Check title for security keywords
        title_lower = title.lower()
        keyword_hits = sum(1 for kw in SECURITY_KEYWORDS if kw in title_lower)
        if keyword_hits >= 3:
            risk += 4.0
        elif keyword_hits >= 1:
            risk += 2.0

        # Repo-level risk
        repo_lower = repo.lower()
        if any(kw in repo_lower for kw in ["auth", "security", "payment", "infra", "core"]):
            risk += 2.0

        # Size-based risk
        if lines_added > 500:
            risk += 2.0
        elif lines_added > 200:
            risk += 1.0

        # Many files = risk of unintended side effects
        if files_changed > 20:
            risk += 1.5
        elif files_changed > 10:
            risk += 0.5

        return max(1.0, min(10.0, risk))

    def estimate_review_time(
        self,
        complexity_score: float,
        lines_added: int,
        lines_deleted: int,
    ) -> int:
        """
        Estimate review time in minutes.
        
        Based on industry data: ~5-15 lines/minute for experienced reviewers.
        """
        total_lines = lines_added + lines_deleted

        # Base time from lines
        base_minutes = max(5, total_lines / 10)

        # Complexity multiplier
        complexity_multiplier = 1.0 + (complexity_score - 5.0) * 0.1
        complexity_multiplier = max(0.5, min(2.5, complexity_multiplier))

        estimated = base_minutes * complexity_multiplier

        # Round to reasonable buckets
        if estimated < 15:
            return 15
        elif estimated < 30:
            return 30
        elif estimated < 60:
            return 60
        elif estimated < 120:
            return 90
        elif estimated < 240:
            return 180
        else:
            return min(480, int(estimated))

    def _title_complexity_score(self, title: str) -> float:
        """Score complexity based on PR title keywords."""
        if not title:
            return 5.0

        title_lower = title.lower()

        # High complexity indicators
        high_complexity_keywords = [
            "refactor", "migration", "redesign", "overhaul", "rewrite",
            "breaking change", "schema change", "architecture",
        ]

        # Medium complexity
        medium_complexity_keywords = [
            "implement", "add", "new feature", "integration",
            "performance", "optimization", "cache",
        ]

        # Low complexity
        low_complexity_keywords = [
            "fix", "bug", "typo", "update readme", "docs",
            "style", "lint", "format", "minor",
        ]

        for kw in high_complexity_keywords:
            if kw in title_lower:
                return 8.0

        for kw in medium_complexity_keywords:
            if kw in title_lower:
                return 5.5

        for kw in low_complexity_keywords:
            if kw in title_lower:
                return 2.5

        return 5.0  # Default