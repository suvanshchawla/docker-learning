import pytest

from conftest import run_alembic

pytestmark = pytest.mark.integration

ADA = {"name": "Ada Lovelace", "email": "ada@example.com", "role": "admin", "phone": "+1-555-0100"}


def query(conn, sql, params=()):
    with conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def create(client, body=ADA):
    resp = client.post("/users", json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_create_then_fetch(client, real_db):
    created = create(client)

    assert created == {"id": 1, "status": "active", **ADA}
    assert client.get("/users/1").get_json() == created
    assert client.get("/users").get_json() == {"users": [created]}


def test_status_defaults_to_active(client, real_db):
    create(client, {"name": "Bob", "email": "bob@example.com"})

    assert query(real_db, "SELECT status, role, phone FROM users") == [("active", None, None)]


def test_update_writes_audit_row(client, real_db):
    create(client)

    resp = client.patch("/users/1", json={"status": "inactive", "phone": "+1-555-0101"})

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "inactive"
    assert query(real_db, "SELECT status, phone FROM users WHERE id = 1") == [("inactive", "+1-555-0101")]
    assert query(real_db, "SELECT user_id, action FROM user_audit_log") == [(1, "user_updated")]


def test_update_missing_user_writes_no_audit_row(client, real_db):
    resp = client.patch("/users/99", json={"name": "Nobody"})

    assert resp.status_code == 404
    assert query(real_db, "SELECT count(*) FROM user_audit_log") == [(0,)]


def test_update_null_name_is_rejected(client, real_db):
    create(client)

    resp = client.patch("/users/1", json={"name": None})

    assert resp.status_code == 400
    assert query(real_db, "SELECT name FROM users WHERE id = 1") == [("Ada Lovelace",)]
    assert query(real_db, "SELECT count(*) FROM user_audit_log") == [(0,)]


def test_update_can_clear_optional_fields(client, real_db):
    create(client)

    resp = client.patch("/users/1", json={"role": None, "phone": None})

    assert resp.status_code == 200
    assert query(real_db, "SELECT role, phone FROM users WHERE id = 1") == [(None, None)]


def test_health_with_real_database(client, real_db):
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "database": "ok"}


def test_health_when_database_unreachable(client, real_db, monkeypatch):
    monkeypatch.setenv("DB_PORT", "1")  # nothing listens on this port

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.get_json() == {"status": "error", "database": "unavailable"}


def test_delete_then_fetch(client, real_db):
    create(client)

    assert client.delete("/users/1").status_code == 200
    assert client.get("/users/1").status_code == 404
    assert query(real_db, "SELECT count(*) FROM users") == [(0,)]


@pytest.mark.parametrize("method, url", [("post", "/users"), ("patch", "/users/1")])
def test_phone_too_long_is_rejected(client, real_db, method, url):
    create(client)
    body = {"name": "Eve", "email": "eve@example.com", "phone": "+1-555-0100-0000"}

    resp = getattr(client, method)(url, json=body)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "phone must be at most 15 characters"}
    assert query(real_db, "SELECT count(*) FROM users") == [(1,)]


def test_migrations_downgrade_and_upgrade(pg, real_db):
    run_alembic(pg, "downgrade", "base")
    assert query(real_db, "SELECT to_regclass('users'), to_regclass('user_audit_log')") == [(None, None)]

    run_alembic(pg, "upgrade", "head")
    assert query(real_db, "SELECT to_regclass('users'), to_regclass('user_audit_log')") == [("users", "user_audit_log")]
