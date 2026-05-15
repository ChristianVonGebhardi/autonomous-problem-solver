"""
actions_runner.py

Entry point for the GitHub Actions daily workflow.
Runs Step 1 (problem brainstorm) and Step 2 (architecture design) in sequence.

Called as: python -c "from actions_runner import run_steps_1_and_2; run_steps_1_and_2()"
"""

from __future__ import annotations

import logging
import os
import sys
import time

# Ensure project root is on the path (Actions runs from repo root)
sys.path.insert(0, os.path.dirname(__file__))

from shared.claude_client import ClaudeClient
from shared.github_client import GitHubClient
from shared.parsers import parse_step2_output, build_architecture_md
from shared.prompts import (
    STEP1_SYSTEM,
    STEP2_SYSTEM,
    step1_user_prompt,
    step2_user_prompt,
)
from shared.utils import (
    today_iso,
    now_iso,
    make_slug,
    branch_name_for_slug,
    extract_title_from_problem_md,
    truncate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logging.getLogger("shared").setLevel(logging.INFO)
logger = logging.getLogger("actions_runner")


def run_steps_1_and_2() -> None:
    """
    Main entrypoint called by GitHub Actions.
    Executes Step 1 then Step 2, commits outputs to a new feature branch.
    """
    # --- Load configuration from environment ---
    anthropic_key = _require_env("ANTHROPIC_API_KEY")
    github_token = _require_env("GITHUB_TOKEN")
    repo_owner = _require_env("REPO_OWNER")
    repo_name = _require_env("REPO_NAME")

    logger.info("Starting daily cycle — date=%s owner=%s repo=%s", today_iso(), repo_owner, repo_name)

    claude = ClaudeClient(api_key=anthropic_key)
    github = GitHubClient(token=github_token, owner=repo_owner, repo_name=repo_name)

    # --- Step 1: Load memory ---
    logger.info("Loading problem memory from repository...")
    past_problems = github.load_all_problem_mds()
    already_explored = [
        extract_title_from_problem_md(p["content"]) for p in past_problems
    ]
    logger.info("Found %d past problem(s) in memory.", len(already_explored))

    # --- Step 1: Brainstorm ---
    logger.info("Running Step 1: Problem Brainstorm (web search disabled)...")
    problem_md = claude.complete(
        system=STEP1_SYSTEM,
        messages=[{"role": "user", "content": step1_user_prompt(already_explored)}],
        use_web_search=False,   # Disable for now because Claude returns empty too often maybe caused by websearch
        max_tokens=4096,
    )
    logger.info("Step 1 complete. Problem MD:\n%s", truncate(problem_md, 600))

    # --- Derive slug ---
    title = extract_title_from_problem_md(problem_md)
    slug = make_slug(today_iso(), title)
    branch = branch_name_for_slug(slug)
    logger.info("Problem slug: %s  Branch: %s", slug, branch)

    # --- Guard: abort if this slug already exists ---
    if github.branch_exists(branch):
        logger.error(
            "Branch %s already exists — this slug was already used today. "
            "This can happen if the workflow is triggered twice in one day. Aborting.",
            branch,
        )
        sys.exit(1)

    # --- Create feature branch ---
    github.create_branch(branch)

    # --- Commit PROBLEM.md ---
    github.commit_file(
        path=f"{slug}/PROBLEM.md",
        content=problem_md,
        commit_message=f"docs: add PROBLEM.md for {slug}",
        branch=branch,
    )
    logger.info("Committed PROBLEM.md to %s", branch)

    # --- Step 2: Architecture Design ---
    # --- Pause between steps to respect rate limits ---
    logger.info("Waiting 120s before Step 2 to respect token-per-minute rate limits...")
    time.sleep(120)

    logger.info("Running Step 2: Architecture Design...")
    arch_raw = claude.complete(
        system=STEP2_SYSTEM,
        messages=[{"role": "user", "content": step2_user_prompt(problem_md)}],
        use_web_search=False,
        max_tokens=8192,
    )
    logger.info("Step 2 raw output (%d chars)", len(arch_raw))

    # --- Parse and validate Step 2 output ---
    prose, mermaid_block = parse_step2_output(arch_raw)
    architecture_md = build_architecture_md(prose, mermaid_block)
    logger.info("Architecture prose (%d chars), diagram block (%d chars)", len(prose), len(mermaid_block))

    # --- Commit ARCHITECTURE.md ---
    github.commit_file(
        path=f"{slug}/ARCHITECTURE.md",
        content=architecture_md,
        commit_message=f"docs: add ARCHITECTURE.md for {slug}",
        branch=branch,
    )
    logger.info("Committed ARCHITECTURE.md to %s", branch)

    # --- Create GitHub Issue to track the cycle ---
    _create_cycle_issue(github, slug, branch, title, repo_owner, repo_name)

    logger.info(
        "✅ Steps 1 & 2 complete. Branch '%s' is ready for the Railway worker (Step 3).",
        branch,
    )


def _create_cycle_issue(
    github: GitHubClient,
    slug: str,
    branch: str,
    title: str,
    owner: str,
    repo_name: str,
) -> None:
    """
    Opens a GitHub Issue to track the lifecycle of this cycle.
    Labelled 'in-progress'. The Railway worker and human both interact via this Issue.
    """
    repo_url = f"https://github.com/{owner}/{repo_name}"
    body = f"""## New problem cycle started

**Slug:** `{slug}`
**Branch:** [`{branch}`]({repo_url}/tree/{branch})
**PROBLEM.md:** [{slug}/PROBLEM.md]({repo_url}/blob/{branch}/{slug}/PROBLEM.md)
**ARCHITECTURE.md:** [{slug}/ARCHITECTURE.md]({repo_url}/blob/{branch}/{slug}/ARCHITECTURE.md)

---

The Railway worker will pick this up automatically and begin Step 3 (MVP implementation).

If the agent gets blocked, it will open a new Issue tagged `blocker`. Watch for that.

**To cancel this cycle:** Close this Issue and add the label `cycle-cancelled`.
**To resume a cancelled cycle:** Reopen this Issue or open a new one with label `cycle-resume` referencing `{slug}`.
"""
    try:
        issue = github._repo.create_issue(
            title=f"[CYCLE] {slug} — {title}",
            body=body,
            labels=github._ensure_labels(["in-progress"]),
        )
        logger.info("Created cycle tracking Issue #%d", issue.number)
    except Exception as e:
        # Non-fatal — cycle can proceed without the tracking issue
        logger.warning("Could not create cycle tracking Issue: %s", e)


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        logger.error("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return val


if __name__ == "__main__":
    run_steps_1_and_2()
