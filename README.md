# Flask + PostgreSQL Docker Demo

[![Tests](https://github.com/suvanshchawla/docker-learning/actions/workflows/tests.yml/badge.svg)](https://github.com/suvanshchawla/docker-learning/actions/workflows/tests.yml)

A small Flask API backed by PostgreSQL and managed with Docker Compose. This
project is intended as a hands-on introduction to:

- Building a Python application image with a multi-stage `Dockerfile`
- Running an API and database as separate Compose services
- Connecting containers over a Compose network
- Persisting PostgreSQL data in a named volume
- Managing database schema changes with Alembic

## Project structure

```text
.
├── app.py                 # Flask application
├── Dockerfile             # Multi-stage API image
├── docker-compose.yml     # API and PostgreSQL services
├── requirements.txt       # Python dependencies
├── requirements-dev.txt   # Test dependencies (pytest, testcontainers)
├── pytest.ini             # Pytest configuration and markers
├── conftest.py            # Shared fixtures, including the test database
├── test_app.py            # Unit tests with a mocked database
├── test_integration.py    # Integration tests against real PostgreSQL
├── .github/workflows/     # GitHub Actions CI
├── alembic.ini            # Alembic configuration
└── migrations/            # Database migration history
```

## Prerequisites

- Docker Engine
- Docker Compose v2 (`docker compose`)

## Configuration

Create a `.env` file in the project root. It is intentionally ignored by Git.

```dotenv
POSTGRES_DB=docker_demo
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-this-for-local-development
```

Use a stronger password if this project is exposed outside your local machine.
Do not commit the `.env` file or real credentials.

## Run the application

Build the API image and start both services:

```bash
docker compose up --build
```

The API is available at:

- <http://localhost:5000/>
- <http://localhost:5000/users>
- <http://localhost:5000/health>

The root endpoint returns a simple greeting. The `/users` endpoints let you
list and create users, fetch an individual user, update selected fields, or
delete a user.

`/health` checks that the API can reach PostgreSQL. It returns
`200 {"status": "ok", "database": "ok"}`, or
`503 {"status": "error", "database": "unavailable"}` if the database cannot be
reached within 3 seconds.

List users:

```bash
curl http://localhost:5000/users
```

Create a user (`name` and `email` are required; `status` defaults to `active`):

```bash
curl -X POST http://localhost:5000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "role": "admin",
    "phone": "+1-555-0100"
  }'
```

Fetch one user:

```bash
curl http://localhost:5000/users/1
```

Update one or more fields. Accepted fields are `name`, `email`, `status`,
`role`, and `phone`:

```bash
curl -X PATCH http://localhost:5000/users/1 \
  -H "Content-Type: application/json" \
  -d '{"status": "inactive", "phone": "+1-555-0101"}'
```

Delete a user:

```bash
curl -X DELETE http://localhost:5000/users/1
```

The list and individual-user endpoints return user records with `id`, `name`,
`email`, `status`, `role`, and `phone`.

Request bodies are validated before the database is touched:

| Field | Rule |
|---|---|
| `name` | Required on create. Must be a non-empty string. |
| `email` | Required on create. Must look like `user@domain.tld`. |
| `status` | Optional. `active` (the default) or `inactive`. |
| `role` | Optional. A string, or `null` to clear it. |
| `phone` | Optional. A string of at most 15 characters, or `null` to clear it. |

A body that isn't a JSON object, an unknown field, or a value that breaks a
rule returns `400` with a message such as
`{"error": "email must be a valid email address"}`. Looking up, updating, or
deleting a user that does not exist returns `404`.

Every error is JSON with an `error` key, including unknown URLs
(`404 {"error": "Not Found"}`), unsupported methods (`405`), and unexpected
server errors (`500 {"error": "Internal server error"}`, with the details in
the API logs).

Every successful update also writes a `user_updated` row to the
`user_audit_log` table in the same transaction. If either write fails, both are
rolled back and the API returns `500`.

Useful commands:

```bash
# View service status
docker compose ps

# Follow API logs
docker compose logs -f api

# Stop the services
docker compose down

# Stop the services and delete the PostgreSQL data volume
docker compose down -v
```

The last command is destructive for local database data.

## Database migrations

The migration history is in `migrations/`. It creates the `users` table, adds
`created_at`, `status`, `role`, and `phone` columns, and then creates the
`user_audit_log` table.

Migrations run automatically through the dedicated `migrate` Compose
service:

1. PostgreSQL starts and must pass its healthcheck.
2. The `migrate` service runs `alembic upgrade head`.
3. The API starts only after migrations complete successfully.

To run migrations again after changing the migration files:

```bash
docker compose run --rm migrate
```

When creating a new migration revision, mount the host `migrations/` directory
into the temporary container. Without this volume mount, Alembic writes the
revision inside the container, and the generated file is lost when the
container is removed:

```bash
docker compose run --rm \
  -v "$(pwd)/migrations:/app/migrations" \
  migrate \
  alembic revision -m "add phone to users"
```

The migration service uses the same application image as the API. The
`Dockerfile` copies `alembic.ini` and `migrations/` into that image.

## Running tests

There are two test suites:

- `test_app.py` contains unit tests. They replace `psycopg2` with a mock, so
  they run in milliseconds and cover error paths that are hard to trigger
  against a real database, such as rollbacks after a failed write.
- `test_integration.py` contains integration tests. They start a throwaway
  `postgres:17` container with [Testcontainers](https://testcontainers.com/),
  apply the real Alembic migrations, and send requests through the API. They
  check the SQL against the real schema, the audit-log writes, database
  constraints, and that the migrations downgrade and upgrade cleanly.

Set up a virtual environment once:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

On Debian or Ubuntu, `python3 -m venv` may first require
`sudo apt install python3.12-venv`.

With the virtual environment activated and Docker running, run everything:

```bash
pytest -v
```

To run only the fast unit tests, without Docker:

```bash
pytest -m "not integration"
```

If Docker is not running, the integration tests are skipped with a message
rather than failing. In CI, where the `CI` environment variable is set, they
fail instead, so a broken Docker setup cannot hide untested code.

The test dependencies live in `requirements-dev.txt` so that they stay out of
the production image.

The integration tests connect to PostgreSQL on a random port. The app and
Alembic read the port from `DB_PORT`, which defaults to `5432`, so Docker
Compose needs no changes.

## Continuous integration

`.github/workflows/tests.yml` runs on every push and pull request. It installs
`requirements-dev.txt`, runs the full test suite (GitHub's Ubuntu runners
have Docker, so the integration tests run too), and builds the Docker image.

## Development notes

- The API container listens on port `5000`.
- The API reaches PostgreSQL at the Compose service hostname `postgres`, on
  port `DB_PORT` (default `5432`).
- PostgreSQL data is stored in the named `postgres-data` volume.
- Gunicorn serves the Flask application in the container.
- The container runs the application as the unprivileged `appuser`.
- The `migrate` service applies the schema before the API starts.
- The `api` service has a Compose healthcheck that calls `/health` every 10
  seconds. `docker compose ps` shows it as `healthy` or `unhealthy`.

## Connection pooling

The API keeps a `psycopg2` `ThreadedConnectionPool` instead of opening a
connection per request. Each request borrows a connection and returns it when
done; the pool rolls back anything left uncommitted and discards connections
that have closed. It is created on first use, so every Gunicorn worker process
gets its own pool.

| Variable | Default | Meaning |
|---|---|---|
| `DB_POOL_MIN` | `5` | Connections opened up front, and the most idle connections kept between requests |
| `DB_POOL_MAX` | `10` | Most connections one process will hold at once |

The pool only keeps `DB_POOL_MIN` idle connections. During a burst of
concurrent requests it opens extra connections (up to `DB_POOL_MAX`), but
closes the surplus ones as they are returned. Raise `DB_POOL_MIN` if your
traffic is bursty and you want more connections kept warm.

Total connections to PostgreSQL are roughly
`workers x DB_POOL_MAX x replicas` at peak (`workers x DB_POOL_MIN x replicas` when idle), which must stay below the server's
`max_connections` (100 by default). If a process needs more than
`DB_POOL_MAX` connections at once, the extra request fails with a `500`
rather than waiting.

## Current limitations


- Email validation only checks the basic `user@domain.tld` shape. It does
  not confirm that the address exists, and duplicate emails are allowed.
