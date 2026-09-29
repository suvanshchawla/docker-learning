from flask import Flask, request
from werkzeug.exceptions import HTTPException
import os
import re
import psycopg2

app = Flask(__name__)
app.json.sort_keys = False  # Disable sorting of JSON keys


def get_connection(**kwargs):
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        **kwargs,
    )


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
        conn = get_connection(connect_timeout=3)
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        finally:
            conn.close()
    except psycopg2.Error as e:
        app.logger.warning(f"Health check failed: {e}")
        return {"status": "error", "database": "unavailable"}, 503

    return {"status": "ok", "database": "ok"}


@app.route("/users")
def users():
    conn = get_connection()

    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, email, status, role, phone
    FROM users
    """)
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

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

    conn = get_connection()

    cursor = conn.cursor()

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

    cursor.close()
    conn.close()

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
    conn = get_connection()

    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, email, status, role, phone
    FROM users
    WHERE id = %s
    """, (user_id,))
    row = cursor.fetchone()

    cursor.close()
    conn.close()

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
    conn = get_connection()

    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, name, email, status, role, phone
    FROM users
    WHERE id = %s
    """, (user_id,))

    row = cursor.fetchone()

    if row is None:
        cursor.close()
        conn.close()

        return {"error": "User not found"}, 404


    cursor.execute(
        "DELETE FROM users WHERE id = %s",
        (user_id,)
    )



    conn.commit()

    cursor.close()
    conn.close()

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

    conn = get_connection()

    cursor = conn.cursor()

    # Build the update query dynamically based on the provided fields
    set_clause = ", ".join([f"{field} = %s" for field in data.keys()])
    values = list(data.values())
    values.append(user_id)  # Add user_id for the WHERE clause

    update_query = f"UPDATE users SET {set_clause} WHERE id = %s RETURNING id, name, email, status, role, phone"

    try:
        cursor.execute(update_query, values)
        updated_row = cursor.fetchone()

        if updated_row is None:
            conn.rollback()
            cursor.close()
            conn.close()
            return {"error": "User not found"}, 404

        cursor.execute(
            """
            INSERT INTO user_audit_log (user_id, action)
            VALUES (%s, %s)
            """,
            (user_id, "user_updated")
        )

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Database error: {e}")
        cursor.close()
        conn.close()
        return {"error": "Database update failed"}, 500

    cursor.close()
    conn.close()

    return {
        "id": updated_row[0],
        "name": updated_row[1],
        "email": updated_row[2],
        "status": updated_row[3],
        "role": updated_row[4],
        "phone": updated_row[5],
    }

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
