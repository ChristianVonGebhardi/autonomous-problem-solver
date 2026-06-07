# Lessons Learned — Autonomous Problem Solver

A running log of hard-won insights from building and operating this system.
Updated after the Step 2.5 peer review and dashboard milestones (June 2026).

---

## Architecture & Design

### The system works — trust the design
The multi-step pipeline (GitHub Actions → Railway worker → Claude API) is sound.
Early failures were bugs in the implementation, not flaws in the architecture.
When something breaks, look for the specific bug before questioning the design.

### Agentic loops need hard limits everywhere
Any loop that can auto-repeat must have a maximum iteration count enforced in persistent
storage — not in memory. Memory resets on container restart. A `RESUME_COUNT` file on the
branch survives restarts and prevents infinite loops even after unexpected redeploys.

### In-memory state is fragile across sessions
`processed_fresh` and `processed_resumed` are in-memory Python sets. They work within a
single worker session but reset on container restart. Design the system so that branch/issue
state on GitHub is the single source of truth, and in-memory sets are only a performance
optimisation — never a correctness requirement.

### Streaming is required for large outputs
The Anthropic Python SDK raises a `ValueError` for non-streaming requests that may exceed
roughly 10 minutes. Any Step 3 call with `max_tokens` above ~8192 requires
`use_streaming=True`. Streaming with `stream.get_final_message()` returns the same `Message`
object as `.create()` — it is a drop-in replacement with no downstream parsing changes.

### `stop_reason` is load-bearing information
Always surface `stop_reason` from the Claude API response. `max_tokens` means truncation —
not an error, not completion. Treating truncation as an ambiguous response was the root cause
of many false `[BLOCKER]` issues. Once `stop_reason` was threaded through to the parser and
dispatcher, the entire auto-resume flow became reliable.

---

## Claude Prompt Engineering

### The last instruction Claude sees matters most
Critical formatting instructions (e.g. "start with `## `") are more effective at the end of
the system prompt than at the beginning. Claude's attention is stronger near the end of a
long context. For anti-preamble instructions, add a `CRITICAL:` block as the very last lines
of the system prompt.

### Artifact labels in prompts leak into outputs
Naming sections `ARTIFACT 1:` and `ARTIFACT 2:` in the prompt causes Claude to echo those
labels into the output. Use positional instructions instead: "start with prose, then output
the delimiter, then output only the Mermaid block."

### Delimiter syntax must be unmistakable
The `<<<FILE: path>>>` / `<<<END_FILE>>>` / `<<<MVP_COMPLETE>>>` / `<<<BLOCKER>>>` delimiters
work reliably because they are visually distinct from any natural language Claude would
generate. Angle-bracket-heavy syntax with all-caps keywords is a good pattern for
structured output parsing in agentic systems.

### Missing terminal blocks are almost always truncation
If Claude emits files but no `<<<MVP_COMPLETE>>>` or `<<<BLOCKER>>>`, the most likely cause
is `stop_reason=max_tokens` — Claude ran out of tokens before finishing. Check `stop_reason`
before treating the response as a prompt compliance failure.

### Sources and structure must be explicitly requested
Claude will not include source citations, one-sentence problem statements, or other
structured fields unless they are listed in the output format with explicit placeholder text.
Vague instructions like "include supporting evidence" are ignored. Explicit format lines like
`**Problem statement:** <one sentence>` and `**Sources:** - <URL>` produce reliable output.

---

## GitHub Actions & CI

### Step 2.5 adds a peer review without blocking autonomous operation
The review step (domain expert + software architect personas in one Claude call) surfaces weak
problem definitions and flawed architectures before the Railway worker spends tokens on
implementation. The verdict is informational — the cycle always proceeds regardless. This is
the right trade-off: a blocking gate would require human intervention to unblock, breaking
fully autonomous operation. If the reviews consistently flag the same weaknesses, the right
fix is to improve the Step 1/2 prompts, not to add a gate.

