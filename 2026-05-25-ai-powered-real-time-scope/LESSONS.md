# Lessons Learned — First Test Run (2026-06-08)

This document records what was found during the first end-to-end test of this MVP
on a real machine (Windows 11, Python 3.12, Docker Desktop). It is intended as
feedback to the autonomous problem-solver for future MVP generation cycles.

---

## Bugs Fixed During Testing

### 1. Unused and Python 3.12-incompatible dependency
**File:** `backend/requirements.txt`
**Symptom:** `pip install` failed immediately — `unstructured==0.13.7` requires Python <3.12.
**Root cause:** The package was listed as a dependency but never imported anywhere in the
code. `document_parser.py` uses PyMuPDF and python-docx directly.
**Fix:** Removed `unstructured[pdf]==0.13.7` from requirements.txt.
**Lesson for AI:** Before listing a package in requirements.txt, verify it is actually
imported in the codebase. Run a compatibility check against the target Python version range.

---

### 2. passlib / bcrypt version incompatibility
**File:** `backend/requirements.txt`
**Symptom:** Registration returned HTTP 500. Error: `module 'bcrypt' has no attribute '__about__'`.
**Root cause:** `passlib==1.7.4` (last updated 2020) accesses `bcrypt.__about__.__version__`,
an attribute removed in bcrypt 4.x. pip resolved to bcrypt 5.0.0, breaking all password
operations.
**Fix:** Added explicit pin `bcrypt==4.0.1` to requirements.txt.
**Lesson for AI:** passlib is unmaintained. Whenever using `passlib[bcrypt]`, always
explicitly pin `bcrypt==4.0.1`. A general rule: if a security library hasn't been updated
in 3+ years, pin its low-level dependencies explicitly.

---

### 3. SQLAlchemy native enum mismatch with Alembic migration
**Files:** `backend/app/models.py`, `backend/alembic/versions/001_initial.py`
**Symptom:** Dashboard, Violations, and Change Orders pages all returned HTTP 500.
Error: `operator does not exist: character varying = violationstatus`.
**Root cause:** The Alembic migration created `status`/`severity` columns as `VARCHAR(50)`,
but `models.py` declared them as `SAEnum(ViolationStatus)` (native PostgreSQL enum types).
SQLAlchemy's `create_all()` on startup created the PostgreSQL enum types, but the table
columns were still VARCHAR. asyncpg could not compare `VARCHAR = violationstatus`.
**Fix:** Added `native_enum=False` to all `SAEnum()` column definitions in models.py.
**Lesson for AI:** Alembic migrations and SQLAlchemy models must agree on column types.
If migrations use `String(50)` for enum-like columns, models must use `native_enum=False`.
Never mix Alembic-managed schema creation with SQLAlchemy `create_all()` for the same tables —
pick one authoritative source and stick to it.

---

### 4. `.env` file not loaded — API key silently missing
**File:** `backend/app/config.py`
**Symptom:** AI analysis was silently skipped after message submission. No error logged.
Background task never ran. The `if settings.openai_api_key:` guard evaluated False.
**Root cause:** pydantic-settings `env_file = ".env"` resolves relative to the process
working directory. The README instructs `cd backend && uvicorn ...`, making cwd = `backend/`.
But `.env` lives one level up in `scope-creep-detector/`. All env vars silently fell back
to defaults, including `openai_api_key = ""`.
**Fix:** Changed `env_file = ".env"` to `env_file = "../.env"` in config.py.
**Lesson for AI:** When the FastAPI app lives in a `backend/` subdirectory and `.env`
is at the project root, set `env_file` to the path relative to where uvicorn will be
launched from. Alternatively, document that uvicorn must be run from the project root,
and adjust the path accordingly. The silent failure mode here is particularly dangerous —
consider adding a startup assertion that logs a clear warning when critical env vars are empty.

---

## Known Issues Not Fixed During This Session

### 5. WeasyPrint PDF generation fails on Windows
**Issue:** [#64](https://github.com/ChristianVonGebhardi/autonomous-problem-solver/issues/64)
WeasyPrint requires GTK/GLib native libraries (`gobject-2.0-0`, `pango`) that are not
available on Windows by default. The HTML fallback is generated and saved correctly, but
the frontend has no UI to download or view it.
**Lesson for AI:** WeasyPrint is Linux/macOS-only in practice. For cross-platform PDF
generation, prefer `reportlab`, `fpdf2`, or client-side browser print. If WeasyPrint is
chosen, document the GTK dependency requirement prominently and implement a frontend
fallback that serves the HTML file when no PDF is available.

### 6. Drag-and-drop file upload opens file in browser instead of uploading
**Issue:** [#65](https://github.com/ChristianVonGebhardi/autonomous-problem-solver/issues/65) — filed separately
Dropping a `.txt` file onto the contract upload area navigates the browser to that file
instead of triggering the upload handler. The file picker button works correctly.
**Lesson for AI:** Drag-and-drop upload zones must call `event.preventDefault()` on the
`dragover` event to prevent the browser's default file-open behavior. This is a common
omission when implementing drop zones.

### 7. docker-compose.yml `version` attribute is obsolete
**Issue:** [#63](https://github.com/ChristianVonGebhardi/autonomous-problem-solver/issues/63)
The `version` key generates a warning on every `docker-compose` command with Docker
Compose v2+.
**Lesson for AI:** Remove the top-level `version` field from all generated docker-compose.yml
files. It has been deprecated since Docker Compose v2 (2022).

---

## What the AI Got Right

- Overall architecture is well-structured and production-ready in its shape
- Frontend design is polished, professional, and clearly communicates the product's value
- The AI analysis pipeline (embed → pgvector semantic search → GPT-4o analysis → violation
  + change order generation) is correctly implemented end-to-end
- WebSocket real-time notifications work correctly
- Error handling and fallback logic is thoughtful (embedding fallback to full-text,
  HTML fallback when PDF fails)
- The sample test in the README accurately demonstrates the core product value
- Background task architecture correctly decouples HTTP response from OpenAI latency

---

## Setup Difficulty

**Time from zero to working app (with an experienced guide):** ~3 hours
Blockers in order: Docker Desktop not installed → WSL2 not installed → pip install
failure (unstructured) → bcrypt crash on registration → enum 500 errors → .env not loaded.

All blockers were dependency/configuration issues, not architectural problems. The
business logic and AI pipeline worked correctly on first run once the environment was
correct.
