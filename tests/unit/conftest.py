from unittest.mock import MagicMock, patch

import psycopg2
import pytest
from psycopg2.extensions import TRANSACTION_STATUS_IDLE


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
    with patch.object(psycopg2, "connect", return_value=conn) as connect:
        yield connect, conn, cursor
