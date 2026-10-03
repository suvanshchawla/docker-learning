from contextlib import contextmanager
from flask import Flask, request
from psycopg2 import pool
from werkzeug.exceptions import HTTPException
import atexit
import os
import re
import threading
import psycopg2

app = Flask(__name__)
app.json.sort_keys = False  # Disable sorting of JSON keys


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
                int(os.environ.get("DB_POOL_MIN", "5")),
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


USER_FIELDS = ["name", "email", "status", "role", "phone"]
REQUIRED_FIELDS = ["name", "email"]
STATUSES = ["active", "inactive"]
PHONE_MAX_LENGTH = 15  # matches users.phone VARCHAR(15)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_user(data, partial=False):
    """Return an error message for an invalid user payload, or None if it's valid.

    partial=True is for PATCH, where every field is optional.
    """
    if not isinstance(data, dict) or not data:
        return "Request body must contain JSON"

    for field in data:
        if field not in USER_FIELDS:
            return f"Invalid field: {field}"

    if not partial:
        for field in REQUIRED_FIELDS:
            if field not in data:
                return f"Missing required field: {field}"

    for field in ["name", "email"]:
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            return f"{field} must be a non-empty string"

    if "email" in data and not EMAIL_PATTERN.match(data["email"]):
        return "email must be a valid email address"

    if "status" in data and data["status"] not in STATUSES:
        return f"status must be one of: {', '.join(STATUSES)}"

    for field in ["role", "phone"]:
        if data.get(field) is not None and not isinstance(data[field], str):
            return f"{field} must be a string or null"

    if data.get("phone") is not None and len(data["phone"]) > PHONE_MAX_LENGTH:
        return f"phone must be at most {PHONE_MAX_LENGTH} characters"

    return None


@app.errorhandler(HTTPException)
def http_error(e):
    # e.g. an unknown URL (404) or a wrong method (405)
    return {"error": e.name}, e.code


@app.errorhandler(Exception)
def unexpected_error(e):
    app.logger.exception("Unhandled error")
    return {"error": "Internal server error"}, 500


@app.route("/")
def hello():
    return "Hello from Flask + PostgreSQL!"


@app.route("/health")
def health():
    try:
        with db_connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    except psycopg2.Error as e:
        app.logger.warning(f"Health check failed: {e}")
        return {"status": "error", "database": "unavailable"}, 503

    return {"status": "ok", "database": "ok"}


@app.route("/users")
def users():
    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute("""
        SELECT id, name, email, status, role, phone
        FROM users
        """)
        rows = cursor.fetchall()

    return {
        "users": [
            {
                "id": row[0],
                "name": row[1],
                "email": row[2],
                "status": row[3],
                "role": row[4],
                "phone": row[5],
            }
            for row in rows
        ]
    }

@app.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True)

    error = validate_user(data)
    if error:
        return {"error": error}, 400

    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (name, email, status, role, phone)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, email, status, role, phone;
            """,
            (
                data["name"],
                data["email"],
                data.get("status", "active"),
                data.get("role"),
                data.get("phone"),
            ),
        )
        row = cursor.fetchone()
        conn.commit()

    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "status": row[3],
        "role": row[4],
        "phone": row[5],
    }, 201


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute("""
        SELECT id, name, email, status, role, phone
        FROM users
        WHERE id = %s
        """, (user_id,))
        row = cursor.fetchone()

    if row:
        return {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "status": row[3],
            "role": row[4],
            "phone": row[5],
        }
    else:
        return {"error": "User not found"}, 404

@app.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute("""
        SELECT id, name, email, status, role, phone
        FROM users
        WHERE id = %s
        """, (user_id,))
        row = cursor.fetchone()

        if row is None:
            return {"error": "User not found"}, 404

        cursor.execute(
            "DELETE FROM users WHERE id = %s",
            (user_id,)
        )
        conn.commit()

    return {"message": "User deleted successfully",
            "user": {
                "id": row[0],
                "name": row[1],
                "email": row[2],
                "status": row[3],
                "role": row[4],
                "phone": row[5],
            }
            }, 200

@app.route("/users/<int:user_id>", methods=["PATCH"])
def update_user(user_id):
    data = request.get_json(silent=True)

    error = validate_user(data, partial=True)
    if error:
        return {"error": error}, 400

    # Build the update query dynamically based on the provided fields
    set_clause = ", ".join([f"{field} = %s" for field in data.keys()])
    values = list(data.values())
    values.append(user_id)  # Add user_id for the WHERE clause

    update_query = f"UPDATE users SET {set_clause} WHERE id = %s RETURNING id, name, email, status, role, phone"

    with db_connection() as conn, conn.cursor() as cursor:
        try:
            cursor.execute(update_query, values)
            updated_row = cursor.fetchone()

            if updated_row is None:
                conn.rollback()
                return {"error": "User not found"}, 404

            cursor.execute(
                """
                INSERT INTO user_audit_log (user_id, action)
                VALUES (%s, %s)
                """,
                (user_id, "user_updated")
            )

            conn.commit()

            return {
                "id": updated_row[0],
                "name": updated_row[1],
                "email": updated_row[2],
                "status": updated_row[3],
                "role": updated_row[4],
                "phone": updated_row[5],
            }

        except Exception as e:
            conn.rollback()
            app.logger.error("Database error while updating user")
            print(f"Database error: {e}")

            return {"error": "Database update failed"}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
