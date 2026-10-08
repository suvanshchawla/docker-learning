from flask import Blueprint, current_app, request
import psycopg2

from app.db import db_connection
from app.validation import normalize_user, validate_user

bp = Blueprint("users", __name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def parse_int_arg(name, default, minimum, maximum=None):
    """Read an integer query parameter; raises ValueError with a message if it's invalid."""
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be {bound}")
    return value


@bp.route("/users")
def users():
    try:
        limit = parse_int_arg("limit", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        offset = parse_int_arg("offset", 0, 0)
    except ValueError as e:
        return {"error": str(e)}, 400

    with db_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM users")
        total = cursor.fetchone()[0]
        cursor.execute("""
        SELECT id, name, email, status, role, phone
        FROM users
        ORDER BY id
        LIMIT %s OFFSET %s
        """, (limit, offset))
        rows = cursor.fetchall()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
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

@bp.route("/users", methods=["POST"])
def create_user():
    data = normalize_user(request.get_json(silent=True))

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


@bp.route("/users/<int:user_id>", methods=["GET"])
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

@bp.route("/users/<int:user_id>", methods=["DELETE"])
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

@bp.route("/users/<int:user_id>", methods=["PATCH"])
def update_user(user_id):
    data = normalize_user(request.get_json(silent=True))

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

        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            current_app.logger.warning("Unique constraint violation while updating user")
            raise  # re-raised so the unique_violation handler returns the 409

        except Exception:
            conn.rollback()
            current_app.logger.exception("Database error while updating user")

            return {"error": "Database update failed"}, 500
