"""
shared/markers.py

Generates the content for DONE.md and CANCELLED.md marker files.
These are committed to the problem branch at the end of a cycle.
"""

from __future__ import annotations

from shared.utils import now_iso


def make_done_md(slug: str, summary: str, repo_base_url: str) -> str:
    """
    Generates the content for DONE.md.

    Args:
        slug:           Problem slug, e.g. "2025-05-14-offline-medication-reminders"
        summary:        1-3 sentence description of what was built.
        repo_base_url:  e.g. "https://github.com/ChristianVonGebhardi/autonomous-problem-solver"
    """

    return f"""# ✅ DONE — {slug}

**Completed at:** {now_iso()}

## What was built

{summary}

## Source code

[Repository branch]({repo_base_url}/tree/feature/{slug})

---
*This file was written automatically by the autonomous problem-solving agent.*
"""


def make_cancelled_md(
    slug: str,
    blocker_description: str,
    human_reason: str | None,
    repo_base_url: str,
) -> str:
    """
    Generates the content for CANCELLED.md.

    Args:
        slug:                 Problem slug.
        blocker_description:  The open blocker at time of cancellation.
        human_reason:         Optional reason extracted from the closing Issue comment.
        repo_base_url:        e.g. "https://github.com/ChristianVonGebhardi/autonomous-problem-solver"
    """
    reason_section = ""
    if human_reason:
        reason_section = f"\n## Reason provided by human\n\n{human_reason}\n"

    return f"""# ❌ CANCELLED — {slug}

**Cancelled at:** {now_iso()}

## Open blocker at time of cancellation

{blocker_description}
{reason_section}
## How to resume this cycle

1. Reopen the blocker Issue in this repository **and** add the label `cycle-resume`, OR
2. Open a new Issue with the label `cycle-resume` and include `{slug}` in the title or body.

The Railway worker will detect the `cycle-resume` label, read this file to restore context,
review the last committed state in `src/`, and continue implementation from where it left off.

---
*This file was written automatically by the autonomous problem-solving agent.*
"""
