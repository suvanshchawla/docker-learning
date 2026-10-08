from flask import Blueprint, current_app
import psycopg2

from app.db import db_connection

bp = Blueprint("health", __name__)


@bp.route("/")
def hello():
    return "Hello from Flask + PostgreSQL!"


@bp.route("/health")
def health():
    try:
        with db_connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    except psycopg2.Error as e:
        current_app.logger.warning(f"Health check failed: {e}")
        return {"status": "error", "database": "unavailable"}, 503

    return {"status": "ok", "database": "ok"}
