# Lessons Learned — Autonomous Problem Solver

A running log of hard-won insights from building and operating this system.
Updated after the v0.3.1 milestone sprint (May 2026).

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

### 120 seconds between Steps 1 and 2 is not always enough
The 30,000 input token per minute rate limit is hit consistently when Step 1 produces a
long PROBLEM.md and Step 2 immediately consumes it along with the full system prompt.
The SDK retries with exponential backoff and recovers, but consider increasing the delay
to 180s if rate limit retries become frequent.

### GitHub Actions logs are in UTC
The scheduler fires at 00:00 UTC. Local time offsets (e.g. UTC-6 for CST, UTC-8 for PST)
mean the workflow appears to run at 6 PM or 8 PM local time the previous day. Always
cross-reference logs in UTC to avoid confusion when correlating Actions and Railway timestamps.

### Closing an issue via commit message is an intent, not a validation
`closes #N` in a commit message closes the issue the moment the commit is pushed to the
default branch — before any runtime validation. For bugs that require Railway deployment to
validate (streaming, auto-resume, Claude API behaviour), omit the closing keyword, validate
on Railway, then close manually with a comment linking the commit hash.

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

### Claude generates syntactically plausible but uncompiled code
Generated MVPs are architecturally sound and substantially complete, but may contain
compilation errors (unused variables, incomplete `go.sum` files, missing imports). These are
minor — the real-world test of the Go circuit breaker MVP required exactly one line fix
after `go mod tidy`. A Step 4 automated build/test loop would catch these automatically.

### `go mod tidy` is a required setup step for Go MVPs
Claude generates `go.mod` and `go.sum` but does not run `go mod tidy` during generation.
The committed `go.sum` may be incomplete. Any Go MVP README should include `go mod tidy`
as the first setup step before `go build` or `go run`.

### One line fix, working CLI — that is the benchmark
The first fully validated MVP (real-time cloud spending circuit breaker) worked after a
single one-line fix: removing an unused variable. It produced a working Go CLI with
subcommands, real-time simulation, ASCII dashboards, YAML policy engine, and cost
estimation. The ratio of human effort to autonomous output is the metric that matters.

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

### Validate before closing issues
Do not use `closes #N` in commit messages for bugs that require runtime validation on
Railway. Push the fix, deploy, observe the logs, then close manually with a comment linking
the commit. This keeps the issue tracker honest — a closed issue means the fix was confirmed
working, not just pushed.

### Dedicated commits per issue
One commit per issue fix makes `git log` a useful audit trail and simplifies bisection if a
regression appears. Use the issue number in the commit message body even when not using the
`closes` keyword: `fix: increase Step 3 max_tokens to 32768 — related to #29`.

### Bulk validation saves API credits
Group prompt engineering fixes (Step 1 and Step 2 system prompt changes) into one GitHub
Actions run. Group Railway-side fixes (worker logic, streaming, auto-resume) into one
Railway validation run. Do not run a full pipeline to validate a one-line Python change.

### The embedded systems analogy holds
Building this system is structurally identical to embedded systems development: write code
locally, deploy to target hardware (Railway), observe via logs (serial port equivalent),
iterate. The main difference is cost — each Railway + Claude API test cycle has a real dollar
cost, which imposes healthy discipline on the size of each change.
