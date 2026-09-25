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

The root endpoint returns a simple greeting. The `/users` endpoint supports
listing users with `GET` and creating users with `POST`.

List users:

```bash
curl http://localhost:5000/users
```

Create a user:

```bash
curl -X POST http://localhost:5000/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "status": "active",
    "role": "admin",
    "phone": "+1-555-0100"
  }'
```

The `name`, `email`, and `status` fields are required. `role` and `phone` are
optional.

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
then adds `created_at`, `status`, `role`, and `phone` columns.

Migrations now run automatically through the dedicated `migrate` Compose
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

## Development notes

- The API container listens on port `5000`.
- The API reaches PostgreSQL at the Compose service hostname `postgres`.
- PostgreSQL data is stored in the named `postgres-data` volume.
- Gunicorn serves the Flask application in the container.
- The container runs the application as the unprivileged `appuser`.
- The `migrate` service applies the schema before the API starts.

## Current limitations

- There are no automated tests yet.
- Database connections are opened and closed for each request; connection
  pooling has not been added yet.
- The API currently has no update or delete user operations.
