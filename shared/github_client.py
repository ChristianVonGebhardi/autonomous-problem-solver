"""
shared/github_client.py

Centralised GitHub API wrapper used by both the Actions runner and the Railway worker.
Uses PyGithub for high-level operations and falls back to raw httpx for anything
PyGithub doesn't expose (e.g. creating commits with trees).
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from github import Github, GithubException
from github.ContentFile import ContentFile
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class ProblemBranch:
    """Represents a feature branch for a single problem cycle."""
    slug: str                        # e.g. "2025-05-14-offline-medication-reminders"
    branch_name: str                 # e.g. "feature/2025-05-14-offline-medication-reminders"
    has_problem_md: bool = False
    has_architecture_md: bool = False
    has_src: bool = False
    has_done_md: bool = False
    has_cancelled_md: bool = False
    open_blocker_issue: Optional[Issue] = None
    open_resume_issue: Optional[Issue] = None


@dataclass
class CycleFiles:
    """File contents committed during a cycle."""
    problem_md: str = ""
    architecture_md: str = ""
    src_files: dict[str, str] = field(default_factory=dict)  # path -> content
    readme_md: str = ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class GitHubClient:
    """
    Wraps PyGithub + httpx to provide all GitHub operations the agent needs.
    """

    def __init__(self, token: str, owner: str, repo_name: str):
        self.token = token
        self.owner = owner
        self.repo_name = repo_name
        self._gh = Github(token)
        self._repo: Repository = self._gh.get_repo(f"{owner}/{repo_name}")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Memory: read all past PROBLEM.md files
    # ------------------------------------------------------------------

    def load_all_problem_mds(self) -> list[dict]:
        """
        Fetches every PROBLEM.md from every feature/* branch.
        Returns a list of dicts: {"slug": str, "content": str}.
        Never raises — logs and skips on error.
        """
        results = []
        try:
            branches = self._repo.get_branches()
            for branch in branches:
                if not branch.name.startswith("feature/"):
                    continue
                slug = branch.name[len("feature/"):]
                path = f"{slug}/PROBLEM.md"
                try:
                    content_file: ContentFile = self._repo.get_contents(path, ref=branch.name)
                    # Strip embedded newlines — GitHub API paginates base64 output
                    text = base64.b64decode(content_file.content.replace("\n", "")).decode("utf-8")
                    results.append({"slug": slug, "content": text})
                    logger.debug("Loaded PROBLEM.md for slug=%s", slug)
                except GithubException as e:
                    if e.status == 404:
                        pass  # Branch exists but no PROBLEM.md yet — skip
                    else:
                        logger.warning("Error reading %s: %s", path, e)
        except Exception as e:
            logger.error("Failed to load problem memory: %s", e)
        return results

    # ------------------------------------------------------------------
    # Branch management
    # ------------------------------------------------------------------

    def branch_exists(self, branch_name: str) -> bool:
        try:
            self._repo.get_branch(branch_name)
            return True
        except GithubException:
            return False

    def create_branch(self, branch_name: str, base_branch: str = "main") -> None:
        """Creates a new branch from base_branch."""
        try:
            base = self._repo.get_branch(base_branch)
        except GithubException:
            # Fall back to 'master' if 'main' doesn't exist
            base = self._repo.get_branch("master")
        ref = f"refs/heads/{branch_name}"
        self._repo.create_git_ref(ref=ref, sha=base.commit.sha)
        logger.info("Created branch %s from %s", branch_name, base_branch)

    def get_all_problem_branches(self) -> list[ProblemBranch]:
        """
        Returns ProblemBranch objects for every feature/* branch,
        populated with existence flags.
        """
        results = []
        try:
            branches = self._repo.get_branches()
        except GithubException as e:
            logger.error("Cannot list branches: %s", e)
            return results

        for branch in branches:
            if not branch.name.startswith("feature/"):
                continue
            slug = branch.name[len("feature/"):]
            pb = ProblemBranch(slug=slug, branch_name=branch.name)
            pb.has_problem_md = self._file_exists(f"{slug}/PROBLEM.md", branch.name)
            pb.has_architecture_md = self._file_exists(f"{slug}/ARCHITECTURE.md", branch.name)
            pb.has_src = self._file_exists(f"{slug}/src", branch.name)
            pb.has_done_md = self._file_exists(f"{slug}/DONE.md", branch.name)
            pb.has_cancelled_md = self._file_exists(f"{slug}/CANCELLED.md", branch.name)
            results.append(pb)
        return results

    def _file_exists(self, path: str, ref: str) -> bool:
        try:
            self._repo.get_contents(path, ref=ref)
            return True
        except GithubException:
            return False

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def commit_file(
        self,
        path: str,
        content: str,
        commit_message: str,
        branch: str,
    ) -> None:
        """
        Creates or updates a single file on a branch.
        Uses UTF-8 encoding. Retries once on 409 conflict.
        """
        # Check if file already exists (need sha for update)
        sha: Optional[str] = None
        try:
            existing: ContentFile = self._repo.get_contents(path, ref=branch)
            sha = existing.sha
        except GithubException as e:
            if e.status != 404:
                raise

        for attempt in range(2):
            try:
                if sha:
                    self._repo.update_file(
                        path=path,
                        message=commit_message,
                        content=content,  # plain text — PyGithub encodes internally
                        sha=sha,
                        branch=branch,
                    )
                else:
                    self._repo.create_file(
                        path=path,
                        message=commit_message,
                        content=content,  # plain text — PyGithub encodes internally
                        branch=branch,
                    )
                logger.info("Committed %s to branch %s", path, branch)
                return
            except GithubException as e:
                if e.status == 409 and attempt == 0:
                    logger.warning("409 conflict on %s — retrying after 2s", path)
                    time.sleep(2)
                    try:
                        existing = self._repo.get_contents(path, ref=branch)
                        sha = existing.sha
                    except GithubException:
                        sha = None
                else:
                    raise

    def read_file(self, path: str, branch: str) -> Optional[str]:
        """Returns file content as string, or None if not found."""
        try:
            content_file: ContentFile = self._repo.get_contents(path, ref=branch)
            return base64.b64decode(content_file.content).decode("utf-8")
        except GithubException as e:
            if e.status == 404:
                return None
            raise

    def commit_multiple_files(
        self,
        files: dict[str, str],  # path -> content
        commit_message: str,
        branch: str,
    ) -> None:
        """
        Commits multiple files in sequence. Each is a separate commit.
        For truly atomic multi-file commits the GitHub Trees API would be needed;
        sequential commits are sufficient here and much simpler.
        """
        for path, content in files.items():
            self.commit_file(path, content, commit_message, branch)

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def create_blocker_issue(
        self,
        slug: str,
        summary: str,
        what_is_blocked: str,
        what_was_attempted: str,
        resolution_options: list[str],
        impact_if_unresolved: str,
        cycle_issue_number: Optional[int] = None,
    ) -> Issue:
        """Opens a blocker Issue following the spec's format."""
        options_md = "\n".join(f"- {opt}" for opt in resolution_options)
        cycle_ref = f"\n**Cycle tracking issue:** #{cycle_issue_number}\n" if cycle_issue_number else ""
        body = f"""## What is blocked
{what_is_blocked}

## What was attempted
{what_was_attempted}

## Resolution options
{options_md}

## Impact if unresolved
{impact_if_unresolved}
{cycle_ref}
---
**To unblock this cycle:** Resolve the issue above, then add label `cycle-resume` to this Issue or to #{cycle_issue_number if cycle_issue_number else 'the [CYCLE] issue'}.

**To cancel this cycle:** Close this Issue and add the label `cycle-cancelled` (optionally add a comment with your reason).
"""
        issue = self._repo.create_issue(
            title=f"[BLOCKER] {slug} — {summary}",
            body=body,
            labels=self._ensure_labels(["blocker"]),
        )
        logger.info("Created blocker Issue #%d for slug=%s", issue.number, slug)
        return issue

    def get_open_issues_for_slug(self, slug: str) -> list[Issue]:
        """Returns all open Issues whose title contains the slug."""
        results = []
        try:
            issues = self._repo.get_issues(state="open")
            for issue in issues:
                if slug in issue.title:
                    results.append(issue)
        except GithubException as e:
            logger.error("Failed to list issues: %s", e)
        return results

    def get_issues_by_label(self, label: str, state: str = "open") -> list[Issue]:
        try:
            return list(self._repo.get_issues(state=state, labels=[label]))
        except GithubException as e:
            logger.error("Failed to list issues by label %s: %s", label, e)
            return []

    def add_label_to_issue(self, issue: Issue, label: str) -> None:
        issue.add_to_labels(self._ensure_label(label))

    def remove_label_from_issue(self, issue: Issue, label: str) -> None:
        try:
            issue.remove_from_labels(label)
        except GithubException:
            pass  # Label may not be present — ignore

    def get_issue_labels(self, issue: Issue) -> list[str]:
        return [lbl.name for lbl in issue.labels]

    def get_latest_issue_comment(self, issue: Issue) -> Optional[str]:
        """Returns the body of the most recent comment, or None."""
        try:
            comments = list(issue.get_comments())
            if comments:
                return comments[-1].body
            return None
        except GithubException:
            return None

    def close_issue(self, issue: Issue) -> None:
        issue.edit(state="closed")

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    def create_done_pr(self, slug: str, branch_name: str) -> PullRequest:
        """Opens a PR from the feature branch to main, labelled 'done'."""
        pr = self._repo.create_pull(
            title=f"[DONE] {slug} — MVP complete",
            body=f"Automated PR: MVP cycle complete for `{slug}`.\n\nSee `{slug}/DONE.md` for a summary.",
            head=branch_name,
            base="main",
        )
        pr.add_to_labels(self._ensure_label("done"))
        logger.info("Created done PR #%d for slug=%s", pr.number, slug)
        return pr

    # ------------------------------------------------------------------
    # Label helpers
    # ------------------------------------------------------------------

    def _ensure_label(self, name: str) -> str:
        """Creates a label if it doesn't exist. Returns the label name."""
        LABEL_COLORS = {
            "blocker": "d73a4a",
            "blocker-resolved": "0075ca",
            "in-progress": "e4e669",
            "cycle-cancelled": "cfd3d7",
            "cycle-resume": "a2eeef",
            "done": "0e8a16",
        }
        try:
            self._repo.get_label(name)
        except GithubException:
            color = LABEL_COLORS.get(name, "ededed")
            try:
                self._repo.create_label(name=name, color=color)
                logger.info("Created label '%s'", name)
            except GithubException as e:
                logger.warning("Could not create label '%s': %s", name, e)
        return name

    def _ensure_labels(self, names: list[str]) -> list[str]:
        return [self._ensure_label(n) for n in names]
