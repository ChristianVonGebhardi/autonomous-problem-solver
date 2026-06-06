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
    Walks code_dir recursively (breadth-first via sorted dirs) to find a language marker.
    Returns on the first supported marker found; unsupported markers are returned only
    if no supported marker exists anywhere in the tree.

    Claude MVPs can be nested arbitrarily deep (e.g. slug/project-name/backend/requirements.txt),
    so a full recursive walk is required.

    Returns (language, commands) for a supported language,
    or (unsupported_language_name, []) / (None, []) when skipping.
    """
    first_unsupported: Optional[tuple[str, str]] = None  # (directory, language)

    for root, dirs, files in os.walk(code_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))

        for marker, language, commands in _DETECTORS:
            if marker in files:
                runtime = _runtime_binary(language)
                if runtime and not shutil.which(runtime):
                    logger.warning(
                        "Detected language=%s (in %s) but runtime binary '%s' not found — skipping Step 4",
                        language, root, runtime,
                    )
                    return language, []
                logger.info("Detected language=%s (marker=%s in %s)", language, marker, root)
                return language, [f"cd {root} && {cmd}" for cmd in commands]

        if first_unsupported is None:
            for marker, language in _UNSUPPORTED_MARKERS.items():
                if marker in files:
                    first_unsupported = (root, language)
                    break

    if first_unsupported:
        directory, language = first_unsupported
        logger.warning(
            "Detected language=%s (in %s) but not supported for build validation — skipping Step 4",
            language, directory,
        )
        return language, []

    logger.warning("No language marker found in %s — skipping Step 4", code_dir)
    return None, []


def _runtime_binary(language: str) -> Optional[str]:
    """Returns the binary name that must be on PATH for this language to run."""
    return {"go": "go", "python": "python"}.get(language)
