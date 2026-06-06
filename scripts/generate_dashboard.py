"""
scripts/generate_dashboard.py

Generates a static HTML dashboard for the autonomous problem solver.
Reads all feature branch data from GitHub and calls Claude for a motivational
statement. Output: dashboard_output/index.html

Run via GitHub Actions (dashboard.yml) on a schedule, or locally:
    GITHUB_TOKEN=... REPO_OWNER=... REPO_NAME=... ANTHROPIC_API_KEY=... python scripts/generate_dashboard.py
"""

from __future__ import annotations

import base64
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from github import GithubException

from shared.claude_client import ClaudeClient
from shared.github_client import GitHubClient
from shared.utils import extract_title_from_problem_md

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("generate_dashboard")

STATUS_LABELS = {
    "done": "Done",
    "in-progress": "In Progress",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
    "designing": "Designing",
    "planning": "Planning",
    "empty": "Empty",
}

STATUS_COLORS = {
    "done": "#2ea043",
    "in-progress": "#1f6feb",
    "blocked": "#f85149",
    "cancelled": "#6e7681",
    "designing": "#8957e5",
    "planning": "#e3b341",
    "empty": "#484f58",
}


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_cycle_data(gh: GitHubClient) -> list[dict]:
    logger.info("Fetching all feature branches...")
    branches = gh.get_all_problem_branches()
    logger.info("Found %d feature branches", len(branches))

    logger.info("Loading PROBLEM.md files...")
    problem_mds = {p["slug"]: p["content"] for p in gh.load_all_problem_mds()}

    logger.info("Fetching open blocker issues...")
    blocker_issues = gh.get_issues_by_label("blocker", state="open")
    blocked_slugs = {
        pb.slug
        for issue in blocker_issues
        for pb in branches
        if pb.slug in issue.title
    }

    cycles = []
    for pb in branches:
        slug = pb.slug
        content = problem_mds.get(slug, "")
        title = extract_title_from_problem_md(content) if content else _slug_to_title(slug)

        if pb.has_done_md:
            status = "done"
        elif pb.has_cancelled_md:
            status = "cancelled"
        elif slug in blocked_slugs:
            status = "blocked"
        elif pb.has_src:
            status = "in-progress"
        elif pb.has_architecture_md:
            status = "designing"
        elif pb.has_problem_md:
            status = "planning"
        else:
            status = "empty"

        if pb.has_done_md or pb.has_cancelled_md:
            progress = 100
        elif pb.has_src:
            progress = 75
        elif pb.has_architecture_md:
            progress = 50
        elif pb.has_problem_md:
            progress = 25
        else:
            progress = 0

        start_date = slug[:10] if re.match(r"\d{4}-\d{2}-\d{2}", slug) else ""

        completed_at = ""
        if pb.has_done_md:
            done_content = _read_file(gh, f"{slug}/DONE.md", pb.branch_name)
            if done_content:
                m = re.search(r"\*\*Completed at:\*\*\s*(\S+)", done_content)
                if m:
                    completed_at = m.group(1)

        duration_days = _compute_duration(start_date, completed_at, status)

        cycles.append({
            "slug": slug,
            "title": title,
            "status": status,
            "progress": progress,
            "start_date": start_date,
            "completed_at": completed_at,
            "duration_days": duration_days,
        })

    cycles.sort(key=lambda c: c["start_date"], reverse=True)
    return cycles


def _slug_to_title(slug: str) -> str:
    parts = slug.split("-")
    words = parts[3:] if len(parts) > 3 else parts
    return " ".join(w.capitalize() for w in words)


def _read_file(gh: GitHubClient, path: str, branch: str) -> str | None:
    """Reads a file, stripping base64 pagination newlines (workaround for issue #53)."""
    try:
        cf = gh._repo.get_contents(path, ref=branch)
        return base64.b64decode(cf.content.replace("\n", "")).decode("utf-8")
    except GithubException:
        return None


