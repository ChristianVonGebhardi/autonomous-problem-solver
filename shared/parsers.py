"""
shared/parsers.py

Parses structured output from Claude responses.
All parsing is tolerant: logs warnings instead of raising on malformed output.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 2 parser
# ---------------------------------------------------------------------------

STEP2_DELIMITER = "---ARCHITECTURE-DIAGRAM---"


def parse_step2_output(raw: str) -> tuple[str, str]:
    """
    Splits Step 2 output into (architecture_prose, mermaid_block).

    Returns the mermaid block as a full ```mermaid ... ``` fenced block,
    ready to be embedded in ARCHITECTURE.md.

    Falls back gracefully if the delimiter is missing.
    """
    if STEP2_DELIMITER in raw:
        parts = raw.split(STEP2_DELIMITER, 1)
        prose = parts[0].strip()
        diagram_raw = parts[1].strip()
    else:
        logger.warning("Step 2 delimiter not found — attempting to extract mermaid block from full output")
        prose = raw.strip()
        diagram_raw = raw.strip()

    # Extract ```mermaid block from diagram_raw
    mermaid_match = re.search(r"```mermaid(.+?)```", diagram_raw, re.DOTALL)
    if mermaid_match:
        mermaid_block = f"```mermaid{mermaid_match.group(1)}```"
    else:
        logger.warning("No ```mermaid block found in Step 2 output — using placeholder")
        mermaid_block = "```mermaid\nflowchart TD\n    A[Architecture diagram not generated]\n```"

    # If prose accidentally contains the mermaid block, strip it out
    prose = re.sub(r"```mermaid.+?```", "", prose, flags=re.DOTALL).strip()

    return prose, mermaid_block


def build_architecture_md(prose: str, mermaid_block: str) -> str:
    """Combines prose and diagram into a single ARCHITECTURE.md string."""
    return f"{prose}\n\n## Architecture Diagram\n\n{mermaid_block}\n"


# ---------------------------------------------------------------------------
# Step 3 parser
# ---------------------------------------------------------------------------

FILE_START_RE = re.compile(r"<<<FILE:\s*(.+?)>>>")
FILE_END = "<<<END_FILE>>>"
MVP_COMPLETE_START = "<<<MVP_COMPLETE>>>"
MVP_COMPLETE_END = "<<<END_MVP_COMPLETE>>>"
BLOCKER_START = "<<<BLOCKER>>>"
BLOCKER_END = "<<<END_BLOCKER>>>"


@dataclass
class Step3Output:
    files: dict[str, str] = field(default_factory=dict)  # path -> content
    mvp_complete: bool = False
    mvp_summary: str = ""
    blocker: Optional["BlockerInfo"] = None
    parse_warnings: list[str] = field(default_factory=list)


@dataclass
class BlockerInfo:
    summary: str = ""
    what_is_blocked: str = ""
    what_was_attempted: str = ""
    resolution_options: list[str] = field(default_factory=list)
    impact_if_unresolved: str = ""


def parse_step3_output(raw: str) -> Step3Output:
    """
    Parses Claude's Step 3 response into structured output.
    Handles files, MVP_COMPLETE, and BLOCKER sections.
    """
    result = Step3Output()

    # --- Parse files ---
    pos = 0
    while pos < len(raw):
        m = FILE_START_RE.search(raw, pos)
        if not m:
            break
        path = m.group(1).strip()
        content_start = m.end()
        end_pos = raw.find(FILE_END, content_start)
        if end_pos == -1:
            result.parse_warnings.append(f"No <<<END_FILE>>> found for <<<FILE: {path}>>> — skipping")
            break
        content = raw[content_start:end_pos]
        # Strip a single leading newline if present (delimiter formatting artifact)
        if content.startswith("\n"):
            content = content[1:]
        if content.endswith("\n"):
            content = content[:-1]
        result.files[path] = content
        logger.debug("Parsed file: %s (%d chars)", path, len(content))
        pos = end_pos + len(FILE_END)

    # --- Parse MVP_COMPLETE ---
    mvp_start = raw.find(MVP_COMPLETE_START)
    if mvp_start != -1:
        summary_start = mvp_start + len(MVP_COMPLETE_START)
        mvp_end = raw.find(MVP_COMPLETE_END, summary_start)
        if mvp_end != -1:
            result.mvp_complete = True
            result.mvp_summary = raw[summary_start:mvp_end].strip()
            logger.info("MVP marked complete: %s", result.mvp_summary[:120])
        else:
            result.parse_warnings.append("<<<MVP_COMPLETE>>> found but no <<<END_MVP_COMPLETE>>>")

    # --- Parse BLOCKER ---
    blocker_start = raw.find(BLOCKER_START)
    if blocker_start != -1:
        b_content_start = blocker_start + len(BLOCKER_START)
        blocker_end = raw.find(BLOCKER_END, b_content_start)
        if blocker_end != -1:
            blocker_text = raw[b_content_start:blocker_end].strip()
            result.blocker = _parse_blocker_block(blocker_text)
            logger.info("Parsed BLOCKER: %s", result.blocker.summary)
        else:
            result.parse_warnings.append("<<<BLOCKER>>> found but no <<<END_BLOCKER>>>")

    if result.parse_warnings:
        for w in result.parse_warnings:
            logger.warning("Step3 parse warning: %s", w)

    return result


def _parse_blocker_block(text: str) -> BlockerInfo:
    """
    Parses the contents of a <<<BLOCKER>>> block into a BlockerInfo.
    Format is key: value lines with a special RESOLUTION_OPTIONS list.
    """
    b = BlockerInfo()
    lines = text.splitlines()
    current_key: Optional[str] = None
    options_mode = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("SUMMARY:"):
            b.summary = stripped[len("SUMMARY:"):].strip()
            current_key = "summary"
            options_mode = False
        elif stripped.startswith("WHAT_IS_BLOCKED:"):
            b.what_is_blocked = stripped[len("WHAT_IS_BLOCKED:"):].strip()
            current_key = "what_is_blocked"
            options_mode = False
        elif stripped.startswith("WHAT_WAS_ATTEMPTED:"):
            b.what_was_attempted = stripped[len("WHAT_WAS_ATTEMPTED:"):].strip()
            current_key = "what_was_attempted"
            options_mode = False
        elif stripped.startswith("RESOLUTION_OPTIONS:"):
            options_mode = True
            current_key = None
        elif stripped.startswith("IMPACT_IF_UNRESOLVED:"):
            b.impact_if_unresolved = stripped[len("IMPACT_IF_UNRESOLVED:"):].strip()
            current_key = "impact"
            options_mode = False
        elif options_mode and stripped.startswith("-"):
            b.resolution_options.append(stripped[1:].strip())
        elif current_key and stripped:
            # Multi-line continuation
            if current_key == "what_is_blocked":
                b.what_is_blocked += " " + stripped
            elif current_key == "what_was_attempted":
                b.what_was_attempted += " " + stripped
            elif current_key == "impact":
                b.impact_if_unresolved += " " + stripped

    return b
