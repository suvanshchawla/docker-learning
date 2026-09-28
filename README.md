# Flask + PostgreSQL Docker Demo

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
├── test_app.py            # Pytest suite for the API
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

The root endpoint returns a simple greeting. The `/users` endpoints let you
list and create users, fetch an individual user, update selected fields, or
delete a user.

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
`email`, `status`, `role`, and `phone`. Requests with an empty body, a missing
required creation field, or an unknown update field return a `400` response.
Looking up, updating, or deleting a user that does not exist returns `404`.

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

The tests in `test_app.py` mock `psycopg2`, so they do not need Docker or a
running database. Set up a virtual environment once:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt pytest
```

On Debian or Ubuntu, `python3 -m venv` may first require
`sudo apt install python3.12-venv`.

Then run the suite with the virtual environment activated:

```bash
pytest -v
```

`requirements.txt` must be installed as well as `pytest`, because `app.py`
imports `psycopg2` at startup. `pytest` is not added to `requirements.txt` so
that it stays out of the production image.

To run the tests without a local Python setup, use a throwaway container:

```bash
docker run --rm -v "$(pwd)":/app -w /app python:3.12-slim \
  sh -c "pip install -q -r requirements.txt pytest && pytest -v"
```

## Development notes

- The API container listens on port `5000`.
- The API reaches PostgreSQL at the Compose service hostname `postgres`.
- PostgreSQL data is stored in the named `postgres-data` volume.
- Gunicorn serves the Flask application in the container.
- The container runs the application as the unprivileged `appuser`.
- The `migrate` service applies the schema before the API starts.

## Current limitations

- The tests use a mocked database, so they do not check the SQL against a
  real PostgreSQL instance.
- Database connections are opened and closed for each request; connection
  pooling has not been added yet.
- Request validation is limited to checking required fields on creation and
  the allowed field names on updates.
