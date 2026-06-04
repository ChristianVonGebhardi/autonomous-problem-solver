"""
shared/build_detector.py

Detects the programming language of an MVP from its directory structure
and returns the appropriate build/validation commands.

Only Go and Python are supported — other languages are logged and skipped.
The caller is responsible for verifying the runtime binary exists before running commands.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

# Ordered list of (marker_file, language, build_commands).
# Commands run with cwd=code_dir, in sequence, stopping on first non-zero exit.
_DETECTORS: list[tuple[str, str, list[str]]] = [
    (
        "go.mod",
        "go",
        ["go mod tidy", "go build ./...", "go vet ./..."],
    ),
    (
        "requirements.txt",
        "python",
        # compileall catches syntax errors without installing dependencies into the worker env
        ["python -m compileall -q ."],
    ),
    (
        "pyproject.toml",
        "python",
        ["python -m compileall -q ."],
    ),
    (
        "setup.py",
        "python",
        ["python -m compileall -q ."],
    ),
]

_UNSUPPORTED_MARKERS: dict[str, str] = {
    "package.json": "node",
    "pom.xml": "java/maven",
    "build.gradle": "java/gradle",
    "Cargo.toml": "rust",
}


def detect_language(code_dir: str) -> tuple[Optional[str], list[str]]:
    """
    Inspects code_dir for language marker files, then each immediate subdirectory.
    Claude typically creates a named project folder inside the slug root
    (e.g. slug/my-project/requirements.txt), so one level of descent is required.

    Returns (language, commands) for a supported language,
    or (unsupported_language_name, []) / (None, []) when skipping.
    The commands' cwd will be the directory where the marker was found.
    """
    dirs_to_check = [code_dir]
    try:
        subdirs = sorted(
            os.path.join(code_dir, e)
            for e in os.listdir(code_dir)
            if os.path.isdir(os.path.join(code_dir, e)) and not e.startswith(".")
        )
        dirs_to_check.extend(subdirs)
    except OSError:
        pass

    for search_dir in dirs_to_check:
        result = _check_dir(search_dir)
        if result is not None:
            return result

    logger.warning("No language marker found in %s or its subdirectories — skipping Step 4", code_dir)
    return None, []


def _check_dir(directory: str) -> Optional[tuple[Optional[str], list[str]]]:
    """
    Checks a single directory for language markers.
    Returns (language, commands) if found, None if nothing matched.
    Commands are prefixed with 'cd <dir> &&' when the marker is in a subdirectory,
    so Step4Runner can still run them with cwd=code_dir.
    """
    for marker, language, commands in _DETECTORS:
        if os.path.exists(os.path.join(directory, marker)):
            runtime = _runtime_binary(language)
            if runtime and not shutil.which(runtime):
                logger.warning(
                    "Detected language=%s (in %s) but runtime binary '%s' not found — skipping Step 4",
                    language, directory, runtime,
                )
                return language, []
            logger.info("Detected language=%s (marker=%s in %s)", language, marker, directory)
            return language, [f"cd {directory} && {cmd}" for cmd in commands]

    for marker, language in _UNSUPPORTED_MARKERS.items():
        if os.path.exists(os.path.join(directory, marker)):
            logger.warning(
                "Detected language=%s (in %s) but not supported for build validation — skipping Step 4",
                language, directory,
            )
            return language, []

    return None


def _runtime_binary(language: str) -> Optional[str]:
    """Returns the binary name that must be on PATH for this language to run."""
    return {"go": "go", "python": "python"}.get(language)
