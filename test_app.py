from unittest.mock import MagicMock, patch

import pytest
from psycopg2.extensions import TRANSACTION_STATUS_IDLE

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
    monkeypatch.setenv("DB_POOL_MIN", "1")  # the pool opens this many connections up front


@pytest.fixture
def db():
    """Patch psycopg2.connect and hand back (conn, cursor) mocks."""
    conn = MagicMock()
    conn.closed = 0  # the pool checks these when a connection is returned
    conn.info.transaction_status = TRANSACTION_STATUS_IDLE
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = (0,)  # GET /users reads the total row count first

    def close_cursor(*exc):
        cursor.close()  # `with` closes the cursor...
        return False  # ...and never swallows an exception raised inside the block

    cursor.__exit__.side_effect = close_cursor
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
        host="localhost", port="5432", database="testdb", user="test", password="secret",
        connect_timeout=3,
    )


def test_connections_are_reused_across_requests(client, db):
    connect, conn, cursor = db
    cursor.fetchall.return_value = []

    for _ in range(5):
        assert client.get("/users").status_code == 200

    connect.assert_called_once()
    conn.close.assert_not_called()


def test_connection_returned_to_pool_after_failed_update(client, db):
    connect, conn, cursor = db
    cursor.execute.side_effect = [None, RuntimeError("boom")]
    cursor.fetchone.return_value = USER_ROW

    assert client.patch("/users/1", json={"name": "Alicia"}).status_code == 500

    # The next request must be able to borrow the same connection again.
    cursor.execute.side_effect = None
    cursor.fetchall.return_value = []
    assert client.get("/users").status_code == 200
    connect.assert_called_once()


def test_closed_connection_is_not_reused(client, db):
    connect, conn, cursor = db
    cursor.fetchall.return_value = []

    client.get("/users")
    conn.closed = 2  # e.g. the server restarted and dropped the connection
    client.get("/users")
    conn.closed = 0
    client.get("/users")

    assert connect.call_count == 2  # the dead connection was discarded, a new one opened


# GET /users

def test_list_users(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = (2,)
    cursor.fetchall.return_value = [USER_ROW, (2, "Bob", "bob@example.com", "inactive", None, None)]

    resp = client.get("/users")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "total": 2,
        "limit": 20,
        "offset": 0,
        "users": [
            USER_JSON,
            {"id": 2, "name": "Bob", "email": "bob@example.com", "status": "inactive", "role": None, "phone": None},
        ]
    }
    cursor.close.assert_called_once()
    conn.close.assert_not_called()  # returned to the pool, not closed


def test_list_users_empty(client, db):
    _, _, cursor = db
    cursor.fetchall.return_value = []

    resp = client.get("/users")

    assert resp.status_code == 200
    assert resp.get_json() == {"total": 0, "limit": 20, "offset": 0, "users": []}


def test_list_users_pagination_params_reach_the_query(client, db):
    _, _, cursor = db
    cursor.fetchall.return_value = []

    resp = client.get("/users?limit=5&offset=10")

    assert resp.status_code == 200
    assert resp.get_json()["limit"] == 5
    assert resp.get_json()["offset"] == 10
    assert cursor.execute.call_args[0][1] == (5, 10)


@pytest.mark.parametrize("query, message", [
    ("limit=abc", "limit must be an integer"),
    ("limit=0", "limit must be between 1 and 100"),
    ("limit=101", "limit must be between 1 and 100"),
    ("offset=-1", "offset must be at least 0"),
    ("offset=x", "offset must be an integer"),
])
def test_list_users_rejects_bad_pagination(client, db, query, message):
    connect, _, _ = db

    resp = client.get(f"/users?{query}")

    assert resp.status_code == 400
    assert resp.get_json() == {"error": message}
    connect.assert_not_called()


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


def test_create_user_trims_name_and_email(client, db):
    _, _, cursor = db
    cursor.fetchone.return_value = (3, "Carol", "carol@example.com", "active", None, None)

    resp = client.post("/users", json={"name": "  Carol\n", "email": "  carol@example.com \t"})

    assert resp.status_code == 201
    assert cursor.execute.call_args.args[1][:2] == ("Carol", "carol@example.com")


def test_create_user_duplicate_email(client, db):
    _, conn, cursor = db
    cursor.execute.side_effect = app_module.psycopg2.errors.UniqueViolation("duplicate key value violates unique constraint")

    resp = client.post("/users", json={"name": "Alice", "email": "alice@example.com"})

    assert resp.status_code == 409
    assert resp.get_json() == {"error": "Email already exists"}


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
    conn.close.assert_not_called()  # returned to the pool, not closed


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
    conn.close.assert_not_called()  # returned to the pool, not closed


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
    conn.close.assert_not_called()  # returned to the pool, not closed


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
    conn.close.assert_not_called()  # returned to the pool, not closed


