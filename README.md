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

The root endpoint returns a simple greeting. The `/users` endpoint queries
PostgreSQL and returns users as JSON.

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

The migration history is in `migrations/`. It creates the `users` table and
then adds `created_at` and `status` columns.

Migrations are not currently run automatically by `docker compose up`, and the
current image does not copy the Alembic files into the runtime image. As a
result, a new PostgreSQL volume will not have a `users` table yet, so
`/users` requires the schema to be created separately.

This is an intentional next step for the Docker exercise: add a migration
step, either through an application entrypoint or a one-shot Compose service,
and make the API wait for that step before serving requests.

## Development notes

- The API container listens on port `5000`.
- The API reaches PostgreSQL at the Compose service hostname `postgres`.
- PostgreSQL data is stored in the named `postgres-data` volume.
- Gunicorn serves the Flask application in the container.
- The container runs the application as the unprivileged `appuser`.

## Current limitations

- There are no automated tests yet.
- Migrations are not part of the container startup flow.
- The API currently supports only a greeting endpoint and a read-only users
  endpoint.
