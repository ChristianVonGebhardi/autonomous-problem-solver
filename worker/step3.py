"""
worker/step3.py

Implements Step 3: MVP Implementation.
Called by the main polling loop for both fresh cycles and resumed cycles.
"""

from __future__ import annotations

import logging
from typing import Optional

from shared.claude_client import ClaudeClient
from shared.github_client import GitHubClient
from shared.markers import make_done_md, make_cancelled_md
from shared.parsers import parse_step3_output, BlockerInfo
from shared.prompts import STEP3_SYSTEM, step3_user_prompt, step3_resume_prompt
from shared.utils import now_iso, truncate

logger = logging.getLogger(__name__)

REPO_BASE_URL_TEMPLATE = "https://github.com/{owner}/{repo}"


class Step3Runner:
    """
    Orchestrates MVP implementation for a single problem cycle.

    Responsibilities:
    - Load PROBLEM.md and ARCHITECTURE.md from GitHub
    - Enumerate any already-committed src/ files (for resumed cycles)
    - Call Claude with the full Step 3 prompt
    - Parse the response: commit files, handle BLOCKER, or finalise with DONE.md
    """

    MAX_AUTO_RESUMES = 5  # Maximum auto-resume cycles before requiring human review

    def __init__(
        self,
        github: GitHubClient,
        claude: ClaudeClient,
        slug: str,
        repo_owner: str,
        repo_name: str,
        processed_resumed: set | None = None,
    ):
        self.github = github
        self.claude = claude
        self.slug = slug
        self.branch = f"feature/{slug}"
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.repo_base_url = REPO_BASE_URL_TEMPLATE.format(owner=repo_owner, repo=repo_name)
        self.processed_resumed = processed_resumed  # reference to main loop's set

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def run_fresh(self) -> str:
        """
        Runs Step 3 for a brand-new cycle.
        Returns one of: "done", "blocked", "error"
        """
        logger.info("[%s] Starting Step 3 (fresh cycle)", self.slug)
        problem_md, architecture_md = self._load_required_docs()
        if not problem_md or not architecture_md:
            return "error"

        prompt = step3_user_prompt(
            problem_md=problem_md,
            architecture_md=architecture_md,
            existing_src_files=None,
        )
        return self._execute_and_handle(prompt, problem_md, architecture_md, cancelled_md=None)

    def run_resumed(self, cancelled_md: str) -> str:
        """
        Resumes a previously cancelled cycle.
        Returns one of: "done", "blocked", "error"
        """
        logger.info("[%s] Resuming cancelled cycle", self.slug)
        problem_md, architecture_md = self._load_required_docs()
        if not problem_md or not architecture_md:
            return "error"

        existing_src = self._load_existing_src()
        logger.info("[%s] Found %d existing src file(s)", self.slug, len(existing_src))

        prompt = step3_resume_prompt(
            cancelled_md=cancelled_md,
            problem_md=problem_md,
            architecture_md=architecture_md,
            existing_src_files=existing_src,
        )
        return self._execute_and_handle(prompt, problem_md, architecture_md, cancelled_md=cancelled_md)

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def _execute_and_handle(
            self,
            prompt: str,
            problem_md: str,
            architecture_md: str,
            cancelled_md: Optional[str],
        ) -> str:
            logger.info("[%s] Calling Claude for Step 3...", self.slug)
            try:
                raw_response, stop_reason = self.claude.complete(
                    system=STEP3_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                    use_web_search=False,
                    use_streaming=True,
                    max_tokens=32768,
                )
            except Exception as e:
                logger.error("[%s] Claude API call failed: %s", self.slug, e)
                return "error"

            logger.info("[%s] Claude responded (%d chars, stop_reason=%s)", self.slug, len(raw_response), stop_reason)
            parsed = parse_step3_output(raw_response)
            parsed.stop_reason = stop_reason

            # Commit any files Claude emitted, regardless of terminal state
            if parsed.files:
                logger.info("[%s] Committing %d file(s)...", self.slug, len(parsed.files))
                self._commit_src_files(parsed.files)

            if parsed.blocker:
                return self._handle_blocker(parsed.blocker)

            if parsed.mvp_complete:
                return self._handle_done(parsed.mvp_summary)

            # Check if truncation caused the missing terminal block
            if stop_reason == "max_tokens":
                logger.info("[%s] Response truncated — auto-scheduling resume", self.slug)
                return self._handle_truncation()

            # Truly ambiguous — treat as blocker
            logger.warning(
                "[%s] Claude response had neither <<<MVP_COMPLETE>>> nor <<<BLOCKER>>>. "
                "This may indicate a prompt compliance issue. Treating as blocker.",
                self.slug,
            )
            return self._handle_blocker(BlockerInfo(
                summary="Agent response was ambiguous — neither MVP_COMPLETE nor BLOCKER emitted",
                what_is_blocked="The Step 3 Claude response did not include a terminal block. "
                                "Implementation may be partially complete.",
                what_was_attempted="Claude was prompted with the full PROBLEM.md and ARCHITECTURE.md. "
                                "Files may have been committed if any <<<FILE>>> blocks were present.",
                resolution_options=[
                    "Review committed files in src/ to assess progress, then add label cycle-resume to [CYCLE] issue to retry",
                    "Inspect the raw response in Railway logs for clues",
                    "Cancel this cycle if the partial output is unusable",
                ],
                impact_if_unresolved="MVP is incomplete — no DONE.md will be created.",
            ))

    def _handle_truncation(self) -> str:
        """
        Auto-resumes when Claude was truncated mid-response (stop_reason=max_tokens).
        Tracks resume count in RESUME_COUNT file on the branch.
        If MAX_AUTO_RESUMES is exceeded, opens a blocker instead.
        """
        # Read current resume count
        resume_count = 0
        try:
            count_str = self.github.read_file(f"{self.slug}/RESUME_COUNT", self.branch)
            if count_str:
                resume_count = int(count_str.strip())
        except Exception:
            resume_count = 0

        resume_count += 1
        logger.info("[%s] Auto-resume count: %d/%d", self.slug, resume_count, self.MAX_AUTO_RESUMES)

        # Write updated count back to branch
        try:
            self.github.commit_file(
                path=f"{self.slug}/RESUME_COUNT",
                content=str(resume_count),
                commit_message=f"chore: update resume count to {resume_count}",
                branch=self.branch,
            )
        except Exception as e:
            logger.warning("[%s] Failed to write RESUME_COUNT: %s", self.slug, e)

        # Check if limit exceeded
        if resume_count > self.MAX_AUTO_RESUMES:
            logger.warning(
                "[%s] Max auto-resumes (%d) exceeded — opening blocker for human review",
                self.slug, self.MAX_AUTO_RESUMES,
            )
            return self._handle_blocker(BlockerInfo(
                summary=f"Max auto-resume limit ({self.MAX_AUTO_RESUMES}) reached — human review required",
                what_is_blocked=f"Implementation has been auto-resumed {resume_count} times due to "
                            f"response truncation (stop_reason=max_tokens) but has not completed. "
                            f"The MVP may require more files than can be generated in {self.MAX_AUTO_RESUMES} cycles.",
                what_was_attempted=f"Claude was prompted {resume_count} times with all existing files as context. "
                                f"Each run committed partial output before hitting the token limit.",
                resolution_options=[
                    f"Add label cycle-resume to [CYCLE] issue to continue for {self.MAX_AUTO_RESUMES} more cycles",
                    "Review committed files to assess if MVP is already functionally complete",
                    "Cancel this cycle if the scope is too large for automated implementation",
                    f"Increase MAX_AUTO_RESUMES in worker/step3.py (currently {self.MAX_AUTO_RESUMES})",
                ],
                impact_if_unresolved="MVP remains incomplete — no DONE.md will be created.",
            ))

        # Add cycle-resume label to trigger next poll
        try:
            issues = self.github.get_open_issues_for_slug(self.slug)
            for issue in issues:
                if issue.title.startswith(f"[CYCLE] {self.slug}"):
                    self.github.add_label_to_issue(issue, "cycle-resume")
                    logger.info("[%s] Added cycle-resume to Issue #%d for auto-resume (%d/%d)",
                            self.slug, issue.number, resume_count, self.MAX_AUTO_RESUMES)
                                        # Clear from processed_resumed so worker picks it up on next poll
                    if self.processed_resumed is not None:
                        self.processed_resumed.discard(self.slug)
                        logger.info("[%s] Cleared from processed_resumed for auto-resume", self.slug)
                    return "resuming"
        except Exception as e:
            logger.error("[%s] Failed to add cycle-resume label: %s", self.slug, e)
        return "error"

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _load_required_docs(self) -> tuple[Optional[str], Optional[str]]:
        problem_md = self.github.read_file(f"{self.slug}/PROBLEM.md", self.branch)
        architecture_md = self.github.read_file(f"{self.slug}/ARCHITECTURE.md", self.branch)

        if not problem_md:
            logger.error("[%s] PROBLEM.md not found on branch %s", self.slug, self.branch)
        if not architecture_md:
            logger.error("[%s] ARCHITECTURE.md not found on branch %s", self.slug, self.branch)

        return problem_md, architecture_md

    def _load_existing_src(self) -> dict[str, str]:
        """
        Enumerates and reads all source files under the slug root on the feature branch.
        Excludes known non-source files (PROBLEM.md, ARCHITECTURE.md, DONE.md,
        CANCELLED.md, README.md). Returns a dict of {relative_path: content}.
        """
        EXCLUDED_FILES = {
            "PROBLEM.md", "ARCHITECTURE.md", "DONE.md", "CANCELLED.md", "README.md", "RESUME_COUNT"
        }
        result = {}
        try:
            contents = self.github._repo.get_contents(self.slug, ref=self.branch)
            if not isinstance(contents, list):
                contents = [contents]
            queue = list(contents)
            while queue:
                item = queue.pop(0)
                if item.type == "dir":
                    sub = self.github._repo.get_contents(item.path, ref=self.branch)
                    if isinstance(sub, list):
                        queue.extend(sub)
                    else:
                        queue.append(sub)
                else:
                    filename = item.path.split("/")[-1]
                    if filename in EXCLUDED_FILES:
                        continue
                    text = self.github.read_file(item.path, self.branch)
                    if text is not None:
                        rel_path = item.path[len(f"{self.slug}/"):]
                        result[rel_path] = text
        except Exception as e:
            logger.debug("[%s] No existing files found or error reading slug root: %s", self.slug, e)
        return result

    def _commit_src_files(self, files: dict[str, str]) -> None:
        """
        Commits all files emitted by Claude to the feature branch.
        Paths are relative to slug root (e.g. "src/main.py") — prefixed with slug.
        """
        for rel_path, content in files.items():
            full_path = f"{self.slug}/{rel_path}"
            try:
                self.github.commit_file(
                    path=full_path,
                    content=content,
                    commit_message=f"feat: add {rel_path}",
                    branch=self.branch,
                )
                logger.info("[%s] Committed %s", self.slug, full_path)
            except Exception as e:
                logger.error("[%s] Failed to commit %s: %s", self.slug, full_path, e)

    # ------------------------------------------------------------------
    # Terminal state handlers
    # ------------------------------------------------------------------

    def _handle_done(self, summary: str) -> str:
        """Commits DONE.md and opens a PR."""
        logger.info("[%s] MVP complete — writing DONE.md", self.slug)
        done_md = make_done_md(
            slug=self.slug,
            summary=summary,
            repo_base_url=self.repo_base_url,
        )
        try:
            self.github.commit_file(
                path=f"{self.slug}/DONE.md",
                content=done_md,
                commit_message="chore: close cycle — MVP complete",
                branch=self.branch,
            )
        except Exception as e:
            logger.error("[%s] Failed to commit DONE.md: %s", self.slug, e)

        # Update tracking Issue labels
        self._update_cycle_issue_labels(remove="in-progress", add="done")

        # Open PR
        try:
            pr = self.github.create_done_pr(self.slug, self.branch)
            logger.info("[%s] Done PR #%d opened", self.slug, pr.number)
        except Exception as e:
            logger.warning("[%s] Could not create done PR (may already exist): %s", self.slug, e)

        return "done"

    def _handle_blocker(self, blocker: BlockerInfo) -> str:
        """Opens a blocker Issue and updates labels."""
        logger.info("[%s] Blocker encountered: %s", self.slug, blocker.summary)

        # Find the [CYCLE] issue number for cross-reference
        cycle_issue_number = self._get_cycle_issue_number()

        try:
            self.github.create_blocker_issue(
                slug=self.slug,
                summary=blocker.summary,
                what_is_blocked=blocker.what_is_blocked,
                what_was_attempted=blocker.what_was_attempted,
                resolution_options=blocker.resolution_options or ["Provide missing information and add label cycle-resume to the [CYCLE] issue"],
                impact_if_unresolved=blocker.impact_if_unresolved,
                cycle_issue_number=cycle_issue_number,
            )
        except Exception as e:
            logger.error("[%s] Failed to create blocker Issue: %s", self.slug, e)

        self._update_cycle_issue_labels(remove="in-progress", add="blocker")
        return "blocked"

    def _get_cycle_issue_number(self) -> Optional[int]:
        """Finds the [CYCLE] issue number for this slug."""
        try:
            issues = self.github.get_open_issues_for_slug(self.slug)
            for issue in issues:
                if issue.title.startswith(f"[CYCLE] {self.slug}"):
                    return issue.number
        except Exception as e:
            logger.warning("[%s] Could not find cycle issue number: %s", self.slug, e)
        return None

    def handle_cancelled(self, blocker_description: str, human_reason: Optional[str]) -> None:
        """Commits CANCELLED.md. Called by the main loop when the cycle is cancelled."""
        logger.info("[%s] Writing CANCELLED.md", self.slug)
        cancelled_md = make_cancelled_md(
            slug=self.slug,
            blocker_description=blocker_description,
            human_reason=human_reason,
            repo_base_url=self.repo_base_url,
        )
        try:
            self.github.commit_file(
                path=f"{self.slug}/CANCELLED.md",
                content=cancelled_md,
                commit_message="chore: close cycle — cancelled by human",
                branch=self.branch,
            )
            logger.info("[%s] CANCELLED.md committed", self.slug)
        except Exception as e:
            logger.error("[%s] Failed to commit CANCELLED.md: %s", self.slug, e)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_cycle_issue_labels(self, remove: Optional[str], add: Optional[str]) -> None:
        """
        Finds the main cycle tracking Issue for this slug and updates its labels.
        The tracking Issue title starts with "[CYCLE] {slug}".
        """
        try:
            issues = self.github.get_open_issues_for_slug(self.slug)
            for issue in issues:
                if issue.title.startswith(f"[CYCLE] {self.slug}"):
                    if remove:
                        self.github.remove_label_from_issue(issue, remove)
                    if add:
                        self.github.add_label_to_issue(issue, add)
                    logger.debug("[%s] Updated cycle Issue #%d labels: -%s +%s", self.slug, issue.number, remove, add)
                    return
        except Exception as e:
            logger.warning("[%s] Could not update cycle Issue labels: %s", self.slug, e)
