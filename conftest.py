import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import app as app_module

ALEMBIC_INI = Path(__file__).parent / "alembic.ini"


@pytest.fixture(autouse=True)
def fresh_pool():
    """Every test gets its own connection pool, built from that test's DB_* env."""
    app_module.close_pool()
    yield
    app_module.close_pool()


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


def run_alembic(env, action, revision):
    """Run an Alembic command with the DB_* variables pointing at `env`."""
    with pytest.MonkeyPatch.context() as mp:
        for key, value in env.items():
            mp.setenv(key, value)
        getattr(command, action)(Config(str(ALEMBIC_INI)), revision)


@pytest.fixture(scope="session")
def pg():
    """Start a throwaway PostgreSQL 17 container and migrate it to head."""
    from testcontainers.community.postgres import PostgresContainer

    try:
        container = PostgresContainer("postgres:17")
        container.start()
    except Exception as e:
        # In CI a missing Docker daemon is a real failure, not a reason to skip.
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Docker is not available for integration tests: {e}")

    env = {
        "DB_HOST": container.get_container_host_ip(),
        "DB_PORT": str(container.get_exposed_port(5432)),
        "DB_NAME": container.dbname,
        "DB_USER": container.username,
        "DB_PASSWORD": container.password,
    }
    try:
        run_alembic(env, "upgrade", "head")
        yield env
    finally:
        container.stop()


@pytest.fixture
def real_db(pg, monkeypatch):
    """Point the app at the test database and empty it before each test."""
    for key, value in pg.items():
        monkeypatch.setenv(key, value)

    conn = app_module.get_connection()
    with conn, conn.cursor() as cursor:
        cursor.execute("TRUNCATE users, user_audit_log RESTART IDENTITY")
    yield conn
    conn.close()
