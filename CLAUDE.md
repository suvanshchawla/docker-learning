# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A small Flask + PostgreSQL user API (the `app/` package, built by `create_app()`), run with Docker Compose and used as a Docker learning project. Schema is managed by Alembic migrations in `migrations/` (raw SQL via psycopg2 — there are no ORM models, so `target_metadata = None` and `alembic revision --autogenerate` does not work; write migrations by hand).

## Commands

```bash
# Run the stack (postgres -> migrate -> api on :5000). Needs a .env with POSTGRES_DB/USER/PASSWORD
docker compose up --build
docker compose run --rm migrate          # re-run migrations

# New migration: must mount host migrations/ or the file is lost with the container
docker compose run --rm -v "$(pwd)/migrations:/app/migrations" migrate alembic revision -m "message"

# Tests (activate venv first: source venv/bin/activate; pip install -r requirements-dev.txt)
pytest -v                                # everything (integration tests need Docker)
pytest -m "not integration"              # fast unit tests only, no Docker
pytest tests/unit/test_users.py::test_name            # single test

# Benchmark GET /users on a throwaway stack (optional gunicorn flags as the argument)
scripts/bench.sh "--workers 4"
```

There is no linter configured. CI (`.github/workflows/tests.yml`) runs `pytest -v` then `docker build .`.

## Architecture

- **`app/`** is an application factory: `create_app()` in `__init__.py` wires up logging, error handlers and one Blueprint per file in `routes/` (`health`, `users`, `docs`). Gunicorn runs `app:create_app()`.
  - `db.py`: `db_connection()` borrows from a lazily created per-process `ThreadedConnectionPool`, sized by `DB_POOL_MIN`/`DB_POOL_MAX`; `get_connection()` is the unpooled variant used by test fixtures; configured via `DB_HOST`, `DB_PORT` (default 5432), `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
  - `validation.py`: `normalize_user()`, `validate_user()` and the field/length constants. `errors.py`: JSON error handlers. All errors, including 404/405/500, must return JSON `{"error": ...}`.
  - `logs.py`: JSON log formatter and the request-ID/access-log hooks. `openapi.py`: the hand-written OpenAPI spec (a unit test fails if a route is undocumented).
- **Audit log:** a successful user update writes a `user_updated` row to `user_audit_log` in the same transaction as the update; if either fails both roll back and the API returns 500.
- **Column limits are mirrored in code:** e.g. `PHONE_MAX_LENGTH` matches `users.phone VARCHAR(15)`. Update both when changing a migration.
- **Compose ordering:** `postgres` (healthcheck) -> `migrate` (`alembic upgrade head`, same image as the API) -> `api` (gunicorn, healthcheck hits `/health`). The `Dockerfile` copies `alembic.ini` and `migrations/` into the image, so rebuild after adding a migration.
- **`migrations/env.py`** builds the DB URL from the same `DB_*` env vars as the app.

## Testing

- `tests/unit/`: unit tests that mock `psycopg2`; use these for error paths such as rollbacks. The mock connection needs `closed = 0` and an idle `transaction_status` or the pool discards it.
- An autouse `fresh_pool` fixture in `tests/conftest.py` closes the pool around every test, so it is rebuilt from that test's `DB_*` env.
- `tests/integration/` (marked `integration`): uses the session-scoped `pg` fixture in `tests/conftest.py`, which starts a throwaway `postgres:17` Testcontainer and runs real Alembic migrations to head. The `real_db` fixture points the app at it via `DB_*` env vars and truncates `users`/`user_audit_log` before each test.
- Without Docker the integration tests skip locally, but **fail when the `CI` env var is set**.
- Test dependencies live in `requirements-dev.txt` to stay out of the production image.
