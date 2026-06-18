# Lessons Learned — license-guard MVP

**Session date:** 2026-06-18
**Tester:** Christian von Gebhardi + Claude Sonnet 4.6
**Result:** All bugs resolved. Full stack working end-to-end. 18/18 tests pass.

---

## What we learned

### 1. AI-generated code requires a mandatory end-to-end run phase

8 distinct bugs across 7 files were invisible to static analysis and unit tests. They only appeared when the full stack was actually started. The autonomous solver closed the cycle ("chore: close cycle") without ever executing the generated system. A validation step — boot, seed, run demo, check dashboard — must be part of the definition of done for every MVP.

### 2. Library version mismatches are a silent killer

React Query v5 changed the `refetchInterval` callback signature from `(data) => ...` to `(query) => query.state.data...`. The generated code used the v4 API. The AI wrote code against a mental model of the library that did not match the installed version. Rule: generated code should reference the library versions in `package.json`/`requirements.txt` and be validated against those exact versions, not general knowledge.

### 3. Vite env vars are baked at BUILD time, not at runtime

A `VITE_` variable set in docker-compose `environment:` has no effect on a built frontend image. Vite only reads these variables during `npm run build` (inside the Dockerfile). The fix is either:
- Pass them as Docker build args (`ARG VITE_API_URL` in Dockerfile + `build.args` in docker-compose), or
- Provide a `.env.production` file that is present when the image is built.

Missing this caused the dashboard to make all API requests to its own port (the static server), get HTML back instead of JSON, and crash Recharts on `undefined.length`.

### 4. psycopg2 misparses `::` as a second named parameter

In SQLAlchemy `text()` queries, `:embedding::vector` makes psycopg2 treat `:embedding:` as one named parameter and `:vector` as another. The SQL sent to PostgreSQL is unsubstituted and causes a syntax error. Always use `CAST(:param AS type)` syntax instead of `:param::type` when combining psycopg2 named parameters with PostgreSQL type casts.

### 5. numpy numeric types crash psycopg2 serialization

`datasketch` returns `numpy.uint64` values in MinHash signatures. psycopg2 cannot serialize these to a PostgreSQL `ARRAY(Integer())` column. Always cast: `[int(x) for x in minhash]` before storing numpy numeric arrays via SQLAlchemy.

### 6. `python -m rq` does not work

The `rq` package does not expose a `__main__.py` module, so `python -m rq worker ...` fails with `No module named rq.__main__`. The correct invocation is `rq worker --url ...` directly.

### 7. PostgreSQL aborts the entire transaction on a failed query

When one query inside a transaction fails (e.g., a bad SQL cast), PostgreSQL marks the connection as `InFailedSqlTransaction`. Every subsequent query on that connection fails immediately, including the fallback code you wrote to recover from the first error. You must call `db.rollback()` before any follow-up database operations. A bare `except` that logs and falls through is not sufficient.

### 8. Test thresholds need to be measured, not guessed

The generated test asserted MinHash Jaccard similarity > 50% between merge-sort code variants (the "original" and a version with two widespread variable renames). The actual measured similarity was ~30%. The 50% threshold was intuitive but wrong. Write the test, run it, measure the real value, then set the threshold with a deliberate margin — not a round number.

**Underlying issue:** trigram MinHash similarity between two code snippets that differ only in identifier names is much lower than human intuition suggests, because the changed identifiers appear in every trigram that touches them.

### 9. TypeScript strict mode catches dead code that blocks the Docker build

The generated code had two unused identifiers (`TIER_COLORS` constant, `showRemediation` state) that `noUnusedLocals: true` in `tsconfig.json` turns into compile errors. The Docker build runs `npm run build`, which runs `tsc`, which fails. AI code generators should always run `tsc --noEmit` before declaring TypeScript code complete.

### 10. `.env.example` is not self-executing

The README said to "configure environment" but did not explicitly say `cp .env.example .env`. Without `.env`, docker compose starts without environment variables and fails in a confusing, non-obvious way. A README should include the exact copy command, or the Makefile should do it automatically.

### 11. MinHash near-duplicate detection has a much lower effective threshold than its name implies

The system is configured with `SIMILARITY_THRESHOLD=0.75`. Modified code (variable renames, light reformatting) achieves ~30% Jaccard similarity with trigram MinHash — well below this threshold. In practice, the MinHash path catches only near-verbatim copies. Semantically similar but modified code is caught by the embedding/pgvector path. The `near_duplicate` match type will rarely appear. This is acceptable but should be documented, and the test expectations should reflect it.

---

## Bugs found but not fixed (candidates for GitHub issues)

| # | Area | Description |
|---|------|-------------|
| 1 | docker-compose | `environment: VITE_API_URL` for the dashboard service is dead code — Vite ignores runtime env vars. Current workaround (`.env.production`) hardcodes `localhost:8000` and breaks non-local deployments. Real fix: use build args. |
| 2 | scanner.py | `_find_exact_matches` is O(n) brute-force: loads up to 1000 corpus snippets and recomputes their hash. Should store and index `code_hash` in the DB. |
| 3 | scanner.py | MinHash threshold gap is undocumented: the `near_duplicate` match type is effectively unreachable for any modified code at the default threshold of 0.75. |
| 4 | docker-compose | RQ Dashboard (port 9181) is exposed without authentication. |
| 5 | license-guard/cli | The Go CLI (`scan`, `hook`, `status` commands) was never exercised. Its correctness against the live API is untested. |

---

## What worked well

- The three-strategy detection pipeline (exact hash → MinHash → semantic embeddings) is sound. Each layer handles a different failure mode.
- The SPDX risk taxonomy (HIGH/MEDIUM/LOW/CLEAN) with per-tier recommendations is clear and actionable.
- The pgvector fallback to manual cosine similarity is a good defensive pattern — once the SQL bug was fixed, the primary path worked correctly.
- The RQ worker/Redis job queue decouples scan submission from processing cleanly. Adding the `rq worker` command fixed it immediately.
- The dashboard auto-refresh via React Query `refetchInterval` works well once the v5 API was corrected.
- The remediation panel correctly uses `remediateMutation.data` as its own gate — no separate state needed.
