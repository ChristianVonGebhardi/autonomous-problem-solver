"""
shared/utils.py

Shared utility functions: slug generation, timestamps, text helpers.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone


def today_iso() -> str:
    """Returns today's date in YYYY-MM-DD format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    """Returns current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_slug(date: str, title: str) -> str:
    """
    Converts a date and free-form title into a problem slug.
    e.g. ("2025-05-14", "Offline Medication Reminders") -> "2025-05-14-offline-medication-reminders"

    Keeps only alphanumeric characters and hyphens, collapses spaces/underscores
    to single hyphens, and trims to a reasonable length.
    """
    title_part = title.lower().strip()
    title_part = re.sub(r"[^a-z0-9\s-]", "", title_part)
    title_part = re.sub(r"[\s_]+", "-", title_part)
    title_part = re.sub(r"-+", "-", title_part).strip("-")
    # Keep slug to 5 words (rough heuristic: split on hyphen, take first 5)
    words = title_part.split("-")[:5]
    title_part = "-".join(words)
    return f"{date}-{title_part}"


def extract_slug_from_branch(branch_name: str) -> str:
    """Strips the 'feature/' prefix from a branch name."""
    return branch_name.removeprefix("feature/")


def branch_name_for_slug(slug: str) -> str:
    return f"feature/{slug}"


def extract_title_from_problem_md(problem_md: str) -> str:
    """
    Extracts the H2 title from a PROBLEM.md.
    Falls back to the first non-empty line if no H2 is found.
    """
    for line in problem_md.splitlines():
        line = line.strip()
        if line.startswith("## "):
            return line[3:].strip()
        if line.startswith("# "):
            return line[2:].strip()
    for line in problem_md.splitlines():
        if line.strip():
            return line.strip()
    return "Unknown Problem"


def truncate(text: str, max_chars: int = 500) -> str:
    """Truncates text for logging."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"… [truncated, total {len(text)} chars]"
