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
    
    required_fields = ["name", "email", "status"]
    
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)