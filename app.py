from flask import Flask, request
import os
import psycopg2

app = Flask(__name__)
app.json.sort_keys = False  # Disable sorting of JSON keys

@app.route("/")
def hello():
    return "Hello from Flask + PostgreSQL!"


@app.route("/users")
def users():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

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
    data = request.get_json()

    required_fields = ["name", "email"]

    if not data:
        return {"error": "Request body must contain JSON"}, 400
    for field in required_fields:
        if field not in data:
            return {"error": f"Missing required field: {field}"}, 400

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

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
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

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
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],

    )

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
    data = request.get_json()

    if not data:
        return {"error": "Request body must contain JSON"}, 400

    conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
    )

    cursor = conn.cursor()


    # Check if the fields to update are valid
    valid_fields = ["name", "email", "status", "role", "phone"]
    for field in data.keys():
        if field not in valid_fields:
            cursor.close()
            conn.close()
            return {"error": f"Invalid field: {field}"}, 400

    # Build the update query dynamically based on the provided fields
    set_clause = ", ".join([f"{field} = %s" for field in data.keys()])
    values = list(data.values())
    values.append(user_id)  # Add user_id for the WHERE clause

    update_query = f"UPDATE users SET {set_clause} WHERE id = %s RETURNING id, name, email, status, role, phone"

    try:
        cursor.execute(update_query, values)
        updated_row = cursor.fetchone()

        conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Database error: {e}")
        cursor.close()
        conn.close()
        return {"error": "Database update failed"}, 500


    if updated_row:
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