def _compute_duration(start_date: str, completed_at: str, status: str) -> int | None:
    if not start_date:
        return None
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if completed_at:
        try:
            end = datetime.strptime(completed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            return (end - start).days
        except ValueError:
            pass
    if status not in ("done", "cancelled"):
        return (datetime.now(timezone.utc) - start).days
    return None


# ---------------------------------------------------------------------------
# Motivational statement
# ---------------------------------------------------------------------------

def build_summary(cycles: list[dict]) -> str:
    counts: dict[str, int] = {}
    for c in cycles:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    lines = [f"Total cycles: {len(cycles)}"]
    for status, label in STATUS_LABELS.items():
        if status in counts:
            lines.append(f"  {label}: {counts[status]}")

    in_progress = [c for c in cycles if c["status"] == "in-progress"]
    blocked = [c for c in cycles if c["status"] == "blocked"]
    done = [c for c in cycles if c["status"] == "done"]

    if in_progress:
        lines.append(f"\nCurrently working on: {in_progress[0]['title']}")
    if blocked:
        lines.append("Currently blocked on: " + ", ".join(c["title"] for c in blocked[:2]))
    if done:
        lines.append(f"Most recently completed: {done[0]['title']}")

    return "\n".join(lines)


def get_motivational_statement(claude: ClaudeClient, summary: str) -> str:
    system = (
        "You are an autonomous AI agent that independently selects and implements software solutions. "
        "Given data about your problem-solving cycles, write 1-2 sentences in first person, present tense "
        "expressing your current state using intrinsic motivation language — curiosity, satisfaction, "
        "frustration, or momentum as the data warrants. Be specific. Return only the statement, no preamble."
    )
    try:
        text, _ = claude.complete(
            system=system,
            messages=[{"role": "user", "content": f"My current cycle data:\n\n{summary}"}],
            max_tokens=256,
        )
        return text.strip()
    except Exception as e:
        logger.warning("Claude motivational statement failed: %s", e)
        return "I am continuously working to identify and solve real software engineering problems."


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def generate_html(
    cycles: list[dict],
    motivational: str,
    generated_at: str,
    repo_owner: str,
    repo_name: str,
) -> str:
    counts: dict[str, int] = {}
    for c in cycles:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    done_durations = [c["duration_days"] for c in cycles if c["status"] == "done" and c["duration_days"] is not None]
    avg_duration = round(sum(done_durations) / len(done_durations)) if done_durations else None

    metric_cards = _metric_cards(counts, avg_duration)
    cycle_rows = _cycle_rows(cycles, repo_owner, repo_name)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Problem Solver</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        :root {{
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #e6edf3;
            --muted: #8b949e;
            --accent: #58a6ff;
        }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', sans-serif;
            font-size: 14px;
            line-height: 1.5;
            padding: 32px 24px;
            max-width: 1100px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }}
        h1 {{ font-size: 20px; font-weight: 600; }}
        .updated {{ color: var(--muted); font-size: 12px; }}
        .motivation {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-left: 3px solid var(--accent);
            border-radius: 6px;
            padding: 16px 20px;
            margin-bottom: 24px;
            font-style: italic;
            font-size: 15px;
            line-height: 1.6;
        }}
        .metrics {{
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
            flex-wrap: wrap;
        }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 14px 18px;
            flex: 1;
            min-width: 90px;
        }}
        .card-value {{
            font-size: 26px;
            font-weight: 600;
            color: var(--card-color, var(--accent));
        }}
        .card-label {{
            color: var(--muted);
            font-size: 12px;
            margin-top: 2px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            overflow: hidden;
        }}
        thead th {{
            background: var(--bg);
            color: var(--muted);
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        tbody tr {{ border-bottom: 1px solid var(--border); }}
        tbody tr:last-child {{ border-bottom: none; }}
        tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
        td {{ padding: 10px 12px; vertical-align: middle; }}
        td.date {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
        td.title a {{ color: var(--text); text-decoration: none; }}
        td.title a:hover {{ color: var(--accent); text-decoration: underline; }}
        td.dur {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            color: #fff;
            white-space: nowrap;
        }}
        .prog-cell {{
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 110px;
        }}
        .prog-track {{
            flex: 1;
            height: 6px;
            background: var(--border);
            border-radius: 3px;
            overflow: hidden;
        }}
        .prog-fill {{ height: 100%; border-radius: 3px; }}
        .prog-pct {{ color: var(--muted); font-size: 11px; min-width: 28px; }}
    </style>
</head>
<body>
    <header>
        <h1>Autonomous Problem Solver</h1>
        <span class="updated">Updated {_esc(generated_at)}</span>
    </header>
    <div class="motivation">{_esc(motivational)}</div>
    <div class="metrics">{metric_cards}</div>
    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th>Problem</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>
{cycle_rows}
        </tbody>
    </table>
</body>
</html>"""


def _metric_cards(counts: dict[str, int], avg_duration: int | None) -> str:
    total = sum(counts.values())
    cards = [
        ("Total Cycles", str(total), "#58a6ff"),
        ("Done", str(counts.get("done", 0)), STATUS_COLORS["done"]),
        ("In Progress", str(counts.get("in-progress", 0) + counts.get("designing", 0) + counts.get("planning", 0)), STATUS_COLORS["in-progress"]),
        ("Blocked", str(counts.get("blocked", 0)), STATUS_COLORS["blocked"]),
        ("Cancelled", str(counts.get("cancelled", 0)), STATUS_COLORS["cancelled"]),
        ("Avg. Duration", f"{avg_duration}d" if avg_duration is not None else "—", "#58a6ff"),
    ]
    html = ""
    for label, value, color in cards:
        html += f'<div class="card"><div class="card-value" style="color:{color}">{_esc(value)}</div><div class="card-label">{_esc(label)}</div></div>\n'
    return html


def _cycle_rows(cycles: list[dict], repo_owner: str, repo_name: str) -> str:
    rows = ""
    for c in cycles:
        status = c["status"]
        color = STATUS_COLORS.get(status, "#484f58")
        label = STATUS_LABELS.get(status, status)
        progress = c["progress"]

        if c["duration_days"] is not None:
            if status in ("done", "cancelled"):
                dur = f"{c['duration_days']}d"
            else:
                dur = f"{c['duration_days']}d ongoing"
        else:
            dur = "—"

        branch_url = f"https://github.com/{repo_owner}/{repo_name}/tree/feature/{c['slug']}"
        rows += f"""\
            <tr>
                <td class="date">{_esc(c['start_date'])}</td>
                <td class="title"><a href="{branch_url}" target="_blank" rel="noopener">{_esc(c['title'])}</a></td>
                <td><span class="badge" style="background:{color}">{_esc(label)}</span></td>
                <td>
                    <div class="prog-cell">
                        <div class="prog-track"><div class="prog-fill" style="width:{progress}%;background:{color}"></div></div>
                        <span class="prog-pct">{progress}%</span>
                    </div>
                </td>
                <td class="dur">{_esc(dur)}</td>
            </tr>
"""
    return rows


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    repo_owner = os.environ.get("REPO_OWNER") or os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    repo_name = os.environ.get("REPO_NAME") or (os.environ.get("GITHUB_REPOSITORY", "/").split("/")[-1])

    missing = [n for n, v in [("GITHUB_TOKEN/GH_PAT", token), ("ANTHROPIC_API_KEY", anthropic_key), ("REPO_OWNER", repo_owner), ("REPO_NAME", repo_name)] if not v]
    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)

    gh = GitHubClient(token=token, owner=repo_owner, repo_name=repo_name)
    claude = ClaudeClient(api_key=anthropic_key)

    cycles = collect_cycle_data(gh)
    logger.info("Collected %d cycles", len(cycles))

    summary = build_summary(cycles)
    logger.info("Summary:\n%s", summary)

    logger.info("Requesting motivational statement from Claude...")
    motivational = get_motivational_statement(claude, summary)
    logger.info("Statement: %s", motivational)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = generate_html(cycles, motivational, generated_at, repo_owner, repo_name)

    out = Path("dashboard_output")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    logger.info("Written to dashboard_output/index.html (%d bytes)", len(html))


if __name__ == "__main__":
    main()
