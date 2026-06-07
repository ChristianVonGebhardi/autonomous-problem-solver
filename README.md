# Autonomous Problem Solver

An autonomous AI agent that identifies real-world problems daily, designs software architectures, and builds working MVPs — entirely on its own, with human-in-the-loop support for blockers.

## How it works

| Step | Where | What happens |
|---|---|---|
| **1 — Problem Brainstorm** | GitHub Actions (daily, 00:00 UTC) | Claude searches the web, avoids past problems, picks the best new candidate, writes `PROBLEM.md` |
| **2 — Architecture Design** | GitHub Actions (same run) | Claude designs the best-fit stack, writes `ARCHITECTURE.md` with a Mermaid diagram |
| **2.5 — Peer Review** | GitHub Actions (same run) | Claude reviews PROBLEM.md as a domain expert and ARCHITECTURE.md as a software architect; commits `REVIEW.md` to the feature branch |
| **3 — MVP Implementation** | Railway (always-on worker) | Claude implements the MVP (with REVIEW.md as additional context), commits source files, opens blocker Issues if stuck, writes `DONE.md` when complete |
| **4 — Build Validation** | Railway (same worker, runs after Step 3) | Clones the feature branch, detects language, runs build/compile commands; up to 3 Claude-assisted fix attempts; labels PR `done` on pass or `needs-review` on failure |
| **Dashboard** | GitHub Actions (after each daily cycle) | Reads all feature branch data, calls Claude for a motivational statement, generates a static HTML page deployed to GitHub Pages |

Each problem lives on its own branch: `feature/YYYY-MM-DD-problem-slug`.

---

## Repository structure

```
.
├── .github/
│   └── workflows/
│       ├── daily_cycle.yml       # Steps 1 & 2 — runs daily at 00:00 UTC
│       └── dashboard.yml         # Dashboard — runs after daily cycle completes, deploys to GitHub Pages
├── shared/
│   ├── build_detector.py         # Language detection — returns build commands for Step 4
│   ├── claude_client.py          # Anthropic API wrapper (web search + retry)
│   ├── github_client.py          # PyGithub wrapper (branches, files, issues, PRs)
│   ├── markers.py                # DONE.md and CANCELLED.md generators
│   ├── parsers.py                # Parses Claude's structured Step 2 & 3 output
│   ├── prompts.py                # All Claude prompts in one place
│   └── utils.py                  # Slug generation, timestamps, text helpers
├── worker/
│   ├── main.py                   # Railway persistent worker — polling loop
│   ├── step3.py                  # Step 3 runner (fresh + resumed cycles)
│   └── step4.py                  # Step 4 runner (build validation + Claude fix loop)
├── scripts/
│   ├── run_step4.py              # Run Step 4 locally against any completed feature branch
│   └── generate_dashboard.py     # Generate dashboard HTML (also run by dashboard.yml)
├── actions_runner.py             # GitHub Actions entry point (Steps 1 & 2)
├── requirements.txt
├── Procfile                      # Railway process definition
├── railway.toml                  # Railway build & deploy config
└── .env.example                  # Template for local development
```

---

## Setup

### 1. Fork / create the repository

Create a repository at `github.com/{you}/autonomous-problem-solver`. The repository must be **public** for the GitHub Pages dashboard to work.

Make sure the `main` branch exists (push an initial commit if needed — this README works fine as the first commit).

### 2. Configure GitHub Actions secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |

The `GITHUB_TOKEN` secret is provided automatically by GitHub Actions — you do not need to add it.

### 3. Test the GitHub Actions workflow

The workflow is already configured in `.github/workflows/daily_cycle.yml`. It triggers daily at **00:00 UTC**.

To test it manually: go to **Actions → Daily Problem Cycle → Run workflow**.

A successful run creates a new `feature/*` branch with `PROBLEM.md` and `ARCHITECTURE.md` committed, and opens a tracking Issue labelled `in-progress`.

> **Note:** Use **Run workflow** (the green button) to trigger a fresh run. The **Re-run jobs** button replays the original run with the original code snapshot — it will not pick up new commits.

### 4. Create a GitHub Personal Access Token for the Railway worker

The Railway worker operates outside GitHub Actions and cannot use `GITHUB_TOKEN`. It needs a PAT.

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Create a token scoped to this repository with the following permissions:
   - **Contents**: Read and write
   - **Issues**: Read and write
   - **Pull requests**: Read and write
   - **Metadata**: Read-only (required)
3. Copy the token — you'll use it in the next step as `GH_PAT`.

### 5. Deploy to Railway

