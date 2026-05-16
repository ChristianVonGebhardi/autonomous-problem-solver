"""
worker/main.py

Railway persistent worker — the always-on Step 3 engine.

Responsibilities:
1. Poll GitHub every POLL_INTERVAL_SECONDS for new feature branches ready for Step 3
2. Handle the full cycle lifecycle:
   - Fresh: branch has ARCHITECTURE.md, no src/, no open blocker, no DONE/CANCELLED
   - Blocked: wait for blocker-resolved or cycle-cancelled labels
   - Cancelled: write CANCELLED.md on cycle-cancelled label
   - Resumed: re-run Step 3 with context when cycle-resume label appears
3. Never process the same slug twice in the same run (in-memory state)

Trigger logic for Step 3 (per the agreed spec decision):
  A branch qualifies for Step 3 if:
  - It starts with "feature/"
  - It has ARCHITECTURE.md on the branch
  - It does NOT have a src/ directory
  - It does NOT have a DONE.md
  - It does NOT have a CANCELLED.md
  - There is no open Issue with label "blocker" referencing this slug
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Optional

# Ensure project root (parent of worker/) is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

from shared.claude_client import ClaudeClient
from shared.github_client import GitHubClient, ProblemBranch
from shared.utils import extract_slug_from_branch, truncate

from worker.step3 import Step3Runner

load_dotenv()  # Load .env for local development; Railway uses env vars directly

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("worker.main")

DEFAULT_POLL_INTERVAL = 60  # seconds


def main() -> None:
    """Main entry point — runs forever."""
    api_key = _require_env("ANTHROPIC_API_KEY")
    github_token = _require_env("GH_PAT")
    repo_owner = _require_env("REPO_OWNER")
    repo_name = _require_env("REPO_NAME")
    poll_interval = int(os.environ.get("POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL))

    logger.info(
        "Railway worker starting. owner=%s repo=%s poll_interval=%ds",
        repo_owner, repo_name, poll_interval,
    )

    claude = ClaudeClient(api_key=api_key)
    github = GitHubClient(token=github_token, owner=repo_owner, repo_name=repo_name)

    # In-memory sets to avoid processing the same event twice within a session
    processed_fresh: set[str] = set()      # slugs where Step 3 has been kicked off
    processed_cancelled: set[str] = set()  # slugs where CANCELLED.md has been written
    processed_resumed: set[str] = set()    # slugs where resume has been kicked off

    while True:
        try:
            _poll_once(
                github=github,
                claude=claude,
                repo_owner=repo_owner,
                repo_name=repo_name,
                processed_fresh=processed_fresh,
                processed_cancelled=processed_cancelled,
                processed_resumed=processed_resumed,
            )
        except Exception as e:
            logger.error("Unhandled exception in poll loop: %s", e, exc_info=True)
            # Don't crash — sleep and retry

        logger.debug("Sleeping %ds before next poll...", poll_interval)
        time.sleep(poll_interval)


def _poll_once(
    github: GitHubClient,
    claude: ClaudeClient,
    repo_owner: str,
    repo_name: str,
    processed_fresh: set[str],
    processed_cancelled: set[str],
    processed_resumed: set[str],
) -> None:
    """One full polling cycle."""

    # --- 1. Detect cycle-cancelled labels ---
    _handle_cancellations(github, claude, repo_owner, repo_name, processed_cancelled)

    # --- 2. Detect cycle-resume labels ---
    _handle_resumes(github, claude, repo_owner, repo_name, processed_resumed, processed_fresh)

    # --- 3. Detect fresh branches ready for Step 3 ---
    _handle_fresh_branches(github, claude, repo_owner, repo_name, processed_fresh)


# ---------------------------------------------------------------------------
# Cancellation handler
# ---------------------------------------------------------------------------

def _handle_cancellations(
    github: GitHubClient,
    claude: ClaudeClient,
    repo_owner: str,
    repo_name: str,
    processed_cancelled: set[str],
) -> None:
    """
    Looks for open or recently-closed Issues labelled 'cycle-cancelled'.
    For each, writes CANCELLED.md if not already done.
    """
    # Check closed issues with cycle-cancelled label
    try:
        cancelled_issues = github.get_issues_by_label("cycle-cancelled", state="closed")
    except Exception as e:
        logger.warning("Could not fetch cycle-cancelled issues: %s", e)
        return

    for issue in cancelled_issues:
        slug = _extract_slug_from_issue(issue.title)
        if not slug or slug in processed_cancelled:
            continue

        branch = f"feature/{slug}"
        if not github.branch_exists(branch):
            continue

        # Already have CANCELLED.md?
        if github._file_exists(f"{slug}/CANCELLED.md", branch):
            processed_cancelled.add(slug)
            continue

        logger.info("Detected cancellation for slug=%s (Issue #%d)", slug, issue.number)

        # Determine the open blocker description
        blocker_description = _get_active_blocker_description(github, slug)

        # Parse human reason from the closing comment
        human_reason = _get_human_cancellation_reason(github, issue)

        runner = Step3Runner(
            github=github,
            claude=claude,
            slug=slug,
            repo_owner=repo_owner,
            repo_name=repo_name,
        )
        runner.handle_cancelled(
            blocker_description=blocker_description or "No active blocker recorded.",
            human_reason=human_reason,
        )
        processed_cancelled.add(slug)


# ---------------------------------------------------------------------------
# Resume handler
# ---------------------------------------------------------------------------

def _handle_resumes(
    github: GitHubClient,
    claude: ClaudeClient,
    repo_owner: str,
    repo_name: str,
    processed_resumed: set[str],
    processed_fresh: set[str],
) -> None:
    """
    Looks for Issues with label 'cycle-resume'.
    For each, loads CANCELLED.md context and runs Step 3 resume flow.
    """
    try:
        resume_issues = github.get_issues_by_label("cycle-resume", state="open")
    except Exception as e:
        logger.warning("Could not fetch cycle-resume issues: %s", e)
        return

    for issue in resume_issues:
        slug = _extract_slug_from_issue(issue.title)
        if not slug:
            # Try to extract from body
            slug = _extract_slug_from_body(issue.body or "")
        if not slug or slug in processed_resumed:
            continue

        branch = f"feature/{slug}"
        if not github.branch_exists(branch):
            logger.warning("cycle-resume for slug=%s but branch %s does not exist", slug, branch)
            continue

        # Already has DONE.md? Nothing to resume.
        if github._file_exists(f"{slug}/DONE.md", branch):
            logger.info("Slug %s already done — ignoring cycle-resume", slug)
            processed_resumed.add(slug)
            continue

        cancelled_md = github.read_file(f"{slug}/CANCELLED.md", branch)
        if not cancelled_md:
            logger.warning("cycle-resume for slug=%s but no CANCELLED.md found — running as fresh resume", slug)
            cancelled_md = "No CANCELLED.md found — this cycle was blocked, not cancelled. Resume from last committed state."
            # Fall through to fresh handler
            continue

        logger.info("Resuming cycle for slug=%s (Issue #%d)", slug, issue.number)

        # Update labels: cycle-resume → in-progress
        github.remove_label_from_issue(issue, "cycle-resume")
        github.add_label_to_issue(issue, "in-progress")

        runner = Step3Runner(
            github=github,
            claude=claude,
            slug=slug,
            repo_owner=repo_owner,
            repo_name=repo_name,
        )
        result = runner.run_resumed(cancelled_md=cancelled_md)
        logger.info("Resume result for slug=%s: %s", slug, result)

        processed_resumed.add(slug)
        processed_fresh.add(slug)  # Prevent fresh handler from picking it up too


# ---------------------------------------------------------------------------
# Fresh branch handler
# ---------------------------------------------------------------------------

def _handle_fresh_branches(
    github: GitHubClient,
    claude: ClaudeClient,
    repo_owner: str,
    repo_name: str,
    processed_fresh: set[str],
) -> None:
    """
    Scans all feature/* branches for ones that qualify for a fresh Step 3 run.

    Qualifies if:
    - Has ARCHITECTURE.md
    - No src/ directory
    - No DONE.md
    - No CANCELLED.md
    - No open blocker Issue for this slug
    """
    try:
        branches = github.get_all_problem_branches()
    except Exception as e:
        logger.warning("Could not list problem branches: %s", e)
        return

    for pb in branches:
        if pb.slug in processed_fresh:
            continue
        if not _qualifies_for_step3(pb, github):
            continue

        logger.info("Found fresh branch ready for Step 3: slug=%s", pb.slug)
        processed_fresh.add(pb.slug)  # Mark before running to prevent duplicate kicks

        runner = Step3Runner(
            github=github,
            claude=claude,
            slug=pb.slug,
            repo_owner=repo_owner,
            repo_name=repo_name,
        )
        result = runner.run_fresh()
        logger.info("Step 3 result for slug=%s: %s", pb.slug, result)


def _qualifies_for_step3(pb: ProblemBranch, github: GitHubClient) -> bool:
    """Returns True if the branch is ready for a fresh Step 3 run."""
    if not pb.has_architecture_md:
        return False
    if pb.has_src:
        return False
    if pb.has_done_md:
        return False
    if pb.has_cancelled_md:
        return False
    
    # Skip branches with base64-encoded PROBLEM.md (created before v0.2.0)
    problem_content = github.read_file(f"{pb.slug}/PROBLEM.md", pb.branch_name)
    if problem_content and " " not in problem_content[:100]:
        logger.warning("Skipping slug=%s — PROBLEM.md appears base64-encoded", pb.slug)
        return False

    # Check for open blocker issue
    blocker_issues = github.get_issues_by_label("blocker", state="open")
    for issue in blocker_issues:
        if pb.slug in issue.title:
            logger.debug("Slug %s has open blocker Issue #%d — skipping", pb.slug, issue.number)
            return False

    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_slug_from_issue(title: str) -> Optional[str]:
    """
    Extracts a problem slug from an Issue title.
    Handles formats:
    - "[BLOCKER] {slug} — ..."
    - "[CYCLE] {slug} — ..."
    - "[DONE] {slug} — ..."
    """
    import re
    # Pattern: optional [TAG] prefix, then the slug (date-words format)
    m = re.search(r"(?:\[[^\]]+\]\s+)?(\d{4}-\d{2}-\d{2}-[a-z0-9-]+)", title)
    if m:
        return m.group(1)
    return None


def _extract_slug_from_body(body: str) -> Optional[str]:
    """Tries to find a slug pattern in an Issue body."""
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2}-[a-z0-9-]+)", body)
    if m:
        return m.group(1)
    return None


def _get_active_blocker_description(github: GitHubClient, slug: str) -> Optional[str]:
    """Returns the body of the most recent open blocker Issue for this slug."""
    try:
        issues = github.get_issues_by_label("blocker", state="open")
        for issue in issues:
            if slug in issue.title:
                return issue.body or issue.title
    except Exception:
        pass
    return None


def _get_human_cancellation_reason(github: GitHubClient, issue) -> Optional[str]:
    """
    Extracts the human's cancellation reason from the most recent Issue comment,
    if any. Returns None if no comment was left.
    """
    try:
        return github.get_latest_issue_comment(issue)
    except Exception:
        return None


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        logger.error("Required environment variable '%s' is not set. Exiting.", name)
        sys.exit(1)
    return val


if __name__ == "__main__":
    main()
