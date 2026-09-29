from unittest.mock import MagicMock, patch

import pytest

import app as app_module

USER_ROW = (1, "Alice", "alice@example.com", "active", "admin", "555-0100")
USER_JSON = {
    "id": 1,
    "name": "Alice",
    "email": "alice@example.com",
    "status": "active",
    "role": "admin",
    "phone": "555-0100",
}


@pytest.fixture(autouse=True)
def db_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "testdb")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "secret")


@pytest.fixture
def db():
    """Patch psycopg2.connect and hand back (conn, cursor) mocks."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    with patch.object(app_module.psycopg2, "connect", return_value=conn) as connect:
        yield connect, conn, cursor


def test_hello(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.data == b"Hello from Flask + PostgreSQL!"


def test_connect_uses_env_vars(client, db):
    connect, _, cursor = db
    cursor.fetchall.return_value = []

    client.get("/users")

    connect.assert_called_once_with(
        host="localhost", port="5432", database="testdb", user="test", password="secret"
    )


# GET /users

def test_list_users(client, db):
    _, conn, cursor = db
    cursor.fetchall.return_value = [USER_ROW, (2, "Bob", "bob@example.com", "inactive", None, None)]

    resp = client.get("/users")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "users": [
            USER_JSON,
            {"id": 2, "name": "Bob", "email": "bob@example.com", "status": "inactive", "role": None, "phone": None},
        ]
    }
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_list_users_empty(client, db):
    _, _, cursor = db
    cursor.fetchall.return_value = []

    resp = client.get("/users")

    assert resp.status_code == 200
    assert resp.get_json() == {"users": []}


# POST /users

def test_create_user(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = USER_ROW

    resp = client.post("/users", json={"name": "Alice", "email": "alice@example.com", "role": "admin", "phone": "555-0100"})

    assert resp.status_code == 201
    assert resp.get_json() == USER_JSON
    params = cursor.execute.call_args.args[1]
    assert params == ("Alice", "alice@example.com", "active", "admin", "555-0100")
    conn.commit.assert_called_once()


def test_create_user_defaults(client, db):
    _, _, cursor = db
    cursor.fetchone.return_value = (3, "Carol", "carol@example.com", "active", None, None)

    resp = client.post("/users", json={"name": "Carol", "email": "carol@example.com"})

    assert resp.status_code == 201
    params = cursor.execute.call_args.args[1]
    assert params == ("Carol", "carol@example.com", "active", None, None)


@pytest.mark.parametrize("missing", ["name", "email"])
def test_create_user_missing_field(client, db, missing):
    connect, _, _ = db
    body = {"name": "Alice", "email": "alice@example.com"}
    del body[missing]

    resp = client.post("/users", json=body)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": f"Missing required field: {missing}"}
    connect.assert_not_called()


def test_create_user_empty_body(client, db):
    resp = client.post("/users", json={})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Request body must contain JSON"}


# GET /users/<id>

def test_get_user(client, db):
    _, _, cursor = db
    cursor.fetchone.return_value = USER_ROW

    resp = client.get("/users/1")

    assert resp.status_code == 200
    assert resp.get_json() == USER_JSON
    assert cursor.execute.call_args.args[1] == (1,)


def test_get_user_not_found(client, db):
    _, _, cursor = db
    cursor.fetchone.return_value = None

    resp = client.get("/users/99")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "User not found"}


# DELETE /users/<id>

def test_delete_user(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = USER_ROW

    resp = client.delete("/users/1")

    assert resp.status_code == 200
    assert resp.get_json() == {"message": "User deleted successfully", "user": USER_JSON}
    last_sql, last_params = cursor.execute.call_args.args
    assert "DELETE FROM users" in last_sql
    assert last_params == (1,)
    conn.commit.assert_called_once()


def test_delete_user_not_found(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = None

    resp = client.delete("/users/99")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "User not found"}
    assert cursor.execute.call_count == 1  # no DELETE issued
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


# PATCH /users/<id>

def test_update_user(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = (1, "Alicia", "alice@example.com", "active", "admin", "555-0100")

    resp = client.patch("/users/1", json={"name": "Alicia"})

    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Alicia"

    update_call, audit_call = cursor.execute.call_args_list
    assert update_call.args[0].startswith("UPDATE users SET name = %s WHERE id = %s")
    assert update_call.args[1] == ["Alicia", 1]
    assert "INSERT INTO user_audit_log" in audit_call.args[0]
    assert audit_call.args[1] == (1, "user_updated")
    conn.commit.assert_called_once()
    cursor.close.assert_called_once()
    conn.close.assert_called_once()


def test_update_user_invalid_field(client, db):
    connect, _, _ = db

    resp = client.patch("/users/1", json={"password": "hunter2"})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid field: password"}
    connect.assert_not_called()


def test_update_user_empty_body(client, db):
    connect, _, _ = db

    resp = client.patch("/users/1", json={})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Request body must contain JSON"}
    connect.assert_not_called()


def test_update_user_db_error_rolls_back(client, db):
    _, conn, cursor = db
    cursor.execute.side_effect = Exception("boom")

    resp = client.patch("/users/1", json={"name": "Alicia"})

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Database update failed"}
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


def test_update_user_audit_failure_rolls_back(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = USER_ROW
    cursor.execute.side_effect = [None, Exception("audit insert failed")]

    resp = client.patch("/users/1", json={"name": "Alicia"})

    assert resp.status_code == 500
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_update_user_not_found(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = None

    resp = client.patch("/users/99", json={"name": "Nobody"})

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "User not found"}
    assert cursor.execute.call_count == 1  # no audit row written
    conn.commit.assert_not_called()
    conn.close.assert_called_once()


# Validation

VALID_USER = {"name": "Alice", "email": "alice@example.com"}


@pytest.mark.parametrize("body, error", [
    ({**VALID_USER, "name": ""}, "name must be a non-empty string"),
    ({**VALID_USER, "name": "   "}, "name must be a non-empty string"),
    ({**VALID_USER, "name": 42}, "name must be a non-empty string"),
    ({**VALID_USER, "email": None}, "email must be a non-empty string"),
    ({**VALID_USER, "email": "not-an-email"}, "email must be a valid email address"),
    ({**VALID_USER, "email": "a@b"}, "email must be a valid email address"),
    ({**VALID_USER, "status": "deleted"}, "status must be one of: active, inactive"),
    ({**VALID_USER, "role": 7}, "role must be a string or null"),
    ({**VALID_USER, "phone": 5550100}, "phone must be a string or null"),
    ({**VALID_USER, "phone": "+1-555-0100-0000"}, "phone must be at most 15 characters"),
    ({**VALID_USER, "password": "hunter2"}, "Invalid field: password"),
])
def test_create_user_rejects_invalid_values(client, db, body, error):
    connect, _, _ = db

    resp = client.post("/users", json=body)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": error}
    connect.assert_not_called()


@pytest.mark.parametrize("body, error", [
    ({"name": None}, "name must be a non-empty string"),
    ({"email": "nope"}, "email must be a valid email address"),
    ({"status": "archived"}, "status must be one of: active, inactive"),
])
def test_update_user_rejects_invalid_values(client, db, body, error):
    connect, _, _ = db

    resp = client.patch("/users/1", json=body)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": error}
    connect.assert_not_called()


def test_update_user_allows_clearing_optional_fields(client, db):
    _, _, cursor = db
    cursor.fetchone.return_value = (1, "Alice", "alice@example.com", "active", None, None)

    resp = client.patch("/users/1", json={"role": None, "phone": None})

    assert resp.status_code == 200


@pytest.mark.parametrize("url, method", [("/users", "post"), ("/users/1", "patch")])
@pytest.mark.parametrize("kwargs", [
    {"json": ["name", "email"]},
    {"data": "name=Alice", "content_type": "application/x-www-form-urlencoded"},
    {"data": "{not json", "content_type": "application/json"},
])
def test_non_object_body_is_rejected(client, db, url, method, kwargs):
    resp = getattr(client, method)(url, **kwargs)

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Request body must contain JSON"}


# JSON errors

def test_unknown_route_returns_json(client):
    resp = client.get("/nope")

    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Not Found"}


def test_wrong_method_returns_json(client):
    resp = client.put("/users/1")

    assert resp.status_code == 405
    assert resp.get_json() == {"error": "Method Not Allowed"}


def test_unexpected_error_returns_json(client, db):
    connect, _, _ = db
    connect.side_effect = RuntimeError("boom")

    resp = client.get("/users")

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Internal server error"}


# GET /health

def test_health_ok(client, db):
    connect, conn, _ = db

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok", "database": "ok"}
    assert connect.call_args.kwargs["connect_timeout"] == 3
    conn.close.assert_called_once()


def test_health_database_down(client, db):
    connect, _, _ = db
    connect.side_effect = app_module.psycopg2.OperationalError("connection refused")

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.get_json() == {"status": "error", "database": "unavailable"}
