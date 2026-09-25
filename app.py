from flask import Flask
import os
import psycopg2

app = Flask(__name__)

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
    cursor.execute("SELECT id, name FROM users")
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return {"users": [{"id": row[0], "name": row[1]} for row in rows]}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)