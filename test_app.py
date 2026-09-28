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
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


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
        host="localhost", database="testdb", user="test", password="secret"
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
    _, conn, cursor = db

    resp = client.patch("/users/1", json={"password": "hunter2"})

    assert resp.status_code == 400
    assert resp.get_json() == {"error": "Invalid field: password"}
    cursor.execute.assert_not_called()
    conn.close.assert_called_once()


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
