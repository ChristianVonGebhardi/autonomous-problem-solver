"""
scripts/run_step4.py

Standalone Step 4 build validation runner.

Runs Step 4 build validation against completed feature branches (those with DONE.md)
without going through the worker poll loop.

Usage:
    # Auto-discover all DONE branches, build-only (no fixes, no GitHub writes):
    python scripts/run_step4.py

    # Specific slugs:
    python scripts/run_step4.py 2026-05-28-some-slug 2026-06-01-other-slug

    # With Claude fix loop and GitHub commits (full Step4Runner behaviour):
    python scripts/run_step4.py --fix
    python scripts/run_step4.py --fix 2026-05-28-some-slug
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

from shared.build_detector import detect_language
from shared.claude_client import ClaudeClient
from shared.github_client import GitHubClient
from worker.step4 import Step4Runner

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

BUILD_TIMEOUT_SECONDS = 180


def _build_only(slug: str, github: GitHubClient, repo_owner: str, repo_name: str) -> tuple[bool, str]:
    """
    Clone the feature branch and run the build. No Claude fixes, no GitHub writes.
    Returns (passed, summary).
    """
    branch = f"feature/{slug}"
    tmpdir = tempfile.mkdtemp(prefix="step4_dry_")
    clone_dir = os.path.join(tmpdir, "repo")
    try:
        # Clone
        clone_url = (
            f"https://x-access-token:{github.token}"
            f"@github.com/{repo_owner}/{repo_name}.git"
        )
        result = subprocess.run(
            ["git", "clone", "--depth=1", "--branch", branch, clone_url, clone_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            safe_err = result.stderr.replace(github.token, "***")[:300]
            return True, f"SKIPPED — git clone failed: {safe_err}"

        code_dir = os.path.join(clone_dir, slug)
        if not os.path.isdir(code_dir):
            return True, f"SKIPPED — {slug}/ directory not found in repo"

        lang, commands = detect_language(code_dir)
        if not commands:
            reason = f"language={lang!r}" if lang else "no language detected"
            return True, f"SKIPPED — {reason}"

        # Run build commands
        output_parts: list[str] = []
        for cmd in commands:
            try:
                res = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=code_dir,
                    capture_output=True,
                    text=True,
                    timeout=BUILD_TIMEOUT_SECONDS,
                )
                chunk = f"$ {cmd}\n{res.stdout}"
                if res.stderr:
                    chunk += res.stderr
                output_parts.append(chunk)
                if res.returncode != 0:
                    build_output = "\n".join(output_parts)
                    return False, f"FAIL (language={lang})\n{build_output}"
            except subprocess.TimeoutExpired:
                return False, f"FAIL — command timed out: {cmd}"

        return True, f"PASS (language={lang})"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _discover_done_slugs(github: GitHubClient) -> list[str]:
    """Returns slugs of all feature branches that have a DONE.md."""
    branches = github.get_all_problem_branches()
    return [pb.slug for pb in branches if pb.has_done_md]


def main() -> None:
    args = sys.argv[1:]
    fix_mode = "--fix" in args
    slugs_from_args = [a for a in args if not a.startswith("--")]

    repo_owner = os.environ["REPO_OWNER"]
    repo_name = os.environ["REPO_NAME"]
    gh_pat = os.environ["GH_PAT"]
    anthropic_key = os.environ["ANTHROPIC_API_KEY"]

    github = GitHubClient(token=gh_pat, owner=repo_owner, repo_name=repo_name)

    if slugs_from_args:
        slugs = slugs_from_args
    else:
        logger.info("Auto-discovering DONE branches...")
        slugs = _discover_done_slugs(github)
        logger.info("Found %d DONE branch(es): %s", len(slugs), slugs)

    if not slugs:
        print("No DONE branches found.")
        return

    mode_label = "FULL (with Claude fixes + GitHub commits)" if fix_mode else "BUILD-ONLY (no GitHub writes)"
    print(f"\n{'='*60}")
    print(f"Step 4 standalone runner — mode: {mode_label}")
    print(f"Slugs ({len(slugs)}): {', '.join(slugs)}")
    print(f"{'='*60}\n")

    results: list[tuple[str, bool, str]] = []

    for slug in slugs:
        print(f"--- {slug} ---")
        if fix_mode:
            claude = ClaudeClient(api_key=anthropic_key)
            runner = Step4Runner(
                github=github,
                claude=claude,
                slug=slug,
                repo_owner=repo_owner,
                repo_name=repo_name,
            )
            passed, summary = runner.run()
        else:
            passed, summary = _build_only(slug=slug, github=github, repo_owner=repo_owner, repo_name=repo_name)

        status = "PASS" if passed else "FAIL"
        print(f"Result: {status}")
        print(summary[:1000] if not passed else summary)
        print()
        results.append((slug, passed, summary))

    # Summary table
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    passed_count = sum(1 for _, p, _ in results if p)
    failed_count = len(results) - passed_count
    for slug, passed, summary in results:
        icon = "PASS" if passed else "FAIL"
        first_line = summary.splitlines()[0] if summary else ""
        print(f"  [{icon}] {slug}")
        print(f"         {first_line}")
    print(f"\n{passed_count} passed, {failed_count} failed out of {len(results)} total.")


if __name__ == "__main__":
    main()
