import psycopg2
import pytest  # noqa: F401

from tests.unit.helpers import USER_ROW


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