1. Go to [railway.app](https://railway.app) and create a new project.
2. Connect your GitHub repository.
3. Railway will detect the `Procfile` / `railway.toml` automatically.
4. Add the following **environment variables** in Railway's service settings:

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `GH_PAT` | The PAT you created in step 4 |
| `REPO_OWNER` | Your GitHub username |
| `REPO_NAME` | `autonomous-problem-solver` |
| `POLL_INTERVAL_SECONDS` | `60` (or adjust as needed) |

5. Deploy. The worker will start and begin polling immediately.

> **Note:** Railway's free tier suspends workers after inactivity. Use the **Hobby** plan ($5/mo) or higher to keep the worker always-on.

---

## Cycle lifecycle

```
in_progress → blocked → in_progress   (loop until resolved)
             ↓
           cancelled → resumed → in_progress → done
```

### Labels used on GitHub Issues

| Label | Meaning |
|---|---|
| `in-progress` | Step 3 is running |
| `blocker` | Agent is waiting for human input |
| `blocker-resolved` | Human has resolved the blocker — worker resumes |
| `cycle-cancelled` | Human closed the Issue — worker writes `CANCELLED.md` |
| `cycle-resume` | Human wants to restart a cancelled cycle |
| `done` | MVP complete, Step 4 build validation passed — PR opened |
| `needs-review` | MVP complete but Step 4 build validation failed after 3 fix attempts — PR opened for human review |

### Responding to a blocker

When the agent is stuck, it opens an Issue titled `[BLOCKER] {slug} — {summary}` with:
- What is blocked
- What was attempted
- 2–4 resolution options
- Impact if unresolved

**To unblock:** Resolve the issue (add an API key, grant access, etc.), add a comment describing what you did, then add the label `blocker-resolved`. The Railway worker detects this and resumes within one poll interval.

**To cancel:** Close the Issue and add the label `cycle-cancelled`. Optionally leave a comment explaining why. The worker will write `CANCELLED.md` preserving all context.

**To resume a cancelled cycle:** Reopen the original Issue and add `cycle-resume`, or open a new Issue with `cycle-resume` in the title and the problem slug in the body.

---

## Dashboard

A live status dashboard is available at:
**https://ChristianVonGebhardi.github.io/autonomous-problem-solver/**

It refreshes automatically after each daily cycle run (Steps 1 & 2) via GitHub Actions, and can be triggered manually via `workflow_dispatch`. It shows:
- A Claude-generated motivational statement based on the current cycle state
- Metric cards: total cycles, done, in progress, blocked, cancelled, average duration
- A per-cycle table with status badge, progress bar (25 / 50 / 75 / 100% by lifecycle stage), and duration

The dashboard is generated by `scripts/generate_dashboard.py` and deployed to the `gh-pages` branch by `.github/workflows/dashboard.yml`. To generate it locally:

```bash
export GITHUB_TOKEN=$GH_PAT
export REPO_OWNER=ChristianVonGebhardi
export REPO_NAME=autonomous-problem-solver
export ANTHROPIC_API_KEY=...
python scripts/generate_dashboard.py
# Output: dashboard_output/index.html
```

---

## Local development

```bash
# Clone and install
git clone https://github.com/ChristianVonGebhardi/autonomous-problem-solver
cd autonomous-problem-solver
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY, GH_PAT, REPO_OWNER, REPO_NAME

# Test Steps 1 & 2 locally
export $(cat .env | xargs)
export GITHUB_TOKEN=$GH_PAT   # Actions runner reads GITHUB_TOKEN
python -c "from actions_runner import run_steps_1_and_2; run_steps_1_and_2()"

# Run the Railway worker locally
python worker/main.py
```

---

## Memory and deduplication

At the start of every daily run, the agent reads all `PROBLEM.md` files from every `feature/*` branch (including cancelled and completed cycles). It uses this list to avoid selecting duplicate or adjacent problems.

Once the problem archive grows beyond ~50 entries, consider adding a ChromaDB vector store for semantic similarity search — the spec notes this upgrade path explicitly.

---

## Secrets policy

- **Never commit** API keys, PATs, or credentials.
- The Actions runner uses the auto-provided `GITHUB_TOKEN` (scoped to the run).
- The Railway worker uses `GH_PAT` as a Railway environment variable.
- Problem source code may require its own secrets (e.g. a third-party API key for the MVP). These go in Railway environment variables, referenced in `ARCHITECTURE.md` as anticipated blockers.

---

## Tuning

| Parameter | Where | Default | Effect |
|---|---|---|---|
| `POLL_INTERVAL_SECONDS` | Railway env var | `60` | How often the worker checks for new branches / label changes |
| `MAX_TOKENS` in `claude_client.py` | Code | `8192` | Max output per Claude call |
| Cron schedule | `daily_cycle.yml` | `0 0 * * *` | When Steps 1 & 2 run |
| Step 1 `max_tokens` | `actions_runner.py` | `4096` | Max length of PROBLEM.md generation |

## Known Issues

### Rate limiting on free tier
The free tier has a 30,000 token-per-minute limit. When Steps 1 and 2 run back-to-back with large prompts (especially when web search generates verbose results), the limit can be exceeded even with pauses between steps.

**Mitigation:** The agent automatically retries rate-limited requests, and if all retries fail, it reduces prompt size and tries once more before giving up.

**Solution:** Upgrade to a higher Anthropic Tier, e.g. Tier 2 ($40/month spend cap) for 80,000 TPM, which eliminates this issue.