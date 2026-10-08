from contextlib import contextmanager
from psycopg2 import pool
import atexit
import os
import threading
import psycopg2

CONNECT_TIMEOUT = 3  # seconds to wait when opening a new connection


def _connection_params():
    return dict(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def get_connection(**kwargs):
    """Open a standalone, unpooled connection (the caller must close it)."""
    return psycopg2.connect(**_connection_params(), **kwargs)


# One pool per process. Gunicorn workers are separate processes, so each gets
# its own pool: total connections = workers x DB_POOL_MAX x replicas.
# psycopg2 only keeps DB_POOL_MIN idle connections; any beyond that are closed
# when returned, so DB_POOL_MIN is how many stay warm between bursts.
_pool = None
_pool_lock = threading.Lock()


def get_pool():
    """Create the connection pool on first use (so it's built inside each worker)."""
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = pool.ThreadedConnectionPool(
                int(os.environ.get("DB_POOL_MIN", "2")),
                int(os.environ.get("DB_POOL_MAX", "10")),
                connect_timeout=CONNECT_TIMEOUT,
                **_connection_params(),
            )
        return _pool


def close_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.closeall()
            _pool = None


atexit.register(close_pool)


@contextmanager
def db_connection():
    """Borrow a connection from the pool and always give it back.

    putconn() rolls back any transaction the caller left open and discards
    connections that have been closed, so a dead connection never goes back in.
    """
    p = get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)