### 120 seconds between Steps 1 and 2 is not always enough
The 30,000 input token per minute rate limit is hit consistently when Step 1 produces a
long PROBLEM.md and Step 2 immediately consumes it along with the full system prompt.
The SDK retries with exponential backoff and recovers, but consider increasing the delay
to 180s if rate limit retries become frequent.

---

## Railway Worker Operations

### Railway is your test environment for anything involving Claude
The full system requires GitHub API, Anthropic API, and Railway all running together.
Local testing of Step 3 is not practical without mocking all three. Accept Railway as the
integration test environment and invest in good logging instead of trying to replicate the
environment locally.

### Logs are the only debugger
There are no breakpoints in a Railway worker. Structured `logger.info` calls at every state
transition — branch qualification, Claude call start, stop_reason, file commit, resume
scheduling — are the equivalent of a serial port in embedded systems. Log early, log often,
log the values that matter (slug, stop_reason, resume count, issue number).

### Container restarts reset in-memory state silently
Railway may restart worker containers without a new deployment — due to memory limits,
platform maintenance, or free-tier policies. Any correctness-critical state must live in
GitHub (branch files, issue labels), not in Python variables. In-memory sets like
`processed_resumed` should only prevent redundant work within a session, never gate
correctness.

### `processed_resumed` must not block auto-resume
After `_handle_truncation` adds `cycle-resume` to a CYCLE issue and returns `"resuming"`,
the calling code in `_handle_resumes` must not add the slug to `processed_resumed`. If it
does, the worker will detect the `cycle-resume` label on the next poll but skip it. The fix:
only add to `processed_resumed` when result is not `"resuming"`.

---

## MVP Quality & Step 4

### Step 4 is a compile/syntax gate, not a functional test
Step 4 validates that the generated code can be built, not that it works. Specifically:
- **Python**: `python -m compileall -q .` — syntax errors only, no dependency installation
- **Go**: `go mod tidy` + `go build ./...` + `go vet ./...` — full compile + static analysis
- **Node/Rust/Java/others**: skipped (unsupported), counted as passed

A `done` label means the code is syntactically/structurally valid. Whether the app starts,
the API responds, or the UI renders is still a human concern.

### Step 4 infrastructure failures always pass through
Clone failures, missing runtime binaries, and unsupported languages all return `passed=True`.
Step 4 is best-effort — it must never block PR creation for a completed MVP.

### Claude generates syntactically plausible but uncompiled code
Generated MVPs are architecturally sound and substantially complete, but may contain
compilation errors (unused variables, incomplete `go.sum` files, missing imports). Step 4's
Claude fix loop (up to 3 attempts) handles these automatically for Go and Python.

### `go mod tidy` is a required setup step for Go MVPs
Claude generates `go.mod` and `go.sum` but does not run `go mod tidy` during generation.
The committed `go.sum` may be incomplete. Step 4 runs `go mod tidy` as the first command,
which fills in the missing entries before `go build`.

### One line fix, working CLI — that is the benchmark
The first fully validated MVP (real-time cloud spending circuit breaker) worked after a
single one-line fix: removing an unused variable. It produced a working Go CLI with
subcommands, real-time simulation, ASCII dashboards, YAML policy engine, and cost
estimation. The ratio of human effort to autonomous output is the metric that matters.

### MVP source code is nested arbitrarily deep
Claude structures MVPs as `slug/project-name/[backend|src|cmd]/` — the language marker
(`requirements.txt`, `go.mod`) can be two or three levels below the slug root, not one.
`build_detector.py` uses `os.walk()` for a full recursive search. Do not replace this with
a fixed-depth scan — the nesting depth varies per MVP.

### `aptPkgs` is additive; `nixPkgs` replaces in nixpacks.toml
Adding `nixPkgs = ["go", "git"]` to `nixpacks.toml` replaced Nixpacks' auto-detected Python
provider, causing `python: command not found` at Railway startup (exit 127). The fix:
use `aptPkgs = ["golang-go", "git"]` under `[phases.setup]` — APT packages are installed
on top of the auto-detected Nix environment, not instead of it.

