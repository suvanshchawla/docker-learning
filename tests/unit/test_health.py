import psycopg2


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
    connect.side_effect = psycopg2.OperationalError("connection refused")

    resp = client.get("/health")

    assert resp.status_code == 503
    assert resp.get_json() == {"status": "error", "database": "unavailable"}


def test_hello(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.data == b"Hello from Flask + PostgreSQL!"