def test_update_user_trims_name_and_email(client, db):
    _, _, cursor = db
    cursor.fetchone.return_value = USER_ROW

    resp = client.patch("/users/1", json={"name": " Alicia ", "email": " alice@example.com "})

    assert resp.status_code == 200
    update_call = cursor.execute.call_args_list[0]
    assert update_call.args[1] == ["Alicia", "alice@example.com", 1]


def test_update_user_duplicate_email(client, db):
    _, conn, cursor = db
    cursor.fetchone.return_value = USER_ROW
    cursor.execute.side_effect = app_module.psycopg2.errors.UniqueViolation("duplicate key value violates unique constraint")

    resp = client.patch("/users/1", json={"email": "bob@example.com"})

    assert resp.status_code == 409
    assert resp.get_json() == {"error": "Email already exists"}
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    assert cursor.execute.call_count == 1  # no audit row written


# Validation

VALID_USER = {"name": "Alice", "email": "alice@example.com"}


@pytest.mark.parametrize("body, error", [
    ({**VALID_USER, "name": ""}, "name must be a non-empty string"),
    ({**VALID_USER, "name": "   "}, "name must be a non-empty string"),
    ({**VALID_USER, "name": 42}, "name must be a non-empty string"),
    ({**VALID_USER, "email": None}, "email must be a non-empty string"),
    ({**VALID_USER, "email": "   "}, "email must be a non-empty string"),
    ({**VALID_USER, "email": " not an email "}, "email must be a valid email address"),
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
    conn.close.assert_not_called()  # returned to the pool, not closed


def test_health_database_down(client, db):
    connect, _, _ = db
    connect.side_effect = app_module.psycopg2.OperationalError("connection refused")

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.get_json() == {"status": "error", "database": "unavailable"}


# OpenAPI docs

def test_openapi_spec_is_valid(client):
    from openapi_spec_validator import validate

    resp = client.get("/openapi.json")

    assert resp.status_code == 200
    validate(resp.get_json())


def test_openapi_documents_every_route(client):
    documented = set()
    for path, item in client.get("/openapi.json").get_json()["paths"].items():
        for method in item:
            if method != "parameters":
                documented.add((path.replace("{user_id}", "<int:user_id>"), method.upper()))

    actual = {
        (rule.rule, method)
        for rule in app_module.app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
        if rule.endpoint not in ("static", "openapi_spec", "docs")
    }

    assert documented == actual


def test_docs_page_points_at_the_spec(client):
    resp = client.get("/docs")

    assert resp.status_code == 200
    assert b"/openapi.json" in resp.data


# Structured logging

@pytest.fixture
def log_lines():
    """Collect what the app logs, rendered by the real JSON formatter."""
    import io
    import json
    import logging

    from jsonlog import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    app_module.app.logger.addHandler(handler)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    app_module.app.logger.removeHandler(handler)


def test_request_is_logged_as_json(client, db, log_lines):
    _, _, cursor = db
    cursor.fetchall.return_value = []

    resp = client.get("/users?limit=5")

    (entry,) = log_lines()
    assert entry["message"] == "request"
    assert entry["level"] == "INFO"
    assert (entry["method"], entry["path"], entry["status"]) == ("GET", "/users", 200)
    assert entry["duration_ms"] >= 0
    assert entry["request_id"] == resp.headers["X-Request-ID"]


def test_request_id_from_caller_is_reused(client, db, log_lines):
    _, _, cursor = db
    cursor.fetchall.return_value = []

    resp = client.get("/users", headers={"X-Request-ID": "trace-123"})

    assert resp.headers["X-Request-ID"] == "trace-123"
    assert log_lines()[0]["request_id"] == "trace-123"


def test_each_request_gets_its_own_id(client, log_lines):
    ids = {client.get("/").headers["X-Request-ID"] for _ in range(3)}

    assert len(ids) == 3


def test_errors_are_logged_with_the_request_id_and_traceback(client, db, log_lines):
    _, _, cursor = db
    cursor.execute.side_effect = RuntimeError("boom")

    resp = client.get("/users")

    assert resp.status_code == 500
    error, access = log_lines()
    assert error["level"] == "ERROR"
    assert "RuntimeError: boom" in error["exception"]
    assert error["request_id"] == access["request_id"] == resp.headers["X-Request-ID"]
    assert access["status"] == 500


def test_health_checks_are_not_logged_at_info(client, db, log_lines):
    client.get("/health")

    assert log_lines() == []