---

## GitHub Issues & Housekeeping

### GitHub web UI loses issues with complex label combinations
When a repository accumulates many issues with overlapping label sets, the GitHub web UI
filter/search can stop showing them — even though they exist and are accessible via direct
URL and CLI. Workaround: add a comment to hidden issues to force re-indexing. The CLI
(`gh issue list`) always shows all issues correctly.

### Stale blocker issues should be closed promptly
When a `[BLOCKER]` issue is created due to a now-fixed bug (e.g. truncation causing missing
terminal block), close it immediately with a comment explaining the root cause. Open blocker
issues that are no longer valid create confusion and may prevent the worker from qualifying
branches for Step 3.

### Manual cycle close procedure
When a cycle needs to be closed manually (MVP substantially complete but auto-complete did
not fire): (1) remove `cycle-resume` label from CYCLE issue, (2) close stale BLOCKER issues,
(3) commit `DONE.md` via `gh api --method PUT`, (4) update CYCLE issue labels to `done`,
(5) open PR via `gh pr create`. Always run `gh` commands from the project directory, not
from an unrelated directory like `Downloads`.

---

## Process & Workflow

### Bulk validation saves API credits
Group prompt engineering fixes (Step 1 and Step 2 system prompt changes) into one GitHub
Actions run. Group Railway-side fixes (worker logic, streaming, auto-resume) into one
Railway validation run. Do not run a full pipeline to validate a one-line Python change.

### The embedded systems analogy holds
Building this system is structurally identical to embedded systems development: write code
locally, deploy to target hardware (Railway), observe via logs (serial port equivalent),
iterate. The main difference is cost — each Railway + Claude API test cycle has a real dollar
cost, which imposes healthy discipline on the size of each change.

---

## Dashboard & GitHub Pages

### GitHub Pages requires the repo to be public
Free GitHub Pages is only available for public repositories. The dashboard was developed
against a private repo and activated by making the repo public. If the repo is ever made
private again, the Pages site will stop serving.

### `gh-pages` is a GitHub convention, not an arbitrary name
GitHub Pages requires this specific branch name when source is set to "Deploy from a branch"
in repository settings. The `peaceiris/actions-gh-pages` action also defaults to it.

### `force_orphan: true` is the right default for generated static sites
Every dashboard deployment rewrites the `gh-pages` branch from scratch as an orphan commit.
This prevents the branch from accumulating history and avoids merge conflicts if the generated
HTML ever changes significantly. It also means the trigger frequency is irrelevant to branch
size — whether the dashboard runs once a day or on-demand, the branch stays a single commit.

### GitHub Actions can call the Anthropic API — no extra infra needed
The dashboard's Claude motivational statement is generated inside a GitHub Actions job using
`ANTHROPIC_API_KEY` from Actions secrets. This avoids the need for a separate Railway service
just to call Claude. The pattern — Actions runner + Anthropic SDK + static output — works
cleanly for any read-only, scheduled Claude call.

### Trigger the dashboard on `workflow_run`, not on a schedule
A 30-minute cron would run the dashboard ~48 times per day regardless of whether anything
changed — burning GitHub Actions minutes and Anthropic API tokens on Claude motivational
statement calls. The `workflow_run` trigger on `Daily Problem Cycle` fires exactly once per
day, immediately after new cycle content is created. `workflow_dispatch`
covers manual refreshes. If Step 3/4 completions later become important to reflect promptly,
add a daily fallback cron then — don't pre-optimise for it.

### Use `GITHUB_TOKEN` in Actions workflows, `GH_PAT` in Railway
Actions jobs receive an auto-provided `GITHUB_TOKEN` scoped to the run. The Railway worker
cannot use it and needs a long-lived PAT (`GH_PAT`). Never confuse the two: using `GH_PAT`
inside an Actions job works but is unnecessary and couples the workflow to a secret rotation
schedule. Using `GITHUB_TOKEN` on Railway would fail silently after the token expires.
