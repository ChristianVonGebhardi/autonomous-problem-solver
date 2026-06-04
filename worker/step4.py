"""
worker/step4.py

Step 4: Build validation.

Clones the feature branch to a temp directory, detects the language,
runs build/compile commands, and asks Claude to fix errors up to
MAX_FIX_ATTEMPTS times. Runs after DONE.md is committed, before the PR is opened.

No sandboxing — generated code runs in the Railway worker container.
This is an accepted risk for v1: Claude's output is not adversarial.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from shared.build_detector import detect_language
from shared.claude_client import ClaudeClient
from shared.github_client import GitHubClient
from shared.parsers import parse_step3_output
from shared.prompts import STEP4_SYSTEM, step4_fix_prompt

logger = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 3
BUILD_TIMEOUT_SECONDS = 180


class Step4Runner:
    """
    Validates that a completed MVP actually builds.
    Runs in a cloned copy of the feature branch under a temp directory.
    The temp directory is always cleaned up, even on error.
    """

    MAX_FIX_ATTEMPTS = MAX_FIX_ATTEMPTS

    def __init__(
        self,
        github: GitHubClient,
        claude: ClaudeClient,
        slug: str,
        repo_owner: str,
        repo_name: str,
    ):
        self.github = github
        self.claude = claude
        self.slug = slug
        self.branch = f"feature/{slug}"
        self.repo_owner = repo_owner
        self.repo_name = repo_name

    def run(self) -> tuple[bool, str]:
        """
        Entry point. Clones branch, validates build, fixes errors.
        Returns (passed, human_readable_summary).
        passed=True also covers skipped cases (unsupported language, clone failure)
        so that infrastructure issues never block PR creation.
        """
        tmpdir = tempfile.mkdtemp(prefix="step4_")
        clone_dir = os.path.join(tmpdir, "repo")
        try:
            return self._run_inner(clone_dir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            logger.info("[%s] Step 4 temp dir cleaned up", self.slug)

    def _run_inner(self, clone_dir: str) -> tuple[bool, str]:
        if not self._clone(clone_dir):
            return True, "git clone failed — skipping build validation"

        # MVP files live under <clone_dir>/<slug>/
        code_dir = os.path.join(clone_dir, self.slug)
        if not os.path.isdir(code_dir):
            logger.warning("[%s] code dir not found after clone: %s", self.slug, code_dir)
            return True, f"code directory {self.slug}/ not found in repo — skipping"

        lang, commands = detect_language(code_dir)
        if not commands:
            reason = f"language={lang!r}" if lang else "no language detected"
            logger.info("[%s] Skipping build validation (%s)", self.slug, reason)
            return True, f"skipped — {reason}"

        logger.info("[%s] Starting build validation (language=%s)", self.slug, lang)

        last_output = ""
        for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
            output, passed = self._run_build(code_dir, commands)
            last_output = output
            logger.info(
                "[%s] Build attempt %d/%d: %s",
                self.slug, attempt, MAX_FIX_ATTEMPTS, "PASS" if passed else "FAIL",
            )

            if passed:
                return True, f"build passed (attempt {attempt}/{MAX_FIX_ATTEMPTS})"

            if attempt == MAX_FIX_ATTEMPTS:
                break

            logger.info("[%s] Asking Claude to fix build errors (attempt %d)...", self.slug, attempt)
            fixed_files = self._ask_claude_to_fix(output, code_dir)
            if not fixed_files:
                logger.warning("[%s] Claude emitted no fixes — stopping early", self.slug)
                break

            self._apply_fixes_locally(fixed_files, code_dir)
            self._commit_fixes_to_github(fixed_files)

        return False, last_output

    # ------------------------------------------------------------------
    # Clone
    # ------------------------------------------------------------------

    def _clone(self, clone_dir: str) -> bool:
        """Clones the feature branch to clone_dir. Token is kept out of logs."""
        clone_url = (
            f"https://x-access-token:{self.github.token}"
            f"@github.com/{self.repo_owner}/{self.repo_name}.git"
        )
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", "--branch", self.branch, clone_url, clone_dir],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                # Redact the token from stderr before logging
                safe_stderr = result.stderr.replace(self.github.token, "***")
                logger.error("[%s] git clone failed (exit %d): %s", self.slug, result.returncode, safe_stderr[:500])
                return False
            logger.info("[%s] git clone succeeded", self.slug)
            return True
        except subprocess.TimeoutExpired:
            logger.error("[%s] git clone timed out", self.slug)
            return False
        except Exception as e:
            logger.error("[%s] git clone error: %s", self.slug, e)
            return False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _run_build(self, code_dir: str, commands: list[str]) -> tuple[str, bool]:
        """
        Runs each command in sequence, stopping on first failure.
        Returns (combined_output, passed).
        """
        output_parts: list[str] = []
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=code_dir,
                    capture_output=True,
                    text=True,
                    timeout=BUILD_TIMEOUT_SECONDS,
                )
                chunk = f"$ {cmd}\n{result.stdout}"
                if result.stderr:
                    chunk += result.stderr
                output_parts.append(chunk)
                if result.returncode != 0:
                    logger.info("[%s] Command failed (exit %d): %s", self.slug, result.returncode, cmd)
                    return "\n".join(output_parts), False
            except subprocess.TimeoutExpired:
                output_parts.append(f"$ {cmd}\n[TIMEOUT after {BUILD_TIMEOUT_SECONDS}s]")
                logger.error("[%s] Build command timed out: %s", self.slug, cmd)
                return "\n".join(output_parts), False
        return "\n".join(output_parts), True

    # ------------------------------------------------------------------
    # Claude fix loop
    # ------------------------------------------------------------------

    def _ask_claude_to_fix(self, build_output: str, code_dir: str) -> dict[str, str]:
        """
        Sends the build error + current source files to Claude.
        Returns {relative_path: corrected_content} of files that need changes.
        """
        existing = self._load_source_files(code_dir)
        prompt = step4_fix_prompt(build_output=build_output, existing_files=existing)
        try:
            raw, stop_reason = self.claude.complete(
                system=STEP4_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                use_web_search=False,
                use_streaming=True,
                max_tokens=16384,
            )
            logger.info(
                "[%s] Claude fix response (%d chars, stop_reason=%s)",
                self.slug, len(raw), stop_reason,
            )
        except Exception as e:
            logger.error("[%s] Claude fix call failed: %s", self.slug, e)
            return {}

        parsed = parse_step3_output(raw)
        for w in parsed.parse_warnings:
            logger.warning("[%s] Step 4 parse warning: %s", self.slug, w)
        logger.info("[%s] Claude proposed fixes for %d file(s)", self.slug, len(parsed.files))
        return parsed.files

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _load_source_files(self, code_dir: str) -> dict[str, str]:
        """Reads all non-doc files from the local clone. Returns {relative_path: content}."""
        EXCLUDED = {
            "PROBLEM.md", "ARCHITECTURE.md", "DONE.md",
            "CANCELLED.md", "README.md", "RESUME_COUNT",
        }
        result: dict[str, str] = {}
        for root, dirs, files in os.walk(code_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if fname in EXCLUDED:
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, code_dir).replace(os.sep, "/")
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as f:
                        result[rel] = f.read()
                except Exception as e:
                    logger.debug("[%s] Could not read %s: %s", self.slug, rel, e)
        return result

    def _apply_fixes_locally(self, fixed_files: dict[str, str], code_dir: str) -> None:
        """Writes Claude's corrected files to the local clone so the next build sees them."""
        for rel_path, content in fixed_files.items():
            full_path = os.path.join(code_dir, *rel_path.split("/"))
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            try:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("[%s] Applied fix locally: %s", self.slug, rel_path)
            except Exception as e:
                logger.error("[%s] Failed to apply fix locally for %s: %s", self.slug, rel_path, e)

    def _commit_fixes_to_github(self, fixed_files: dict[str, str]) -> None:
        """Commits Claude's corrected files to the GitHub feature branch."""
        for rel_path, content in fixed_files.items():
            full_path = f"{self.slug}/{rel_path}"
            try:
                self.github.commit_file(
                    path=full_path,
                    content=content,
                    commit_message=f"fix: step 4 build fix — {rel_path}",
                    branch=self.branch,
                )
                logger.info("[%s] Committed build fix: %s", self.slug, full_path)
            except Exception as e:
                logger.error("[%s] Failed to commit build fix for %s: %s", self.slug, rel_path, e)
