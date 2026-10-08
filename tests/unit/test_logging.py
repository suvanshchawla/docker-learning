import pytest


# Structured logging

@pytest.fixture
def log_lines(app):
    """Collect what the app logs, rendered by the real JSON formatter."""
    import io
    import json
    import logging

    from app.logs import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    app.logger.addHandler(handler)
    yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    app.logger.removeHandler(handler)


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
